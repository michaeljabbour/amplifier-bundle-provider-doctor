"""TDD tests for mount() function in provider_failover.

Tests cover:
- mount() returns None (no cleanup needed)
- mount() builds FailoverProvider and calls coordinator.mount('providers', ..., name='failover')
- mount() resolves providers from coordinator.get('providers')
- mount() strips 'provider-' prefix from tier provider names for lookup
- mount() skips tiers with unresolved providers (logs warning)
- mount() returns None and logs warning when no tiers configured
- mount() returns None and logs warning when no tiers resolve
- mount() passes probe_interval to FailoverProvider
- mount() reads context_window from provider.get_info().defaults
- mount() handles config=None gracefully
- mount() builds multi-tier failover chain in order
"""

from __future__ import annotations

import logging
import os
import sys

import pytest

# ---------------------------------------------------------------------------
# sys.path: make modules/provider-failover importable from tests
# ---------------------------------------------------------------------------
_BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODULE_PATH = os.path.join(_BUNDLE_ROOT, "modules", "provider-failover")
if _MODULE_PATH not in sys.path:
    sys.path.insert(0, _MODULE_PATH)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockProviderInfo:
    """Simulates the object returned by provider.get_info() with a .defaults attribute."""

    def __init__(self, context_window: int = 200_000) -> None:
        self.defaults = {"context_window": context_window}


class MockMountProvider:
    """Minimal mock provider for mount() tests."""

    def __init__(self, context_window: int = 200_000) -> None:
        self._context_window = context_window

    def get_info(self) -> MockProviderInfo:
        return MockProviderInfo(self._context_window)


class MockCoordinator:
    """Minimal mock coordinator with get() and mount() methods."""

    def __init__(self, providers: dict | None = None) -> None:
        self._providers = providers or {}
        self.mounted: dict = {}

    def get(self, namespace: str) -> dict:
        if namespace == "providers":
            return self._providers
        return {}

    def mount(self, namespace: str, obj: object, name: str | None = None) -> None:
        self.mounted[name] = obj


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMountReturnsNone:
    @pytest.mark.asyncio
    async def test_mount_returns_none_on_success(self):
        """mount() returns None (no cleanup function needed)."""
        from provider_failover import mount

        provider = MockMountProvider()
        coordinator = MockCoordinator(providers={"anthropic": provider})
        config = {
            "tiers": [
                {"provider": "anthropic", "model": "claude-opus", "label": "primary"}
            ]
        }
        result = await mount(coordinator, config)
        assert result is None


class TestMountBuildsFailoverProvider:
    @pytest.mark.asyncio
    async def test_mount_constructs_failover_provider(self):
        """mount() constructs FailoverProvider and mounts it on coordinator."""
        from provider_failover import mount
        from provider_failover.failover import FailoverProvider  # noqa: F401

        provider = MockMountProvider()
        coordinator = MockCoordinator(providers={"anthropic": provider})
        config = {
            "tiers": [
                {"provider": "anthropic", "model": "claude-opus", "label": "primary"}
            ]
        }
        await mount(coordinator, config)

        assert "failover" in coordinator.mounted
        assert isinstance(coordinator.mounted["failover"], FailoverProvider)

    @pytest.mark.asyncio
    async def test_mount_calls_coordinator_mount_with_correct_args(self):
        """mount() calls coordinator.mount('providers', failover, name='failover')."""
        from provider_failover import mount
        from provider_failover.failover import FailoverProvider

        provider = MockMountProvider()
        coordinator = MockCoordinator(providers={"anthropic": provider})
        config = {
            "tiers": [
                {"provider": "anthropic", "model": "claude-opus", "label": "primary"}
            ]
        }
        await mount(coordinator, config)

        # The failover should be stored under 'failover' key
        fp = coordinator.mounted.get("failover")
        assert fp is not None
        assert isinstance(fp, FailoverProvider)


