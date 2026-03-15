"""Multi-tier fallback tests for FailoverProvider.

Each tier gets ONE attempt — no per-tier retry (provider handles that internally).

Tests in TestMultiTierFallback:
- test_fall_to_tier2_after_tier1_fails: tier1 fails -> tier2 success (1 call each)
- test_fall_through_all_three_tiers: tier1 fail -> tier2 fail -> tier3 success
- test_all_tiers_exhausted_raises_last_error: all tiers fail, raises last error
- test_nonretryable_falls_to_next_tier: AuthenticationError skips to next tier immediately
- test_each_tier_gets_its_own_model: each tier uses its own model in the request
"""

from __future__ import annotations

import pytest

from conftest import MockRequest, _make_failover, _make_response, _make_tier
from provider_failover.errors import (
    AuthenticationError,
    ProviderUnavailableError,
    RateLimitError,
)


# ---------------------------------------------------------------------------
# Multi-tier fallback tests
# ---------------------------------------------------------------------------


class TestMultiTierFallback:
    @pytest.mark.asyncio
    async def test_fall_to_tier2_after_tier1_fails(self):
        """ProviderUnavailableError on tier1 -> tier2 succeeds.

        p1 call_count==1, p2 call_count==1, fp.name=='failover(sonnet)'.
        """
        response = _make_response("tier2 success")
        tier1, p1 = _make_tier(
            "opus",
            [ProviderUnavailableError(retryable=True)],
            model="claude-opus",
            label="opus",
        )
        tier2, p2 = _make_tier(
            "sonnet",
            [response],
            model="claude-sonnet",
            label="sonnet",
        )
        fp = _make_failover([tier1, tier2])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = await fp.complete(request)

        assert result == response
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1
        assert fp.name == "failover(sonnet)"

    @pytest.mark.asyncio
    async def test_fall_through_all_three_tiers(self):
        """tier1 fail -> tier2 fail -> tier3 success.

        fp.name == 'failover(openai)' after settling on tier3.
        Each tier gets exactly 1 call.
        """
        response = _make_response("tier3 success")
        tier1, p1 = _make_tier(
            "anthropic",
            [ProviderUnavailableError(retryable=True)],
            model="claude-opus",
            label="anthropic",
        )
        tier2, p2 = _make_tier(
            "azure",
            [ProviderUnavailableError(retryable=True)],
            model="gpt-4",
            label="azure",
        )
        tier3, p3 = _make_tier(
            "openai",
            [response],
            model="gpt-4-turbo",
            label="openai",
        )
        fp = _make_failover([tier1, tier2, tier3])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = await fp.complete(request)

        assert result == response
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1
        assert len(p3.calls) == 1
        assert fp.name == "failover(openai)"

    @pytest.mark.asyncio
    async def test_all_tiers_exhausted_raises_last_error(self):
        """All tiers fail; the last RateLimitError is re-raised."""
        last_error = RateLimitError("tier2 final failure", retryable=True)
        tier1, _ = _make_tier(
            "tier1",
            [ProviderUnavailableError(retryable=True)],
        )
        tier2, _ = _make_tier(
            "tier2",
            [last_error],
        )
        fp = _make_failover([tier1, tier2])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        with pytest.raises(RateLimitError) as exc_info:
            await fp.complete(request)

        assert exc_info.value is last_error

    @pytest.mark.asyncio
    async def test_nonretryable_falls_to_next_tier(self):
        """AuthenticationError on tier1 -> immediate fallover to tier2.

        p1 call_count==1 (non-retryable error falls immediately).
        """
        response = _make_response("tier2 success")
        tier1, p1 = _make_tier(
            "tier1",
            [AuthenticationError()],
        )
        tier2, p2 = _make_tier(
            "tier2",
            [response],
        )
        fp = _make_failover([tier1, tier2])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = await fp.complete(request)

        assert result == response
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1

    @pytest.mark.asyncio
    async def test_each_tier_gets_its_own_model(self):
        """Each tier substitutes its own model into the request via model_copy().

        tier1 model='claude-opus-4-6' fails -> tier2 model='claude-sonnet-4-5' succeeds.
        p1 received 'claude-opus-4-6', p2 received 'claude-sonnet-4-5'.
        """
        response = _make_response("tier2 success")
        tier1, p1 = _make_tier(
            "opus",
            [ProviderUnavailableError(retryable=True)],
            model="claude-opus-4-6",
            label="opus",
        )
        tier2, p2 = _make_tier(
            "sonnet",
            [response],
            model="claude-sonnet-4-5",
            label="sonnet",
        )
        fp = _make_failover([tier1, tier2])

        request = MockRequest(
            model="original-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        await fp.complete(request)

        # Each provider received a request stamped with its tier's model
        p1_last_request = p1.calls[-1]["request"]
        p2_last_request = p2.calls[-1]["request"]
        assert p1_last_request.model == "claude-opus-4-6"
        assert p2_last_request.model == "claude-sonnet-4-5"
        # Original request is unchanged (immutable copy semantics)
        assert request.model == "original-model"
