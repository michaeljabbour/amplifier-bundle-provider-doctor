"""Stream proxy tests for FailoverProvider.

Each tier gets ONE attempt — no per-tier retry.

Tests in TestStreamProxy:
- test_stream_happy_path: stream() delegates to tier's stream(), yields chunks, len(chunks)==1
- test_stream_falls_to_next_tier_on_failure: ProviderUnavailableError on tier1 ->
  tier2 stream succeeds, fp.name=='failover(sonnet)'
"""

from __future__ import annotations

import pytest

from conftest import MockRequest, _make_failover, _make_response, _make_tier
from provider_failover.errors import ProviderUnavailableError


# ---------------------------------------------------------------------------
# Stream proxy tests
# ---------------------------------------------------------------------------


class TestStreamProxy:
    @pytest.mark.asyncio
    async def test_stream_happy_path(self):
        """stream() delegates to tier's stream(), yields chunks, len(chunks)==1.

        A single successful response is wrapped as a dict by _make_response().
        MockProvider.stream() yields dicts as a single chunk (dicts are excluded
        from the iterable-split path). fp.stream() must return an async iterable
        and yield exactly that one chunk.
        """
        response = _make_response("hello")
        tier, mock = _make_tier(
            "primary",
            [response],
            model="claude-sonnet",
            label="primary",
        )
        fp = _make_failover([tier])

        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )

        chunks = [chunk async for chunk in fp.stream(request)]

        assert len(chunks) == 1
        assert chunks[0] == response

    @pytest.mark.asyncio
    async def test_stream_falls_to_next_tier_on_failure(self):
        """ProviderUnavailableError on tier1 -> tier2 stream succeeds.

        p1 call_count==1 (no retry), p2 call_count==1, fp.name=='failover(sonnet)'.
        """
        response = _make_response("tier2 stream success")
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

        chunks = [chunk async for chunk in fp.stream(request)]

        assert len(chunks) == 1
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1
        assert fp.name == "failover(sonnet)"