class TestMountProviderResolution:
    @pytest.mark.asyncio
    async def test_mount_resolves_provider_from_coordinator(self):
        """mount() resolves providers from coordinator.get('providers') dict."""
        from provider_failover import mount

        provider = MockMountProvider()
        coordinator = MockCoordinator(providers={"anthropic": provider})
        config = {
            "tiers": [
                {"provider": "anthropic", "model": "claude-opus-4", "label": "tier1"}
            ]
        }
        await mount(coordinator, config)

        fp = coordinator.mounted["failover"]
        assert fp._tiers[0].provider is provider

    @pytest.mark.asyncio
    async def test_mount_strips_provider_prefix_for_lookup(self):
        """mount() strips 'provider-' prefix from tier provider field for coordinator lookup."""
        from provider_failover import mount

        provider = MockMountProvider()
        # Coordinator stores with key 'anthropic' (no prefix)
        coordinator = MockCoordinator(providers={"anthropic": provider})
        # Tier config specifies 'provider-anthropic' (with prefix)
        config = {
            "tiers": [
                {
                    "provider": "provider-anthropic",
                    "model": "claude-opus",
                    "label": "primary",
                }
            ]
        }
        await mount(coordinator, config)

        assert "failover" in coordinator.mounted
        fp = coordinator.mounted["failover"]
        assert fp._tiers[0].provider is provider

    @pytest.mark.asyncio
    async def test_mount_skips_tier_missing_provider_key(self, caplog):
        """mount() skips a tier that has no 'provider' key and logs a clear diagnostic."""
        from provider_failover import mount

        provider = MockMountProvider()
        coordinator = MockCoordinator(providers={"anthropic": provider})
        config = {
            "tiers": [
                # This tier is missing the 'provider' key entirely
                {"model": "claude-opus", "label": "bad-tier"},
                {"provider": "anthropic", "model": "claude-opus", "label": "good-tier"},
            ]
        }
        with caplog.at_level(logging.WARNING):
            await mount(coordinator, config)

        assert "failover" in coordinator.mounted
        fp = coordinator.mounted["failover"]
        # Only the good tier should be present
        assert len(fp._tiers) == 1
        assert fp._tiers[0].label == "good-tier"
        # Warning must mention the missing key, not '' or empty provider name
        assert any(
            "missing" in record.message and "provider" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_mount_skips_unresolved_provider_with_warning(self, caplog):
        """mount() skips tiers whose providers cannot be resolved and logs a warning."""
        from provider_failover import mount

        provider = MockMountProvider()
        coordinator = MockCoordinator(providers={"anthropic": provider})
        config = {
            "tiers": [
                {"provider": "nonexistent", "model": "ghost-model", "label": "missing"},
                {"provider": "anthropic", "model": "claude-opus", "label": "primary"},
            ]
        }
        with caplog.at_level(logging.WARNING):
            await mount(coordinator, config)

        assert "failover" in coordinator.mounted
        fp = coordinator.mounted["failover"]
        # Only the resolved tier is present
        assert len(fp._tiers) == 1
        assert fp._tiers[0].label == "primary"


class TestMountEarlyReturns:
    @pytest.mark.asyncio
    async def test_mount_returns_none_when_no_tiers_configured(self, caplog):
        """mount() returns None and logs warning when config has no tiers."""
        from provider_failover import mount

        coordinator = MockCoordinator()
        config = {}

        with caplog.at_level(logging.WARNING):
            result = await mount(coordinator, config)

        assert result is None
        assert "failover" not in coordinator.mounted

    @pytest.mark.asyncio
    async def test_mount_returns_none_when_no_tiers_resolve(self, caplog):
        """mount() returns None and logs warning when all tier providers are unresolved."""
        from provider_failover import mount

        coordinator = MockCoordinator(providers={})
        config = {
            "tiers": [
                {"provider": "ghost", "model": "ghost-model", "label": "missing"},
            ]
        }

        with caplog.at_level(logging.WARNING):
            result = await mount(coordinator, config)

        assert result is None
        assert "failover" not in coordinator.mounted

    @pytest.mark.asyncio
    async def test_mount_handles_config_none(self, caplog):
        """mount() handles config=None gracefully (treated as no tiers)."""
        from provider_failover import mount

        coordinator = MockCoordinator()
        result = await mount(coordinator, None)
        assert result is None
        assert "failover" not in coordinator.mounted


class TestMountConfigParams:
    @pytest.mark.asyncio
    async def test_mount_passes_probe_interval_to_failover_provider(self):
        """mount() passes probe_interval from config to FailoverProvider."""
        from provider_failover import mount

        provider = MockMountProvider()
        coordinator = MockCoordinator(providers={"anthropic": provider})
        config = {
            "tiers": [{"provider": "anthropic", "model": "claude-opus", "label": "p"}],
            "probe_interval": 10,
        }
        await mount(coordinator, config)

        fp = coordinator.mounted["failover"]
        assert fp._probe_interval == 10

    @pytest.mark.asyncio
    async def test_mount_uses_default_failover_params_when_not_in_config(self):
        """mount() uses FailoverProvider defaults when params not in config."""
        from provider_failover import mount

        provider = MockMountProvider()
        coordinator = MockCoordinator(providers={"anthropic": provider})
        config = {
            "tiers": [{"provider": "anthropic", "model": "claude-opus", "label": "p"}]
        }
        await mount(coordinator, config)

        fp = coordinator.mounted["failover"]
        assert fp._probe_interval == 5


class TestMountContextWindow:
    @pytest.mark.asyncio
    async def test_mount_reads_context_window_from_provider_get_info_defaults(self):
        """mount() reads context_window from provider.get_info().defaults."""
        from provider_failover import mount

        provider = MockMountProvider(context_window=128_000)
        coordinator = MockCoordinator(providers={"openai": provider})
        config = {
            "tiers": [{"provider": "openai", "model": "gpt-4", "label": "primary"}]
        }
        await mount(coordinator, config)

        fp = coordinator.mounted["failover"]
        assert fp._tiers[0].context_window == 128_000

    @pytest.mark.asyncio
    async def test_mount_uses_default_context_window_when_not_in_info(self):
        """mount() uses 200_000 default when provider.get_info().defaults lacks context_window."""
        from provider_failover import mount

        class ProviderNoContextWindow:
            def get_info(self) -> object:
                class Info:
                    def __init__(self) -> None:
                        self.defaults: dict = {}  # no context_window key

                return Info()

        provider = ProviderNoContextWindow()
        coordinator = MockCoordinator(providers={"openai": provider})
        config = {
            "tiers": [{"provider": "openai", "model": "gpt-4", "label": "primary"}]
        }
        await mount(coordinator, config)

        fp = coordinator.mounted["failover"]
        assert fp._tiers[0].context_window == 200_000


class TestMountTierChain:
    @pytest.mark.asyncio
    async def test_mount_builds_multi_tier_chain_in_order(self):
        """mount() builds FailoverProvider with tiers in the order specified."""
        from provider_failover import mount

        p1 = MockMountProvider(context_window=200_000)
        p2 = MockMountProvider(context_window=100_000)
        p3 = MockMountProvider(context_window=50_000)
        coordinator = MockCoordinator(
            providers={"anthropic": p1, "openai": p2, "azure": p3}
        )
        config = {
            "tiers": [
                {"provider": "anthropic", "model": "claude-opus", "label": "tier1"},
                {"provider": "openai", "model": "gpt-4", "label": "tier2"},
                {"provider": "azure", "model": "gpt-35", "label": "tier3"},
            ]
        }
        await mount(coordinator, config)

        fp = coordinator.mounted["failover"]
        assert len(fp._tiers) == 3
        assert fp._tiers[0].label == "tier1"
        assert fp._tiers[1].label == "tier2"
        assert fp._tiers[2].label == "tier3"

    @pytest.mark.asyncio
    async def test_mount_sets_correct_model_per_tier(self):
        """mount() sets the correct model for each tier in the failover chain."""
        from provider_failover import mount

        p1 = MockMountProvider()
        p2 = MockMountProvider()
        coordinator = MockCoordinator(providers={"anthropic": p1, "openai": p2})
        config = {
            "tiers": [
                {"provider": "anthropic", "model": "claude-opus-4", "label": "primary"},
                {"provider": "openai", "model": "gpt-5.4", "label": "fallback"},
            ]
        }
        await mount(coordinator, config)

        fp = coordinator.mounted["failover"]
        assert fp._tiers[0].model == "claude-opus-4"
        assert fp._tiers[1].model == "gpt-5.4"
