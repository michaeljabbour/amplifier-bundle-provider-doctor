"""Fail-up probing tests for FailoverProvider.

Tests in TestFailUpProbing:
- test_probe_after_n_successes: fall to tier2, 5 successes on tier2, 6th call probes
  tier1 which succeeds -> back on tier1
- test_failed_probe_stays_on_current_tier: probe fires but tier1 still failing ->
  stays on tier2, _success_count reset to 0
- test_probe_resets_success_counter_on_success: after successful probe, _success_count==0
- test_no_probe_when_already_on_tier1: _success_count stays 0, no probe
"""

from __future__ import annotations

import pytest

from conftest import MockRequest, _make_failover, _make_response, _make_tier
from provider_failover.errors import ProviderUnavailableError


# ---------------------------------------------------------------------------
# Fail-up probing tests
# ---------------------------------------------------------------------------


class TestFailUpProbing:
    @pytest.mark.asyncio
    async def test_probe_after_n_successes(self):
        """Fall to tier2, 5 successes, 6th call probes tier1 which succeeds -> back on tier1.

        After probe_interval (5) successes on tier2, the next call probes tier1.
        Successful probe restores _current_tier_idx to 0 and fp.name to 'failover(tier1)'.
        p1 call_count == 2 (1 failover + 1 probe), p2 call_count == 5.
        """
        tier1_response = _make_response("tier1 success")
        tier2_response = _make_response("tier2 success")

        # tier1: 1 failure to trigger failover, then 1 success for the probe
        tier1, p1 = _make_tier(
            "tier1",
            [
                ProviderUnavailableError(retryable=True),
                tier1_response,  # succeeds on probe
            ],
            model="tier1-model",
            label="tier1",
        )
        # tier2: always succeeds (last response reused when exhausted)
        tier2, p2 = _make_tier(
            "tier2",
            [tier2_response],
            model="tier2-model",
            label="tier2",
        )

        fp = _make_failover([tier1, tier2], probe_interval=5)
        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Call 1: tier1 fails (1 call), falls over to tier2 (success #1)
        await fp.complete(request)
        assert fp._current_tier_idx == 1
        assert fp._success_count == 1

        # Calls 2-5: 4 more successes on tier2 (_success_count -> 5)
        for _ in range(4):
            await fp.complete(request)
        assert fp._success_count == 5

        # Call 6: probe fires (_success_count==5 >= probe_interval==5),
        # tier1 succeeds -> back on tier1
        result = await fp.complete(request)

        assert result == tier1_response
        assert fp._current_tier_idx == 0
        assert fp._success_count == 0
        assert fp.name == "failover(tier1)"
        assert len(p1.calls) == 2  # 1 failover attempt + 1 probe
        assert len(p2.calls) == 5  # calls 1 through 5

    @pytest.mark.asyncio
    async def test_failed_probe_stays_on_current_tier(self):
        """Probe fires but tier1 still failing -> stays on tier2, counter reset.

        After probe failure, _success_count resets to 0. The call then succeeds
        on the current tier (tier2), so final _success_count == 1 (not 5 or 0).
        fp.name remains 'failover(tier2)'.
        """
        tier2_response = _make_response("tier2 success")

        # tier1 always fails (probe will fail)
        tier1, p1 = _make_tier(
            "tier1",
            [ProviderUnavailableError(retryable=True)],
            model="tier1-model",
            label="tier1",
        )
        # tier2 always succeeds
        tier2, p2 = _make_tier(
            "tier2",
            [tier2_response],
            model="tier2-model",
            label="tier2",
        )

        fp = _make_failover([tier1, tier2], probe_interval=5)
        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Set up state: currently on tier2 with 5 successes (probe_interval reached)
        fp._current_tier_idx = 1
        fp._success_count = 5

        # This call should: probe tier1 (fails) -> reset counter -> succeed on tier2
        result = await fp.complete(request)

        assert result == tier2_response
        assert fp._current_tier_idx == 1  # still on tier2
        assert fp.name == "failover(tier2)"
        # counter reset to 0 by probe failure, then incremented to 1 by tier2 success
        assert fp._success_count == 1
        assert len(p1.calls) == 1  # one probe attempt
        assert len(p2.calls) == 1  # one successful tier2 call

    @pytest.mark.asyncio
    async def test_probe_resets_success_counter_on_success(self):
        """After a successful probe, _success_count is reset to 0.

        Verifies the internal counter is cleared upon moving back up a tier.
        """
        tier1_response = _make_response("tier1 success")
        tier2_response = _make_response("tier2 success")

        # tier1 succeeds (for the probe)
        tier1, p1 = _make_tier(
            "tier1",
            [tier1_response],
            model="tier1-model",
            label="tier1",
        )
        tier2, p2 = _make_tier(
            "tier2",
            [tier2_response],
            model="tier2-model",
            label="tier2",
        )

        fp = _make_failover([tier1, tier2], probe_interval=5)
        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Pre-condition: currently on tier2 with success_count at probe_interval
        fp._current_tier_idx = 1
        fp._success_count = 5

        # Probe fires: tier1 succeeds -> _current_tier_idx=0, _success_count=0
        result = await fp.complete(request)

        assert result == tier1_response
        assert fp._current_tier_idx == 0
        assert fp._success_count == 0  # reset after successful probe

    @pytest.mark.asyncio
    async def test_no_probe_when_already_on_tier1(self):
        """When already on tier1, _success_count stays 0 and no probe fires.

        The probe-up guard (current_tier_idx > 0) prevents probing when
        already on the primary tier.
        """
        tier1_response = _make_response("tier1 success")
        tier2_response = _make_response("tier2 success")

        # tier1 always succeeds
        tier1, p1 = _make_tier(
            "tier1",
            [tier1_response],
            model="tier1-model",
            label="tier1",
        )
        tier2, p2 = _make_tier(
            "tier2",
            [tier2_response],
            model="tier2-model",
            label="tier2",
        )

        fp = _make_failover([tier1, tier2], probe_interval=5)
        request = MockRequest(
            model="any-model",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Make several successful calls on tier1
        for _ in range(10):
            await fp.complete(request)

        # _success_count should stay 0 (not incremented on primary tier)
        assert fp._current_tier_idx == 0
        assert fp._success_count == 0
        # tier2 was never touched
        assert len(p2.calls) == 0
