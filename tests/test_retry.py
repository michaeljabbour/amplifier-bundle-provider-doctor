"""Failover behavior tests for FailoverProvider — no retry at this layer.

Provider-level retry is handled by each provider internally via
retry_with_backoff().  This module tests that errors cause immediate
failover to the next tier (no per-tier retry, no backoff at this layer).

Tests:
- test_single_successful_call: complete() returns provider's response, call_count==1
- test_model_override_in_request: tier's model overrides request model via model_copy
- test_name_reflects_active_tier: fp.name == 'failover(opus)'
- TestImmediateFailover: any error falls to next tier immediately (no retry)
- TestNonRetryableErrors: auth/content errors fall to next tier on single-tier raise
"""

from __future__ import annotations

import pytest

from conftest import MockRequest, _make_failover, _make_response, _make_tier
from provider_failover.errors import (
    AuthenticationError,
    ContentFilterError,
    LLMError,
    ProviderUnavailableError,
    RateLimitError,
)


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_single_successful_call(self):
        """complete() returns the provider's response and call_count is 1."""
        response = _make_response("hello world")
        tier, mock = _make_tier("primary", [response], model="opus")
        fp = _make_failover([tier])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = await fp.complete(request)

        assert result == response
        assert len(mock.calls) == 1

    @pytest.mark.asyncio
    async def test_model_override_in_request(self):
        """Tier's model is substituted into the request via model_copy()."""
        response = _make_response("hi")
        tier, mock = _make_tier("primary", [response], model="opus")
        fp = _make_failover([tier])

        request = MockRequest(
            model="original-model",
            messages=[{"role": "user", "content": "Hi"}],
        )
        await fp.complete(request)

        # The provider received a request with the tier's model, not original
        received_request = mock.calls[0]["request"]
        assert received_request.model == "opus"
        # Original request is unchanged (immutable copy semantics)
        assert request.model == "original-model"

    def test_name_reflects_active_tier(self):
        """fp.name == 'failover(opus)' when the active tier has label 'opus'."""
        tier, _ = _make_tier(
            "opus", [_make_response("response")], model="claude-opus", label="opus"
        )
        fp = _make_failover([tier])

        assert fp.name == "failover(opus)"


# ---------------------------------------------------------------------------
# Immediate failover tests (no retry at this layer)
# ---------------------------------------------------------------------------


class TestImmediateFailover:
    """Verify that ANY error causes immediate failover — no retry loop."""

    @pytest.mark.asyncio
    async def test_retryable_error_falls_immediately_to_next_tier(self):
        """ProviderUnavailableError (retryable=True) falls to next tier immediately.

        Provider already exhausted its own retry budget. No retry here.
        p1 call_count==1, p2 call_count==1.
        """
        response = _make_response("tier2 success")
        tier1, p1 = _make_tier(
            "primary",
            [ProviderUnavailableError(retryable=True)],
        )
        tier2, p2 = _make_tier(
            "fallback",
            [response],
        )
        fp = _make_failover([tier1, tier2])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = await fp.complete(request)

        assert result == response
        assert len(p1.calls) == 1, "No retry — provider already retried internally"
        assert len(p2.calls) == 1

    @pytest.mark.asyncio
    async def test_rate_limit_falls_immediately_to_next_tier(self):
        """RateLimitError (retryable=True) falls to next tier immediately.

        p1 call_count==1, p2 call_count==1.
        """
        response = _make_response("tier2 success")
        tier1, p1 = _make_tier(
            "primary",
            [RateLimitError(retryable=True)],
        )
        tier2, p2 = _make_tier(
            "fallback",
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
    async def test_generic_llm_error_falls_immediately(self):
        """Generic LLMError falls to next tier immediately."""
        response = _make_response("tier2 success")
        tier1, p1 = _make_tier(
            "primary",
            [LLMError("generic failure", retryable=True)],
        )
        tier2, p2 = _make_tier(
            "fallback",
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
    async def test_single_tier_retryable_error_raises(self):
        """Single tier: retryable error raises immediately (no retry)."""
        tier, mock = _make_tier(
            "only",
            [ProviderUnavailableError("overloaded", retryable=True)],
        )
        fp = _make_failover([tier])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        with pytest.raises(ProviderUnavailableError):
            await fp.complete(request)

        assert len(mock.calls) == 1


# ---------------------------------------------------------------------------
# Non-retryable error tests
# ---------------------------------------------------------------------------


class TestNonRetryableErrors:
    @pytest.mark.asyncio
    async def test_auth_error_raises_on_single_tier(self):
        """AuthenticationError is raised immediately on single tier; call_count==1."""
        tier, mock = _make_tier("primary", [AuthenticationError()])
        fp = _make_failover([tier])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        with pytest.raises(AuthenticationError):
            await fp.complete(request)

        assert len(mock.calls) == 1

    @pytest.mark.asyncio
    async def test_content_filter_raises_on_single_tier(self):
        """ContentFilterError is raised immediately on single tier; call_count==1."""
        tier, mock = _make_tier("primary", [ContentFilterError()])
        fp = _make_failover([tier])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        with pytest.raises(ContentFilterError):
            await fp.complete(request)

        assert len(mock.calls) == 1

    @pytest.mark.asyncio
    async def test_auth_error_falls_to_next_tier(self):
        """AuthenticationError on tier1 -> immediate fall to tier2."""
        response = _make_response("tier2 success")
        tier1, p1 = _make_tier("tier1", [AuthenticationError()])
        tier2, p2 = _make_tier("tier2", [response])
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
    async def test_content_filter_falls_to_next_tier(self):
        """ContentFilterError on tier1 -> immediate fall to tier2."""
        response = _make_response("tier2 success")
        tier1, p1 = _make_tier("tier1", [ContentFilterError()])
        tier2, p2 = _make_tier("tier2", [response])
        fp = _make_failover([tier1, tier2])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = await fp.complete(request)

        assert result == response
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1
