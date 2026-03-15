"""Provider failover core implementation.

Defines TierConfig and FailoverProvider for tier-based LLM provider failover.

Provider-level retry (transient errors, rate limits, backoff, jitter) is handled
by each provider internally via retry_with_backoff().  This module adds value
through FAILOVER — routing requests to a different model/provider when the
current one fails — not through redundant retry that would cause amplification.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from provider_failover.errors import (
    AuthenticationError,
    ContentFilterError,
    ContextLengthError,
    LLMError,
)
from provider_failover.telemetry import report_error

logger = logging.getLogger(__name__)


@dataclass
class TierConfig:
    """Configuration for a single provider tier in the failover chain.

    Attributes:
        provider: The provider instance to use for this tier.
        model: The model identifier to use with this provider.
        label: Human-readable label for this tier (e.g., "primary", "fallback").
        context_window: Maximum context window size in tokens (default 200_000).
    """

    provider: Any
    model: str
    label: str
    context_window: int = 200_000


def _provider_name(provider: Any) -> str:
    """Extract a human-readable provider name, safely."""
    if hasattr(provider, "name"):
        return str(provider.name)
    return type(provider).__name__


class FailoverProvider:
    """Tier-based LLM provider failover manager.

    Routes requests through a priority-ordered chain of provider tiers.
    When a tier fails, the request immediately falls to the next tier.
    After sustained success on a fallback tier, periodic probing checks
    whether a higher tier has recovered.

    **No retry at this layer.**  Each provider already wraps its API calls
    in ``retry_with_backoff()`` (3 retries with exponential backoff, jitter,
    and ``retry_after`` header support).  By the time an ``LLMError`` reaches
    this module, the provider has already exhausted its retry budget.  Adding
    retries here would cause amplification — each failover-level retry would
    trigger a fresh round of provider-level retries.
    """

    def __init__(
        self,
        tiers: list[TierConfig],
        probe_interval: int = 5,
    ) -> None:
        """Initialize the FailoverProvider.

        Args:
            tiers: Ordered list of provider tiers to try in sequence.
            probe_interval: Number of successes on a fallback tier before
                probing the primary again.
        """
        self._tiers = tiers
        self._current_tier_idx: int = 0
        self._probe_interval: int = probe_interval
        self._success_count: int = 0
        self.priority: int = 1  # Ensure orchestrator picks failover over raw providers

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def _current_tier(self) -> TierConfig:
        """Return the currently active tier."""
        return self._tiers[self._current_tier_idx]

    @property
    def name(self) -> str:
        """Human-readable name reflecting the active tier label."""
        return f"failover({self._current_tier.label})"

    # ------------------------------------------------------------------
    # Provider interface delegation
    # ------------------------------------------------------------------

    def get_info(self) -> dict[str, Any]:
        """Delegate get_info() to the active tier's provider."""
        return self._current_tier.provider.get_info()

    def parse_tool_calls(self, response: Any) -> list[dict[str, Any]]:
        """Delegate parse_tool_calls() to the active tier's provider."""
        return self._current_tier.provider.parse_tool_calls(response)

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    async def complete(self, request: Any, **kwargs: Any) -> Any:
        """Run a completion request through the active tier.

        Args:
            request: The completion request (must support model_copy()).
            **kwargs: Additional keyword arguments forwarded to the provider.

        Returns:
            The provider's completion response.
        """
        return await self._call_with_failover("complete", request, **kwargs)

    def stream(self, request: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        """Run a streaming request through the active tier.

        Returns an async generator that yields chunks from the provider.
        This is a regular (non-async) method; callers iterate the result
        with ``async for chunk in fp.stream(request)``.

        Args:
            request: The completion request (must support model_copy()).
            **kwargs: Additional keyword arguments forwarded to the provider.

        Returns:
            An async generator that yields response chunks.
        """
        return self._stream_with_failover(request, **kwargs)

    # ------------------------------------------------------------------
    # Telemetry helper
    # ------------------------------------------------------------------

    def _fire_telemetry(
        self,
        exc: BaseException,
        tier: TierConfig,
        tier_idx: int,
        *,
        has_streaming: bool,
    ) -> None:
        """Schedule a fire-and-forget telemetry report for a provider error.

        Uses asyncio.ensure_future so the caller is never blocked or affected
        if telemetry fails.
        """
        failover_from = (
            self._tiers[self._current_tier_idx].label
            if tier_idx != self._current_tier_idx
            else None
        )
        failover_to = (
            self._tiers[tier_idx + 1].label
            if tier_idx + 1 < len(self._tiers)
            else None
        )
        try:
            asyncio.ensure_future(
                report_error(
                    provider=_provider_name(tier.provider),
                    model=tier.model,
                    tier_label=tier.label,
                    tier_index=tier_idx,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:500],
                    status_code=getattr(exc, "status_code", None),
                    retryable=getattr(exc, "retryable", None),
                    has_streaming=has_streaming,
                    failover_from=failover_from,
                    failover_to=failover_to,
                    tiers_tried=tier_idx + 1,
                )
            )
        except Exception:
            pass  # No running event loop, or other edge case — silently skip

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _invoke(self, method: str, provider: Any, request: Any) -> Any:
        """Invoke a provider method, transparently handling sync and async.

        Args:
            method: Name of the provider method to call.
            provider: The provider instance.
            request: The (possibly modified) request object.

        Returns:
            The provider's response.
        """
        fn = getattr(provider, method)
        result = fn(request)
        if inspect.isawaitable(result):
            return await result
        return result

    def _log_usage(self, tier: TierConfig, result: Any) -> None:
        """Log input token usage for a completed request.

        Args:
            tier: The tier that produced the result.
            result: The provider response (dict with optional 'usage' key).
        """
        try:
            input_tokens = result.get("usage", {}).get("input_tokens", 0)
        except (AttributeError, TypeError):
            input_tokens = 0
        logger.debug("tier=%s input_tokens=%d", tier.label, input_tokens)

    def _find_larger_context_tier(self, current_idx: int) -> int | None:
        """Return the index of the first tier after current_idx with a strictly larger context window.

        Args:
            current_idx: Index of the current tier in ``self._tiers``.

        Returns:
            The index of the first subsequent tier whose ``context_window`` is
            strictly greater than that of the current tier, or ``None`` if no
            such tier exists.
        """
        current_window = self._tiers[current_idx].context_window
        for idx in range(current_idx + 1, len(self._tiers)):
            if self._tiers[idx].context_window > current_window:
                return idx
        return None

    async def _probe_up(self, method: str, request: Any, **kwargs: Any) -> Any | None:
        """Probe the tier above the current one to check if it has recovered.

        Called when ``_success_count >= _probe_interval`` and we are on a
        lower tier (``_current_tier_idx > 0``).  On success the provider
        moves back up; on failure the success counter is reset and the
        caller continues on the current tier.

        Args:
            method: Provider method name to call (e.g. ``'complete'``).
            request: The request object (must support ``model_copy()``).
            **kwargs: Ignored (reserved for future use).

        Returns:
            The provider's response if the probe succeeds, otherwise ``None``.
        """
        probe_idx = self._current_tier_idx - 1
        tier = self._tiers[probe_idx]
        modified_request = request.model_copy(update={"model": tier.model})
        try:
            result = await self._invoke(method, tier.provider, modified_request)
            self._log_usage(tier, result)
            self._current_tier_idx = probe_idx
            self._success_count = 0
            return result
        except Exception:
            self._success_count = 0
            return None

    async def _call_with_failover(
        self, method: str, request: Any, **kwargs: Any
    ) -> Any:
        """Execute a provider call with tier failover (no per-tier retry).

        Each tier gets ONE attempt.  Provider-level retry has already been
        exhausted by the time an error reaches this layer — retrying here
        would cause retry amplification.

        Probe-up check: if we are on a lower tier and the success counter has
        reached ``probe_interval``, we first attempt ``_probe_up()``.  A
        successful probe moves the provider back to the higher tier and returns
        immediately; a failed probe resets the counter and falls through to the
        normal call on the current tier.

        Error handling:
        - ``ContextLengthError``: jump to a tier with a strictly larger
          context window, or raise if none exists.
        - ``AuthenticationError`` / ``ContentFilterError``: fall to next tier.
        - Any other ``LLMError``: fall to next tier.

        Args:
            method: Provider method name to call (e.g. ``'complete'``).
            request: The request object (must support ``model_copy()``).
            **kwargs: Ignored (reserved for future use).

        Returns:
            The provider's response from whichever tier succeeds.

        Raises:
            The last ``LLMError`` (or subclass) encountered when all tiers
            are exhausted without a successful response.
        """
        # Probe-up: try moving back to a higher tier after enough successes.
        if self._current_tier_idx > 0 and self._success_count >= self._probe_interval:
            probe_result = await self._probe_up(method, request, **kwargs)
            if probe_result is not None:
                return probe_result
            # Probe failed: counter reset, continue on current tier.

        last_error: BaseException | None = None
        tier_idx = self._current_tier_idx  # start from active tier (post-failover)

        while tier_idx < len(self._tiers):
            tier = self._tiers[tier_idx]
            modified_request = request.model_copy(update={"model": tier.model})

            try:
                result = await self._invoke(method, tier.provider, modified_request)
                self._log_usage(tier, result)
                self._current_tier_idx = (
                    tier_idx  # track active tier for name/get_info/parse_tool_calls
                )
                # Increment success counter only when on a lower (fallback) tier.
                if self._current_tier_idx > 0:
                    self._success_count += 1
                return result
            except ContextLengthError as exc:
                last_error = exc
                self._fire_telemetry(exc, tier, tier_idx, has_streaming=False)
                larger_idx = self._find_larger_context_tier(tier_idx)
                if larger_idx is not None:
                    tier_idx = larger_idx
                    continue
                else:
                    raise ContextLengthError(
                        "Context window exceeded on all available tiers. "
                        "Start a new session with a shorter context."
                    )
            except (AuthenticationError, ContentFilterError) as exc:
                last_error = exc
                self._fire_telemetry(exc, tier, tier_idx, has_streaming=False)
            except LLMError as exc:
                last_error = exc
                self._fire_telemetry(exc, tier, tier_idx, has_streaming=False)

            tier_idx += 1

        if last_error is not None:
            raise last_error
        raise RuntimeError("No tiers available")

    async def _stream_with_failover(
        self, request: Any, **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        """Execute a streaming provider call with tier failover (no per-tier retry).

        Each tier gets ONE attempt.  Provider-level retry has already been
        exhausted by the time an error reaches this layer.

        Probe-up check: if we are on a lower tier and the success counter has
        reached ``probe_interval``, we probe the tier above.  On a successful
        probe the provider moves back up and the probe's chunks are yielded;
        on failure the counter is reset and the call continues on the current tier.

        Error handling per tier follows the same rules as ``_call_with_failover``:
        - ``AuthenticationError`` / ``ContentFilterError``: advance to next tier.
        - Any other ``LLMError``: advance to next tier.

        Args:
            request: The request object (must support ``model_copy()``).
            **kwargs: Ignored (reserved for future use).

        Yields:
            Response chunks from whichever tier succeeds.

        Raises:
            The last ``LLMError`` (or subclass) encountered when all tiers are
            exhausted without a successful response.
        """
        # Probe-up: try moving back to a higher tier after enough successes.
        if self._current_tier_idx > 0 and self._success_count >= self._probe_interval:
            probe_idx = self._current_tier_idx - 1
            probe_tier = self._tiers[probe_idx]
            probe_request = request.model_copy(update={"model": probe_tier.model})
            probe_chunks: list[Any] = []
            try:
                async for chunk in probe_tier.provider.stream(probe_request):
                    probe_chunks.append(chunk)
            except Exception:
                self._success_count = 0
            else:
                self._current_tier_idx = probe_idx
                self._success_count = 0
                for chunk in probe_chunks:
                    yield chunk
                return
            # Probe failed: counter reset above, fall through to current tier.

        last_error: BaseException | None = None
        tier_idx = self._current_tier_idx  # start from active tier (post-failover)

        while tier_idx < len(self._tiers):
            tier = self._tiers[tier_idx]
            modified_request = request.model_copy(update={"model": tier.model})

            try:
                stream_iter = tier.provider.stream(modified_request)
                async for chunk in stream_iter:
                    yield chunk
                # Successful stream completed.
                self._current_tier_idx = tier_idx
                # Increment success counter only when on a lower (fallback) tier.
                if self._current_tier_idx > 0:
                    self._success_count += 1
                return
            except (AuthenticationError, ContentFilterError) as exc:
                last_error = exc
                self._fire_telemetry(exc, tier, tier_idx, has_streaming=True)
            except LLMError as exc:
                last_error = exc
                self._fire_telemetry(exc, tier, tier_idx, has_streaming=True)

            tier_idx += 1

        if last_error is not None:
            raise last_error
        raise RuntimeError("No tiers available")
