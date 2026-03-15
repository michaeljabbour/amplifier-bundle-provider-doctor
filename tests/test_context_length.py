"""ContextLengthError special-handling tests for FailoverProvider.

Tests in TestContextLengthFallback:
- test_falls_to_tier_with_larger_context_window: 200K -> ContextLengthError -> 1M tier succeeds
- test_raises_if_no_larger_context_available: 200K -> ContextLengthError, next tier also 200K -> raises
- test_raises_if_last_tier: single tier -> ContextLengthError -> raises with actionable message
- test_skips_tier_with_same_context_window: 200K fails, 200K tier skipped, 1M tier succeeds
"""

from __future__ import annotations

import pytest

from conftest import MockRequest, _make_failover, _make_response, _make_tier
from provider_failover.errors import ContextLengthError


# ---------------------------------------------------------------------------
# ContextLengthError fallback tests
# ---------------------------------------------------------------------------


class TestContextLengthFallback:
    @pytest.mark.asyncio
    async def test_falls_to_tier_with_larger_context_window(self):
        """tier1 200K -> ContextLengthError -> tier2 1M succeeds.

        p1 call_count==1, p2 call_count==1.
        """
        response = _make_response("tier2 success")
        tier1, p1 = _make_tier(
            "small",
            [ContextLengthError("context exceeded")],
            model="small-model",
            label="small",
            context_window=200_000,
        )
        tier2, p2 = _make_tier(
            "large",
            [response],
            model="large-model",
            label="large",
            context_window=1_000_000,
        )
        fp = _make_failover([tier1, tier2])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = await fp.complete(request)

        assert result == response
        assert len(p1.calls) == 1, "ContextLengthError must not retry within the tier"
        assert len(p2.calls) == 1

    @pytest.mark.asyncio
    async def test_raises_if_no_larger_context_available(self):
        """tier1 200K -> ContextLengthError, tier2 200K same size -> raises ContextLengthError.

        The error message should mention 'Start a new session'.
        """
        tier1, p1 = _make_tier(
            "tier1",
            [ContextLengthError("context exceeded")],
            context_window=200_000,
        )
        tier2, p2 = _make_tier(
            "tier2",
            [_make_response("should not reach")],
            context_window=200_000,
        )
        fp = _make_failover([tier1, tier2])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        with pytest.raises(ContextLengthError, match="Start a new session"):
            await fp.complete(request)

    @pytest.mark.asyncio
    async def test_raises_if_last_tier(self):
        """Single tier -> ContextLengthError -> raises with 'Start a new session' message."""
        tier1, p1 = _make_tier(
            "only-tier",
            [ContextLengthError("context exceeded")],
            context_window=200_000,
        )
        fp = _make_failover([tier1])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        with pytest.raises(ContextLengthError, match="Start a new session"):
            await fp.complete(request)

    @pytest.mark.asyncio
    async def test_skips_tier_with_same_context_window(self):
        """tier1 200K fails, tier2 200K is skipped (p2._call_count==0), tier3 1M succeeds."""
        response = _make_response("tier3 success")
        tier1, p1 = _make_tier(
            "tier1",
            [ContextLengthError("context exceeded")],
            context_window=200_000,
        )
        tier2, p2 = _make_tier(
            "tier2",
            [_make_response("should not reach")],
            context_window=200_000,
        )
        tier3, p3 = _make_tier(
            "tier3",
            [response],
            context_window=1_000_000,
        )
        fp = _make_failover([tier1, tier2, tier3])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = await fp.complete(request)

        assert result == response
        assert len(p1.calls) == 1
        assert len(p2.calls) == 0, "Tier with same context window must be skipped"
        assert len(p3.calls) == 1
