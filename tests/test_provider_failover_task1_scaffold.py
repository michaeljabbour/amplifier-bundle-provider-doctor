"""TDD scaffold tests for provider-failover module.

These tests verify the scaffold structure described in the spec:
- FailoverProvider and TierConfig can be imported
- TierConfig has correct fields
- FailoverProvider has correct __init__ signature
- __init__.py has __amplifier_module_type__ = 'provider'
- mount() is callable
"""

import os
import sys

# Add modules/provider-failover to sys.path (mirrors conftest.py)
BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(BUNDLE_ROOT, "modules", "provider-failover")
if MODULE_PATH not in sys.path:
    sys.path.insert(0, MODULE_PATH)


class TestImports:
    def test_can_import_failover_module(self):
        from provider_failover import failover  # noqa: F401

    def test_can_import_tier_config(self):
        from provider_failover.failover import TierConfig  # noqa: F401

    def test_can_import_failover_provider(self):
        from provider_failover.failover import FailoverProvider  # noqa: F401

    def test_init_exports_module_type(self):
        import provider_failover

        assert provider_failover.__amplifier_module_type__ == "provider"

    def test_init_exports_failover_provider(self):
        from provider_failover import FailoverProvider  # noqa: F401

    def test_init_exports_mount(self):
        from provider_failover import mount  # noqa: F401


class TestTierConfig:
    def test_tier_config_is_dataclass(self):
        from provider_failover.failover import TierConfig
        import dataclasses

        assert dataclasses.is_dataclass(TierConfig)

    def test_tier_config_required_fields(self):
        from provider_failover.failover import TierConfig

        # provider, model, label are required
        sentinel = object()
        tc = TierConfig(provider=sentinel, model="gpt-4", label="primary")
        assert tc.provider is sentinel
        assert tc.model == "gpt-4"
        assert tc.label == "primary"

    def test_tier_config_default_context_window(self):
        from provider_failover.failover import TierConfig

        tc = TierConfig(provider=object(), model="m", label="l")
        assert tc.context_window == 200_000

    def test_tier_config_custom_context_window(self):
        from provider_failover.failover import TierConfig

        tc = TierConfig(provider=object(), model="m", label="l", context_window=8192)
        assert tc.context_window == 8192


class TestFailoverProvider:
    def test_failover_provider_init_defaults(self):
        from provider_failover.failover import FailoverProvider, TierConfig

        tiers = [TierConfig(provider=object(), model="m", label="l")]
        fp = FailoverProvider(tiers=tiers)
        assert fp._tiers is tiers
        assert fp._current_tier_idx == 0
        assert fp._probe_interval == 5
        assert fp._success_count == 0

    def test_failover_provider_custom_params(self):
        from provider_failover.failover import FailoverProvider, TierConfig

        tiers = [TierConfig(provider=object(), model="m", label="l")]
        fp = FailoverProvider(tiers=tiers, probe_interval=10)
        assert fp._probe_interval == 10

    def test_failover_provider_no_retry_params(self):
        """FailoverProvider must NOT accept max_failures or retry_base_delay.

        Provider-level retry is handled internally. These params were removed
        to prevent retry amplification.
        """
        from provider_failover.failover import FailoverProvider, TierConfig
        import inspect

        sig = inspect.signature(FailoverProvider.__init__)
        param_names = set(sig.parameters.keys())
        assert "max_failures" not in param_names, (
            "max_failures removed — provider handles retry"
        )
        assert "retry_base_delay" not in param_names, (
            "retry_base_delay removed — provider handles retry"
        )
