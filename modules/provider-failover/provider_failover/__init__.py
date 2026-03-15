"""Amplifier Provider Module: Tier-based LLM Provider Failover.

Automatically fails over across LLM provider tiers when errors are encountered.
Each provider handles its own retry logic internally via retry_with_backoff().
This module adds value through FAILOVER to different models/providers, not
through redundant retry that would cause amplification.

Usage in behavior.yaml:
    providers:
      - module: provider-failover
        config:
          tiers:
            - provider: anthropic
              model: claude-opus-4
              label: primary
            - provider: anthropic
              model: claude-sonnet-4-5
              label: secondary
            - provider: openai
              model: gpt-5.4
              label: fallback
"""

from __future__ import annotations

import logging
from typing import Any

from provider_failover.failover import FailoverProvider, TierConfig

__all__ = ["mount", "FailoverProvider"]
__amplifier_module_type__ = "provider"

logger = logging.getLogger(__name__)

_DEFAULT_CONTEXT_WINDOW = 200_000


def _resolve_context_window(provider: Any) -> int:
    """Extract context_window from provider.get_info().defaults.

    Attempts attribute access (get_info().defaults["context_window"]) first,
    then falls back to dict access, then to _DEFAULT_CONTEXT_WINDOW.

    Args:
        provider: A resolved provider instance with a get_info() method.

    Returns:
        The context window size in tokens, or _DEFAULT_CONTEXT_WINDOW if not found.
    """
    try:
        info = provider.get_info()
    except Exception:
        return _DEFAULT_CONTEXT_WINDOW
    try:
        return info.defaults.get("context_window", _DEFAULT_CONTEXT_WINDOW)
    except AttributeError:
        pass
    try:
        return info.get("defaults", {}).get("context_window", _DEFAULT_CONTEXT_WINDOW)
    except (AttributeError, TypeError):
        pass
    return _DEFAULT_CONTEXT_WINDOW


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the provider failover module.

    Called by Amplifier kernel during session initialization. Resolves real
    provider instances from the coordinator, builds a TierConfig chain, and
    constructs a FailoverProvider that is registered back with the coordinator.

    Args:
        coordinator: The Amplifier ModuleCoordinator, providing get() and mount()
            methods for accessing and registering providers.
        config: Module configuration dict with optional keys:
            - tiers (list[dict]): Ordered list of tier specs, each with:
                - provider (str): Provider name (may include 'provider-' prefix).
                - model (str): Model identifier for this tier.
                - label (str): Human-readable label (e.g. 'primary', 'fallback').
            - probe_interval (int): Successes on a lower tier before probing the
              primary again (default 5).

    Returns:
        None — no cleanup is needed for this module.
    """
    if config is None:
        config = {}

    tier_specs: list[dict[str, Any]] = config.get("tiers", [])
    probe_interval: int = config.get("probe_interval", 5)

    if not tier_specs:
        logger.warning("provider-failover: no tiers configured — skipping mount")
        return None

    providers_dict: dict[str, Any] = coordinator.get("providers") or {}
    resolved_tiers: list[TierConfig] = []

    for tier_spec in tier_specs:
        provider_name: str = tier_spec.get("provider", "")

        if not provider_name:
            logger.warning(
                "provider-failover: tier is missing required 'provider' key — skipping tier"
            )
            continue

        # Derive the lookup key by stripping the 'provider-' module prefix if present.
        mount_name = provider_name.removeprefix("provider-")

        provider = providers_dict.get(mount_name)
        if provider is None:
            logger.warning(
                "provider-failover: provider %r (key=%r) not found in coordinator"
                " — skipping tier",
                provider_name,
                mount_name,
            )
            continue

        context_window = _resolve_context_window(provider)
        tier = TierConfig(
            provider=provider,
            model=tier_spec.get("model", ""),
            label=tier_spec.get("label", provider_name),
            context_window=context_window,
        )
        resolved_tiers.append(tier)

    if not resolved_tiers:
        logger.warning(
            "provider-failover: no tiers resolved from coordinator — skipping mount"
        )
        return None

    failover = FailoverProvider(
        tiers=resolved_tiers,
        probe_interval=probe_interval,
    )

    coordinator.mount("providers", failover, name="failover")

    chain = " -> ".join(
        f"{t.label}({t.model})[ctx={t.context_window}]" for t in resolved_tiers
    )
    logger.info("provider-failover: mounted tier chain: %s", chain)

    return None
