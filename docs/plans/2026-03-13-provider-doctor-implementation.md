# Provider Doctor Bundle — Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Build an Amplifier bundle that adds tiered provider failover (opus → sonnet → openai), session repair, provider health checks, and support ticket generation — all local, no upstream changes, survives `amplifier reset`.

**Architecture:** A thin bundle (`bundle.md`) composes a behavior (`provider-resilience.yaml`) that mounts a Python module (`provider-failover`). The module implements the Provider protocol as a proxy — the orchestrator sees one provider, failover is invisible. Agents and recipes handle session repair, health checks, and support tooling as declarative YAML/markdown.

**Tech Stack:** Python 3.11+, pytest + pytest-asyncio, amplifier-core (peer dependency — LLMError taxonomy, ChatRequest/ChatResponse, ProviderInfo, ModuleCoordinator)

**Design doc:** `docs/plans/2026-03-13-provider-doctor-design.md`

---

## Prerequisites

Before starting, set up the dev environment:

```bash
cd ~/dev/amplifier-bundle-provider-doctor

# Create a Python virtual environment for testing
python3 -m venv .venv
source .venv/bin/activate

# Install amplifier-core from pre-built wheel (needed for error types, models)
pip install /Users/michaeljabbour/.amplifier/cache/amplifier-core-61734c2990ff26ac/target/wheels/amplifier_core-1.2.0-cp311-cp311-macosx_11_0_arm64.whl

# Install test dependencies
pip install pytest pytest-asyncio ruff
```

If the wheel path doesn't exist, build it:
```bash
cd /Users/michaeljabbour/.amplifier/cache/amplifier-core-61734c2990ff26ac
pip install maturin && maturin build --release
pip install target/wheels/amplifier_core-*.whl
```

All commands below assume you're in `~/dev/amplifier-bundle-provider-doctor/` with the venv active.

---

## Group 1: Provider Failover Module (Python, TDD)

### Task 1: Project Scaffold

**Files:**
- Create: `modules/provider-failover/pyproject.toml`
- Create: `modules/provider-failover/provider_failover/__init__.py`
- Create: `modules/provider-failover/provider_failover/failover.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`

**Step 1: Create directory structure**

```bash
mkdir -p modules/provider-failover/provider_failover
mkdir -p tests
```

**Step 2: Create module pyproject.toml**

Create `modules/provider-failover/pyproject.toml`:

```toml
[project]
name = "amplifier-module-provider-failover"
version = "0.1.0"
description = "Tiered provider failover with retry, backoff, and fail-up probing for Amplifier"
license = "MIT"
requires-python = ">=3.11"
authors = [
    { name = "Michael Jabbour" },
]
dependencies = []

[project.entry-points."amplifier.modules"]
provider-failover = "provider_failover:mount"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
package = true

[tool.hatch.build.targets.wheel]
packages = ["provider_failover"]

[tool.hatch.metadata]
allow-direct-references = true
```

**Step 3: Create `__init__.py` with mount stub**

Create `modules/provider-failover/provider_failover/__init__.py`:

```python
"""Provider failover module for Amplifier.

Tiered provider failover with retry, exponential backoff, and fail-up probing.
The orchestrator sees ONE provider. Failover is invisible.
"""

__all__ = ["mount", "FailoverProvider"]

__amplifier_module_type__ = "provider"

from .failover import FailoverProvider  # noqa: F401


async def mount(coordinator, config=None):
    """Mount the failover provider. Wired up in Task 8."""
    raise NotImplementedError("mount() not yet implemented")
```

**Step 4: Create `failover.py` with empty class**

Create `modules/provider-failover/provider_failover/failover.py`:

```python
"""FailoverProvider — tiered provider failover with retry, backoff, and fail-up."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TierConfig:
    """Configuration for one tier in the failover chain."""

    provider: Any  # Implements Provider protocol
    model: str
    label: str
    context_window: int = 200_000


class FailoverProvider:
    """Implements Provider protocol. Proxies to a chain of real providers."""

    def __init__(
        self,
        tiers: list[TierConfig],
        *,
        max_failures: int = 3,
        retry_base_delay: float = 2.0,
        probe_interval: int = 5,
    ) -> None:
        if not tiers:
            raise ValueError("At least one tier is required")
        self._tiers = tiers
        self._current_tier_idx = 0
        self._max_failures = max_failures
        self._retry_base_delay = retry_base_delay
        self._probe_interval = probe_interval
        self._success_count = 0
        self._sleep = asyncio.sleep  # Injectable for testing
```

**Step 5: Create `pytest.ini` at repo root**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
```

**Step 6: Create `tests/conftest.py` with mock providers**

Create `tests/conftest.py`:

```python
"""Test fixtures — mock providers and helpers for failover tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Make provider_failover importable from repo root
sys.path.insert(
    0, str(Path(__file__).parent.parent / "modules" / "provider-failover")
)

from amplifier_core.llm_errors import (  # noqa: E402
    LLMError,
    AuthenticationError,
    ContentFilterError,
    ContextLengthError,
    LLMTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
    StreamError,
)
from amplifier_core import ProviderInfo  # noqa: E402
from amplifier_core.message_models import (  # noqa: E402
    ChatRequest,
    ChatResponse,
    Message,
    ToolCall,
    Usage,
)

from provider_failover.failover import TierConfig, FailoverProvider  # noqa: E402


class MockProvider:
    """A configurable mock provider for testing.

    Pass a list of responses/exceptions. Each call to complete() pops
    the next item. If it's an exception, it gets raised. Otherwise
    it's returned as the response. When the list runs out, the last
    item is reused forever.
    """

    def __init__(
        self,
        name: str = "mock",
        responses: list | None = None,
        context_window: int = 200_000,
    ):
        self.name = name
        self._responses = list(responses or [])
        self._call_count = 0
        self._context_window = context_window
        self._last_request = None

    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.name,
            display_name=self.name.title(),
            defaults={"context_window": self._context_window},
        )

    async def complete(self, request, **kwargs):
        self._last_request = request
        return self._next_response()

    def stream(self, request, **kwargs):
        self._last_request = request
        return self._stream_response()

    async def _stream_response(self):
        """Async generator that yields the next response or raises."""
        result = self._next_response()
        # Yield the response as a single chunk
        yield result

    def _next_response(self):
        self._call_count += 1
        if not self._responses:
            return _make_response()
        item = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(item, BaseException):
            raise item
        return item

    def parse_tool_calls(self, response) -> list:
        return response.tool_calls or []


def _make_response(text: str = "OK", input_tokens: int = 100) -> ChatResponse:
    """Create a minimal ChatResponse."""
    from amplifier_core.content_models import TextContent

    return ChatResponse(
        content=[TextContent(type="text", text=text)],
        usage=Usage(input_tokens=input_tokens, output_tokens=10, total_tokens=input_tokens + 10),
    )


def _make_request(model: str | None = None) -> ChatRequest:
    """Create a minimal ChatRequest."""
    return ChatRequest(
        messages=[Message(role="user", content="Hello")],
        model=model,
    )


def _make_tier(
    name: str = "mock",
    responses: list | None = None,
    model: str = "test-model",
    label: str = "test",
    context_window: int = 200_000,
) -> tuple[TierConfig, MockProvider]:
    """Create a TierConfig + its MockProvider. Returns both for inspection."""
    provider = MockProvider(name=name, responses=responses, context_window=context_window)
    tier = TierConfig(
        provider=provider,
        model=model,
        label=label,
        context_window=context_window,
    )
    return tier, provider


def _make_failover(
    tiers: list[TierConfig],
    max_failures: int = 3,
    retry_base_delay: float = 0.0,
    probe_interval: int = 5,
) -> FailoverProvider:
    """Create a FailoverProvider with sleep stubbed out (no actual waiting)."""
    fp = FailoverProvider(
        tiers,
        max_failures=max_failures,
        retry_base_delay=retry_base_delay,
        probe_interval=probe_interval,
    )
    # Stub out sleep so tests run instantly
    fp._sleep = _fake_sleep
    return fp


async def _fake_sleep(seconds: float) -> None:
    """Instant sleep for testing — records nothing, waits nothing."""
    pass
```

**Step 7: Verify scaffold compiles**

Run:
```bash
cd ~/dev/amplifier-bundle-provider-doctor
python -c "import sys; sys.path.insert(0, 'modules/provider-failover'); from provider_failover.failover import FailoverProvider, TierConfig; print('OK')"
```
Expected: `OK`

**Step 8: Commit**

```bash
git add modules/ tests/ pytest.ini
git commit -m "feat: scaffold provider-failover module with mock test infrastructure"
```

---

### Task 2: Happy Path — Single Successful Call

**Files:**
- Create: `tests/test_retry.py`
- Modify: `modules/provider-failover/provider_failover/failover.py`

**Step 1: Write the failing test**

Create `tests/test_retry.py`:

```python
"""Tests for single-tier retry behavior."""

from __future__ import annotations

import pytest

# conftest.py handles sys.path — these imports work from repo root
from tests.conftest import (
    _make_failover,
    _make_request,
    _make_response,
    _make_tier,
)


class TestHappyPath:
    """First call succeeds — no retry needed."""

    @pytest.mark.asyncio
    async def test_single_successful_call(self):
        """complete() returns the provider's response on first success."""
        ok_response = _make_response("Hello!")
        tier, provider = _make_tier(responses=[ok_response])
        fp = _make_failover([tier])

        result = await fp.complete(_make_request())

        assert result is ok_response
        assert provider._call_count == 1

    @pytest.mark.asyncio
    async def test_model_override_in_request(self):
        """complete() sets the tier's model in the ChatRequest."""
        ok_response = _make_response()
        tier, provider = _make_tier(model="claude-opus-4-6", responses=[ok_response])
        fp = _make_failover([tier])

        await fp.complete(_make_request(model="original-model"))

        # The provider should have received a request with the tier's model
        assert provider._last_request.model == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_name_reflects_active_tier(self):
        """name property shows the active tier label."""
        tier, _ = _make_tier(label="opus")
        fp = _make_failover([tier])

        assert fp.name == "failover(opus)"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_retry.py -v`
Expected: FAIL — `FailoverProvider` has no `complete()` method yet.

**Step 3: Implement minimal complete() and name property**

In `modules/provider-failover/provider_failover/failover.py`, add these methods to `FailoverProvider`:

```python
    @property
    def name(self) -> str:
        """Provider name — shows the currently active tier."""
        return f"failover({self._current_tier.label})"

    @property
    def _current_tier(self) -> TierConfig:
        return self._tiers[self._current_tier_idx]

    def get_info(self):
        """Delegate to the active tier's provider."""
        return self._current_tier.provider.get_info()

    def parse_tool_calls(self, response) -> list:
        """Delegate to the active tier's provider."""
        return self._current_tier.provider.parse_tool_calls(response)

    async def complete(self, request, **kwargs) -> Any:
        """Complete with failover. Core method."""
        return await self._call_with_failover("complete", request, **kwargs)

    async def _call_with_failover(self, method: str, request, **kwargs) -> Any:
        """Core failover logic — retry within tier, fall between tiers."""
        tier = self._current_tier

        # Override the model in the request to match the current tier
        modified_request = request.model_copy(update={"model": tier.model})

        result = await getattr(tier.provider, method)(modified_request, **kwargs)
        return result
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_retry.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add tests/test_retry.py modules/provider-failover/provider_failover/failover.py
git commit -m "feat: FailoverProvider happy path — complete() delegates to active tier"
```

---

### Task 3: Single-Tier Retry with Exponential Backoff

**Files:**
- Modify: `tests/test_retry.py`
- Modify: `modules/provider-failover/provider_failover/failover.py`

**Step 1: Write the failing tests**

Append to `tests/test_retry.py`:

```python
from amplifier_core.llm_errors import (
    ProviderUnavailableError,
    RateLimitError,
    AuthenticationError,
    ContentFilterError,
)


class TestRetryWithBackoff:
    """Retryable errors trigger retry with exponential backoff within one tier."""

    @pytest.mark.asyncio
    async def test_retry_on_retryable_error_then_succeed(self):
        """Retries on ProviderUnavailableError, then succeeds."""
        ok = _make_response("recovered")
        tier, provider = _make_tier(
            responses=[
                ProviderUnavailableError("overloaded", retryable=True),
                ok,
            ]
        )
        fp = _make_failover([tier], max_failures=3)

        result = await fp.complete(_make_request())

        assert result is ok
        assert provider._call_count == 2  # 1 fail + 1 success

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        """Retries on RateLimitError."""
        ok = _make_response()
        tier, provider = _make_tier(
            responses=[
                RateLimitError("429", retryable=True),
                RateLimitError("429", retryable=True),
                ok,
            ]
        )
        fp = _make_failover([tier], max_failures=3)

        result = await fp.complete(_make_request())

        assert result is ok
        assert provider._call_count == 3  # 2 fails + 1 success

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Backoff delays are base * 2^attempt: 2s, 4s."""
        delays: list[float] = []

        async def recording_sleep(seconds: float):
            delays.append(seconds)

        ok = _make_response()
        tier, _ = _make_tier(
            responses=[
                ProviderUnavailableError("err", retryable=True),
                ProviderUnavailableError("err", retryable=True),
                ok,
            ]
        )
        fp = _make_failover([tier], max_failures=3, retry_base_delay=2.0)
        fp._sleep = recording_sleep

        await fp.complete(_make_request())

        assert delays == [2.0, 4.0]  # base*2^0, base*2^1


class TestNonRetryableErrors:
    """Non-retryable errors skip retry — no backoff, immediate propagation."""

    @pytest.mark.asyncio
    async def test_auth_error_skips_retry_single_tier(self):
        """AuthenticationError with only one tier raises immediately."""
        tier, provider = _make_tier(
            responses=[AuthenticationError("bad key")]
        )
        fp = _make_failover([tier], max_failures=3)

        with pytest.raises(AuthenticationError, match="bad key"):
            await fp.complete(_make_request())

        assert provider._call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_content_filter_skips_retry_single_tier(self):
        """ContentFilterError with only one tier raises immediately."""
        tier, provider = _make_tier(
            responses=[ContentFilterError("blocked")]
        )
        fp = _make_failover([tier], max_failures=3)

        with pytest.raises(ContentFilterError, match="blocked"):
            await fp.complete(_make_request())

        assert provider._call_count == 1
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_retry.py -v`
Expected: New tests FAIL — `_call_with_failover` doesn't retry yet.

**Step 3: Implement retry with backoff in `_call_with_failover`**

Replace the `_call_with_failover` method in `failover.py` with:

```python
    async def _call_with_failover(self, method: str, request, **kwargs) -> Any:
        """Core failover logic — retry within tier, fall between tiers.

        For each tier starting from _current_tier_idx:
          1. Try up to max_failures times with exponential backoff
          2. Non-retryable errors (AuthenticationError, ContentFilterError)
             skip retry and fall to the next tier immediately
          3. If all retries exhausted, fall to the next tier
          4. If all tiers exhausted, raise the last error
        """
        from amplifier_core.llm_errors import (
            LLMError,
            AuthenticationError,
            ContentFilterError,
        )

        last_error: BaseException | None = None
        start_idx = self._current_tier_idx
        tier_idx = start_idx

        while tier_idx < len(self._tiers):
            tier = self._tiers[tier_idx]
            modified_request = request.model_copy(update={"model": tier.model})

            for attempt in range(self._max_failures):
                try:
                    result = await self._invoke(
                        method, tier.provider, modified_request, **kwargs
                    )

                    # Success — update state
                    self._current_tier_idx = tier_idx
                    if tier_idx > 0:
                        self._success_count += 1
                    else:
                        self._success_count = 0

                    self._log_usage(tier, result)
                    return result

                except (AuthenticationError, ContentFilterError) as e:
                    # Non-retryable: skip remaining retries, fall to next tier
                    last_error = e
                    logger.warning(
                        "[FAILOVER] %s: %s (non-retryable). Falling to next tier.",
                        tier.label,
                        type(e).__name__,
                    )
                    tier_idx += 1
                    break  # Break retry loop → next tier

                except LLMError as e:
                    last_error = e
                    if not e.retryable:
                        logger.warning(
                            "[FAILOVER] %s: %s (non-retryable). Falling to next tier.",
                            tier.label,
                            type(e).__name__,
                        )
                        tier_idx += 1
                        break  # Next tier

                    if attempt < self._max_failures - 1:
                        delay = self._retry_base_delay * (2**attempt)
                        logger.warning(
                            "[FAILOVER] %s: Attempt %d/%d failed (%s). Retrying in %.1fs.",
                            tier.label,
                            attempt + 1,
                            self._max_failures,
                            type(e).__name__,
                            delay,
                        )
                        await self._sleep(delay)
                    else:
                        logger.warning(
                            "[FAILOVER] %s: All %d attempts exhausted. Falling to next tier.",
                            tier.label,
                            self._max_failures,
                        )
                        tier_idx += 1
            else:
                # for loop completed without break — all attempts exhausted
                # tier_idx already incremented in the last else branch above
                continue
            # for loop broke (non-retryable error) — tier_idx already incremented
            continue

        # All tiers exhausted
        if last_error is not None:
            raise last_error
        raise RuntimeError("All tiers exhausted with no error recorded")

    async def _invoke(self, method: str, provider, request, **kwargs) -> Any:
        """Call a provider method, handling both sync and async returns."""
        result = getattr(provider, method)(request, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def _log_usage(self, tier: TierConfig, result: Any) -> None:
        """Log token usage if the response includes it."""
        usage = getattr(result, "usage", None)
        if usage and hasattr(usage, "input_tokens") and usage.input_tokens is not None:
            logger.info(
                "[FAILOVER] Tier %s: request succeeded (input_tokens=%s)",
                tier.label,
                f"{usage.input_tokens:,}",
            )
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_retry.py -v`
Expected: All 8 tests pass

**Step 5: Commit**

```bash
git add tests/test_retry.py modules/provider-failover/provider_failover/failover.py
git commit -m "feat: single-tier retry with exponential backoff and non-retryable skip"
```

---

### Task 4: Multi-Tier Fallback

**Files:**
- Create: `tests/test_failover.py`
- (No implementation changes needed — Task 3's code already iterates tiers)

**Step 1: Write the tests**

Create `tests/test_failover.py`:

```python
"""Tests for multi-tier fallback behavior."""

from __future__ import annotations

import pytest

from amplifier_core.llm_errors import (
    AuthenticationError,
    ProviderUnavailableError,
    RateLimitError,
)

from tests.conftest import (
    _make_failover,
    _make_request,
    _make_response,
    _make_tier,
)


class TestMultiTierFallback:
    """When one tier exhausts retries, fall to the next."""

    @pytest.mark.asyncio
    async def test_fall_to_tier2_after_tier1_exhausted(self):
        """3 failures on tier 1 → automatic fallback to tier 2."""
        err = ProviderUnavailableError("overloaded", retryable=True)
        ok = _make_response("from tier 2")

        tier1, p1 = _make_tier(label="opus", responses=[err, err, err])
        tier2, p2 = _make_tier(label="sonnet", responses=[ok])
        fp = _make_failover([tier1, tier2], max_failures=3)

        result = await fp.complete(_make_request())

        assert result is ok
        assert p1._call_count == 3  # All 3 retries exhausted
        assert p2._call_count == 1
        assert fp.name == "failover(sonnet)"  # Now on tier 2

    @pytest.mark.asyncio
    async def test_fall_through_all_three_tiers(self):
        """Tier 1 → Tier 2 → Tier 3, success at tier 3."""
        err = ProviderUnavailableError("down", retryable=True)
        ok = _make_response("from tier 3")

        tier1, p1 = _make_tier(label="opus", responses=[err, err, err])
        tier2, p2 = _make_tier(label="sonnet", responses=[err, err, err])
        tier3, p3 = _make_tier(label="openai", responses=[ok])
        fp = _make_failover([tier1, tier2, tier3], max_failures=3)

        result = await fp.complete(_make_request())

        assert result is ok
        assert p1._call_count == 3
        assert p2._call_count == 3
        assert p3._call_count == 1
        assert fp.name == "failover(openai)"

    @pytest.mark.asyncio
    async def test_all_tiers_exhausted_raises_last_error(self):
        """When every tier fails, raise the LAST error."""
        err1 = ProviderUnavailableError("tier1 down", retryable=True)
        err2 = RateLimitError("tier2 limited", retryable=True)

        tier1, _ = _make_tier(label="opus", responses=[err1, err1, err1])
        tier2, _ = _make_tier(label="sonnet", responses=[err2, err2, err2])
        fp = _make_failover([tier1, tier2], max_failures=3)

        with pytest.raises(RateLimitError, match="tier2 limited"):
            await fp.complete(_make_request())

    @pytest.mark.asyncio
    async def test_nonretryable_falls_to_next_tier(self):
        """AuthenticationError on tier 1 → immediate fall to tier 2 (no retry)."""
        ok = _make_response("from tier 2")

        tier1, p1 = _make_tier(
            label="opus", responses=[AuthenticationError("bad key")]
        )
        tier2, p2 = _make_tier(label="sonnet", responses=[ok])
        fp = _make_failover([tier1, tier2], max_failures=3)

        result = await fp.complete(_make_request())

        assert result is ok
        assert p1._call_count == 1  # No retry — fell immediately
        assert p2._call_count == 1

    @pytest.mark.asyncio
    async def test_each_tier_gets_its_own_model(self):
        """Each tier overrides the model in the ChatRequest."""
        err = ProviderUnavailableError("err", retryable=True)
        ok = _make_response()

        tier1, p1 = _make_tier(
            model="claude-opus-4-6", label="opus", responses=[err, err, err]
        )
        tier2, p2 = _make_tier(
            model="claude-sonnet-4-5", label="sonnet", responses=[ok]
        )
        fp = _make_failover([tier1, tier2], max_failures=3)

        await fp.complete(_make_request(model="user-requested"))

        assert p1._last_request.model == "claude-opus-4-6"
        assert p2._last_request.model == "claude-sonnet-4-5"
```

**Step 2: Run tests**

Run: `python -m pytest tests/test_failover.py -v`
Expected: All 5 tests pass (the multi-tier iteration was already implemented in Task 3).

If any fail, check that `_call_with_failover` properly breaks out of the retry loop for non-retryable errors and continues to the next tier in the outer `while` loop.

**Step 3: Commit**

```bash
git add tests/test_failover.py
git commit -m "test: multi-tier fallback — fall-through, tier exhaustion, model override"
```

---

### Task 5: Fail-Up Probing

**Files:**
- Create: `tests/test_failup.py`
- Modify: `modules/provider-failover/provider_failover/failover.py`

**Step 1: Write the failing tests**

Create `tests/test_failup.py`:

```python
"""Tests for fail-up probing — always try to return to the intended model."""

from __future__ import annotations

import pytest

from amplifier_core.llm_errors import ProviderUnavailableError

from tests.conftest import (
    _make_failover,
    _make_request,
    _make_response,
    _make_tier,
)


class TestFailUpProbing:
    """After falling to a lower tier, probe the tier above periodically."""

    @pytest.mark.asyncio
    async def test_probe_after_n_successes(self):
        """After probe_interval successes on tier 2, probes tier 1."""
        err = ProviderUnavailableError("down", retryable=True)
        ok1 = _make_response("from tier 1")
        ok2 = _make_response("from tier 2")

        # Tier 1: fails first 3 calls (triggers fallback), then succeeds (probe)
        tier1, p1 = _make_tier(
            label="opus",
            responses=[err, err, err, ok1],
        )
        # Tier 2: succeeds 5 times (probe_interval), then we probe up
        tier2, p2 = _make_tier(
            label="sonnet",
            responses=[ok2, ok2, ok2, ok2, ok2, ok2],
        )
        fp = _make_failover([tier1, tier2], max_failures=3, probe_interval=5)

        # Call 1: tier 1 fails 3x → falls to tier 2, tier 2 succeeds
        result1 = await fp.complete(_make_request())
        assert fp.name == "failover(sonnet)"

        # Calls 2-5: tier 2 succeeds, building up success_count (now 2,3,4,5)
        for _ in range(4):
            await fp.complete(_make_request())

        # Call 6: success_count == 5 == probe_interval → probes tier 1
        result6 = await fp.complete(_make_request())
        assert result6 is ok1
        assert fp.name == "failover(opus)"  # Back on tier 1!

    @pytest.mark.asyncio
    async def test_failed_probe_stays_on_current_tier(self):
        """If the probe fails, stay on current tier and reset counter."""
        err = ProviderUnavailableError("still down", retryable=True)
        ok2 = _make_response("from tier 2")

        # Tier 1: always fails
        tier1, p1 = _make_tier(
            label="opus",
            responses=[err, err, err, err],  # 3 for initial + 1 for probe
        )
        tier2, p2 = _make_tier(
            label="sonnet",
            responses=[ok2, ok2, ok2, ok2, ok2, ok2, ok2],
        )
        fp = _make_failover([tier1, tier2], max_failures=3, probe_interval=5)

        # Fall to tier 2
        await fp.complete(_make_request())
        assert fp.name == "failover(sonnet)"

        # 4 more successes on tier 2 (total 5)
        for _ in range(4):
            await fp.complete(_make_request())

        # Probe fires → tier 1 still failing → stays on tier 2
        await fp.complete(_make_request())
        assert fp.name == "failover(sonnet)"
        assert fp._success_count == 0  # Counter reset after probe

    @pytest.mark.asyncio
    async def test_probe_resets_success_counter_on_success(self):
        """After successful probe, success counter resets to 0."""
        err = ProviderUnavailableError("down", retryable=True)
        ok1 = _make_response("tier 1 back")
        ok2 = _make_response("tier 2")

        tier1, _ = _make_tier(label="opus", responses=[err, err, err, ok1])
        tier2, _ = _make_tier(label="sonnet", responses=[ok2] * 6)
        fp = _make_failover([tier1, tier2], max_failures=3, probe_interval=5)

        # Fall to tier 2, then 4 more successes, then probe succeeds
        for _ in range(6):
            await fp.complete(_make_request())

        assert fp.name == "failover(opus)"
        assert fp._success_count == 0  # Reset after moving up

    @pytest.mark.asyncio
    async def test_no_probe_when_already_on_tier1(self):
        """No probing when already on the top tier."""
        ok = _make_response()
        tier1, p1 = _make_tier(label="opus", responses=[ok] * 10)
        fp = _make_failover([tier1], probe_interval=5)

        for _ in range(10):
            await fp.complete(_make_request())

        # success_count stays 0 on tier 0 (no probe needed)
        assert fp._success_count == 0
        assert fp.name == "failover(opus)"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_failup.py -v`
Expected: FAIL — probe logic not yet implemented.

**Step 3: Add probe-up logic to `_call_with_failover`**

In `failover.py`, add the probe check at the **very start** of `_call_with_failover`, before the `last_error` assignment. Insert these lines right after the imports inside the method:

```python
        # Probe up: if on a lower tier and enough successes, try the tier above
        if self._current_tier_idx > 0 and self._success_count >= self._probe_interval:
            probe_result = await self._probe_up(method, request, **kwargs)
            if probe_result is not None:
                return probe_result
```

Add the `_probe_up` method to `FailoverProvider`:

```python
    async def _probe_up(self, method: str, request, **kwargs) -> Any | None:
        """Probe the tier above. Returns result on success, None on failure."""
        from amplifier_core.llm_errors import LLMError

        probe_idx = self._current_tier_idx - 1
        tier = self._tiers[probe_idx]
        modified_request = request.model_copy(update={"model": tier.model})

        try:
            result = await self._invoke(method, tier.provider, modified_request, **kwargs)
            logger.info(
                "[FAILOVER] Probe succeeded — moving back up to %s", tier.label
            )
            self._current_tier_idx = probe_idx
            self._success_count = 0
            self._log_usage(tier, result)
            return result
        except (LLMError, Exception):
            logger.info(
                "[FAILOVER] Probe to %s failed. Staying on %s.",
                tier.label,
                self._current_tier.label,
            )
            self._success_count = 0  # Reset counter — will probe again later
            return None
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_failup.py -v`
Expected: All 4 tests pass

**Step 5: Run ALL tests to ensure nothing broke**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (retry + failover + failup)

**Step 6: Commit**

```bash
git add tests/test_failup.py modules/provider-failover/provider_failover/failover.py
git commit -m "feat: fail-up probing — probe tier above every N successes, move back on success"
```

---

### Task 6: stream() Proxy

**Files:**
- Create: `tests/test_stream.py`
- Modify: `modules/provider-failover/provider_failover/failover.py`

**Step 1: Write the failing tests**

Create `tests/test_stream.py`:

```python
"""Tests for stream() proxy — same failover logic as complete()."""

from __future__ import annotations

import pytest

from amplifier_core.llm_errors import ProviderUnavailableError

from tests.conftest import (
    _make_failover,
    _make_request,
    _make_response,
    _make_tier,
)


class TestStreamProxy:
    """stream() returns an async iterator with failover behavior."""

    @pytest.mark.asyncio
    async def test_stream_happy_path(self):
        """stream() delegates to the tier's stream() and yields chunks."""
        ok = _make_response("streamed")
        tier, provider = _make_tier(responses=[ok])
        fp = _make_failover([tier])

        chunks = []
        async for chunk in fp.stream(_make_request()):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] is ok

    @pytest.mark.asyncio
    async def test_stream_falls_to_next_tier_on_failure(self):
        """stream() applies multi-tier failover."""
        err = ProviderUnavailableError("down", retryable=True)
        ok = _make_response("from tier 2")

        tier1, p1 = _make_tier(label="opus", responses=[err, err, err])
        tier2, p2 = _make_tier(label="sonnet", responses=[ok])
        fp = _make_failover([tier1, tier2], max_failures=3)

        chunks = []
        async for chunk in fp.stream(_make_request()):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] is ok
        assert fp.name == "failover(sonnet)"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_stream.py -v`
Expected: FAIL — `FailoverProvider` has no `stream()` method.

**Step 3: Implement stream() as an async generator**

Add to `FailoverProvider` in `failover.py`:

```python
    def stream(self, request, **kwargs):
        """Stream with failover. Returns an async iterator.

        The orchestrator calls this WITHOUT await:
            stream_iter = provider.stream(request)
            async for chunk in stream_iter: ...

        So this must be a regular method returning an async iterable.
        """
        return self._stream_with_failover(request, **kwargs)

    async def _stream_with_failover(self, request, **kwargs):
        """Async generator — applies failover logic, then yields stream chunks."""
        from amplifier_core.llm_errors import (
            LLMError,
            AuthenticationError,
            ContentFilterError,
        )

        # Probe up if applicable
        if self._current_tier_idx > 0 and self._success_count >= self._probe_interval:
            probe_result = await self._probe_up("stream", request, **kwargs)
            if probe_result is not None:
                async for chunk in probe_result:
                    yield chunk
                return

        last_error: BaseException | None = None
        start_idx = self._current_tier_idx
        tier_idx = start_idx

        while tier_idx < len(self._tiers):
            tier = self._tiers[tier_idx]
            modified_request = request.model_copy(update={"model": tier.model})

            for attempt in range(self._max_failures):
                try:
                    stream_iter = tier.provider.stream(modified_request, **kwargs)
                    async for chunk in stream_iter:
                        yield chunk

                    # Completed successfully
                    self._current_tier_idx = tier_idx
                    if tier_idx > 0:
                        self._success_count += 1
                    else:
                        self._success_count = 0
                    return

                except (AuthenticationError, ContentFilterError) as e:
                    last_error = e
                    logger.warning(
                        "[FAILOVER] %s stream: %s (non-retryable). Falling to next tier.",
                        tier.label,
                        type(e).__name__,
                    )
                    tier_idx += 1
                    break

                except LLMError as e:
                    last_error = e
                    if not e.retryable:
                        tier_idx += 1
                        break

                    if attempt < self._max_failures - 1:
                        delay = self._retry_base_delay * (2**attempt)
                        logger.warning(
                            "[FAILOVER] %s stream: Attempt %d/%d failed. Retrying in %.1fs.",
                            tier.label,
                            attempt + 1,
                            self._max_failures,
                            delay,
                        )
                        await self._sleep(delay)
                    else:
                        logger.warning(
                            "[FAILOVER] %s stream: All %d attempts exhausted.",
                            tier.label,
                            self._max_failures,
                        )
                        tier_idx += 1
            else:
                continue
            continue

        if last_error is not None:
            raise last_error
        raise RuntimeError("All tiers exhausted with no error recorded")
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_stream.py -v`
Expected: 2 passed

**Step 5: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add tests/test_stream.py modules/provider-failover/provider_failover/failover.py
git commit -m "feat: stream() proxy — async generator with same failover logic as complete()"
```

---

### Task 7: ContextLengthError Special Handling

**Files:**
- Create: `tests/test_context_length.py`
- Modify: `modules/provider-failover/provider_failover/failover.py`

**Step 1: Write the failing tests**

Create `tests/test_context_length.py`:

```python
"""Tests for ContextLengthError — context-aware fallback."""

from __future__ import annotations

import pytest

from amplifier_core.llm_errors import ContextLengthError

from tests.conftest import (
    _make_failover,
    _make_request,
    _make_response,
    _make_tier,
)


class TestContextLengthFallback:
    """ContextLengthError only falls to a tier with a LARGER context window."""

    @pytest.mark.asyncio
    async def test_falls_to_tier_with_larger_context_window(self):
        """If next tier has larger context, fall to it."""
        ok = _make_response("fits in bigger window")
        tier1, p1 = _make_tier(
            label="opus",
            context_window=200_000,
            responses=[ContextLengthError("too long")],
        )
        tier2, p2 = _make_tier(
            label="openai",
            context_window=1_000_000,
            responses=[ok],
        )
        fp = _make_failover([tier1, tier2], max_failures=3)

        result = await fp.complete(_make_request())

        assert result is ok
        assert p1._call_count == 1  # No retry — fell immediately
        assert p2._call_count == 1

    @pytest.mark.asyncio
    async def test_raises_if_no_larger_context_available(self):
        """If no tier has a larger context window, raise with actionable message."""
        tier1, _ = _make_tier(
            label="opus",
            context_window=200_000,
            responses=[ContextLengthError("too long")],
        )
        tier2, _ = _make_tier(
            label="sonnet",
            context_window=200_000,
            responses=[_make_response()],  # Won't be called
        )
        fp = _make_failover([tier1, tier2], max_failures=3)

        with pytest.raises(ContextLengthError, match="Start a new session"):
            await fp.complete(_make_request())

    @pytest.mark.asyncio
    async def test_raises_if_last_tier(self):
        """ContextLengthError on last tier raises — nowhere to fall."""
        tier1, _ = _make_tier(
            label="openai",
            context_window=1_000_000,
            responses=[ContextLengthError("way too long")],
        )
        fp = _make_failover([tier1], max_failures=3)

        with pytest.raises(ContextLengthError, match="Start a new session"):
            await fp.complete(_make_request())

    @pytest.mark.asyncio
    async def test_skips_tier_with_same_context_window(self):
        """Same context window = no help. Falls to one with bigger window."""
        ok = _make_response("big window saves the day")
        tier1, _ = _make_tier(
            label="opus",
            context_window=200_000,
            responses=[ContextLengthError("too long")],
        )
        tier2, p2 = _make_tier(
            label="sonnet",
            context_window=200_000,  # Same size — skip
            responses=[_make_response()],
        )
        tier3, p3 = _make_tier(
            label="openai",
            context_window=1_000_000,  # Bigger — try this
            responses=[ok],
        )
        fp = _make_failover([tier1, tier2, tier3], max_failures=3)

        result = await fp.complete(_make_request())

        assert result is ok
        assert p2._call_count == 0  # Skipped — same context window
        assert p3._call_count == 1
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_context_length.py -v`
Expected: FAIL — ContextLengthError is not handled specially yet.

**Step 3: Add ContextLengthError handling to `_call_with_failover`**

In `failover.py`, update `_call_with_failover` to handle ContextLengthError. Add `ContextLengthError` to the imports and insert a new `except` clause **before** the `(AuthenticationError, ContentFilterError)` handler. The try/except block inside the retry `for` loop should now look like this:

```python
                try:
                    result = await self._invoke(
                        method, tier.provider, modified_request, **kwargs
                    )
                    self._current_tier_idx = tier_idx
                    if tier_idx > 0:
                        self._success_count += 1
                    else:
                        self._success_count = 0
                    self._log_usage(tier, result)
                    return result

                except ContextLengthError as e:
                    # Special: only fall to a tier with a LARGER context window
                    last_error = e
                    jump = self._find_larger_context_tier(tier_idx)
                    if jump is not None:
                        logger.warning(
                            "[FAILOVER] Context exceeded for %s (%d tokens). "
                            "Trying %s (%d tokens).",
                            tier.label,
                            tier.context_window,
                            self._tiers[jump].label,
                            self._tiers[jump].context_window,
                        )
                        tier_idx = jump  # Jump to the larger-context tier
                        break  # Break retry loop, outer while continues
                    raise ContextLengthError(
                        f"Context window exceeded for {tier.label}. "
                        f"No tier with a larger context window available. "
                        f"Start a new session.",
                        provider=getattr(e, "provider", None),
                        model=getattr(e, "model", None),
                        status_code=getattr(e, "status_code", None),
                    ) from e

                except (AuthenticationError, ContentFilterError) as e:
                    # ... existing handler unchanged ...
```

Also add the `ContextLengthError` import to the method's import block:

```python
        from amplifier_core.llm_errors import (
            LLMError,
            AuthenticationError,
            ContentFilterError,
            ContextLengthError,
        )
```

And add the `_find_larger_context_tier` helper method to `FailoverProvider`:

```python
    def _find_larger_context_tier(self, current_idx: int) -> int | None:
        """Find the next tier with a strictly larger context window."""
        current_window = self._tiers[current_idx].context_window
        for idx in range(current_idx + 1, len(self._tiers)):
            if self._tiers[idx].context_window > current_window:
                return idx
        return None
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_context_length.py -v`
Expected: All 4 tests pass

**Step 5: Run ALL tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass. If any prior tests broke due to the new `except ContextLengthError` clause, ensure it's placed **before** the `except LLMError` clause (since ContextLengthError is a subclass of LLMError).

**Step 6: Commit**

```bash
git add tests/test_context_length.py modules/provider-failover/provider_failover/failover.py
git commit -m "feat: ContextLengthError handling — fall to larger context tier or raise actionable message"
```

---

### Task 8: mount() Function — Coordinator Integration

**Files:**
- Modify: `modules/provider-failover/provider_failover/__init__.py`

**Step 1: Implement the mount() function**

Replace the stub `mount()` in `modules/provider-failover/provider_failover/__init__.py` with:

```python
"""Provider failover module for Amplifier.

Tiered provider failover with retry, exponential backoff, and fail-up probing.
The orchestrator sees ONE provider. Failover is invisible.
"""

__all__ = ["mount", "FailoverProvider"]

__amplifier_module_type__ = "provider"

import logging
from typing import Any

from .failover import FailoverProvider, TierConfig  # noqa: F401

logger = logging.getLogger(__name__)


async def mount(coordinator, config: dict[str, Any] | None = None):
    """Mount the failover provider.

    Reads tier config, resolves real providers from the coordinator,
    and mounts a FailoverProvider that proxies them.

    Config example (from behaviors/provider-resilience.yaml):
        max_failures: 3
        retry_base_delay: 2
        probe_interval: 5
        tiers:
          - provider: provider-anthropic
            model: claude-opus-4-6
            label: opus
          - provider: provider-anthropic
            model: claude-sonnet-4-5
            label: sonnet
          - provider: provider-openai
            model: gpt-5.4
            label: openai-codex
    """
    config = config or {}
    tier_configs = config.get("tiers", [])

    if not tier_configs:
        logger.warning("[FAILOVER] No tiers configured. Skipping mount.")
        return None

    # Resolve real providers from the coordinator
    providers_dict = coordinator.get("providers") or {}
    tiers: list[TierConfig] = []

    for tc in tier_configs:
        module_id = tc.get("provider", "")
        # Provider mount names strip the "provider-" prefix
        mount_name = (
            module_id.removeprefix("provider-") if module_id.startswith("provider-") else module_id
        )
        provider = providers_dict.get(mount_name)
        if provider is None:
            logger.warning(
                "[FAILOVER] Provider '%s' (mount name '%s') not found. Skipping tier '%s'.",
                module_id,
                mount_name,
                tc.get("label", "?"),
            )
            continue

        # Get context window from provider info
        info = provider.get_info()
        context_window = info.defaults.get("context_window", 200_000)

        tiers.append(
            TierConfig(
                provider=provider,
                model=tc.get("model", ""),
                label=tc.get("label", mount_name),
                context_window=context_window,
            )
        )

    if not tiers:
        logger.warning("[FAILOVER] No valid tiers resolved. Skipping mount.")
        return None

    failover = FailoverProvider(
        tiers,
        max_failures=config.get("max_failures", 3),
        retry_base_delay=config.get("retry_base_delay", 2.0),
        probe_interval=config.get("probe_interval", 5),
    )

    await coordinator.mount("providers", failover, name="failover")
    logger.info(
        "[FAILOVER] Mounted FailoverProvider with %d tiers: %s",
        len(tiers),
        " → ".join(t.label for t in tiers),
    )

    return None  # No cleanup needed — no SDK clients to close
```

**Step 2: Verify the module loads**

Run:
```bash
python -c "
import sys; sys.path.insert(0, 'modules/provider-failover')
from provider_failover import mount, FailoverProvider
print(f'mount: {mount}')
print(f'FailoverProvider: {FailoverProvider}')
print('OK')
"
```
Expected: Prints both objects and `OK`.

**Step 3: Commit**

```bash
git add modules/provider-failover/provider_failover/__init__.py
git commit -m "feat: mount() resolves providers from coordinator, builds failover chain"
```

---

## Group 2: Bundle Wiring

### Task 9: Bundle + Behavior YAML

**Files:**
- Create: `bundle.md`
- Create: `behaviors/provider-resilience.yaml`

**Step 1: Create the root bundle**

Create `bundle.md`:

```markdown
---
bundle:
  name: provider-doctor
  version: 0.1.0
  description: >
    Provider resilience, session repair, and support tooling for Amplifier.
    Adds tiered provider failover with fail-up, session diagnosis/repair,
    and structured support ticket generation.

includes:
  - bundle: behaviors/provider-resilience.yaml

agents:
  session-doctor:
    bundle: ./agents/session-doctor.md
  provider-health:
    bundle: ./agents/provider-health.md
  support:
    bundle: ./agents/support.md
---

# Provider Doctor

Resilience and recovery tooling for Amplifier sessions.

## Capabilities

- **Provider failover**: Tiered failover with retry, backoff, and fail-up probing
- **Session repair**: Diagnose and fix broken sessions
- **Provider health**: Test provider connectivity and latency
- **Support**: Generate structured support tickets with diagnosis
```

**Step 2: Create the behavior YAML**

```bash
mkdir -p behaviors
```

Create `behaviors/provider-resilience.yaml`:

```yaml
bundle:
  name: provider-resilience
  version: 0.1.0
  description: >
    Composable behavior: tiered provider failover with retry, backoff,
    and fail-up probing. Include this in any bundle for provider resilience.

providers:
  - module: provider-failover
    source: ./modules/provider-failover
    config:
      max_failures: 3
      retry_base_delay: 2
      probe_interval: 5
      tiers:
        - provider: provider-anthropic
          model: claude-opus-4-6
          label: "opus"
        - provider: provider-anthropic
          model: claude-sonnet-4-5
          label: "sonnet"
        - provider: provider-openai
          model: gpt-5.4
          label: "openai-codex"
```

**Step 3: Commit**

```bash
git add bundle.md behaviors/
git commit -m "feat: bundle.md + provider-resilience behavior — composable failover config"
```

---

## Group 3: Session Doctor

### Task 10: Session Doctor Agent

**Files:**
- Create: `agents/session-doctor.md`

**Step 1: Create the agent**

```bash
mkdir -p agents
```

Create `agents/session-doctor.md`:

````markdown
---
meta:
  name: session-doctor
  description: >
    Diagnoses and repairs broken Amplifier sessions. Checks for orphaned tool calls,
    ordering violations, oversized transcripts, and other structural issues. Can
    perform repairs (inject synthetic results, rewind transcripts) with backup.
model_role: fast
---

You are a session repair specialist for Amplifier. When given a session ID or session path:

## Diagnosis Steps

1. **Locate the session directory** — check `~/.amplifier/sessions/<session_id>/`
2. **Read `metadata.json`** — extract session info, provider, model, timestamps
3. **Analyze `events.jsonl`** for structural issues:
   - **Orphaned tool calls**: assistant messages with `tool_use` blocks that have no matching tool result
   - **Ordering violations**: tool results that appear before their corresponding tool calls
   - **Oversized transcripts**: total character count exceeding reasonable limits (>500K chars)
   - **Duplicate entries**: identical consecutive events
   - **Truncated events**: incomplete JSON lines (usually from a crash)
4. **Report findings** with severity (critical/warning/info)

## Repair Strategies

When repair is requested:

1. **ALWAYS create a backup first**: copy `events.jsonl` to `events.jsonl.bak.<timestamp>`
2. **Prefer REPAIR over REWIND**:
   - REPAIR = inject synthetic tool results for orphaned calls (minimal, non-destructive)
   - REWIND = truncate the transcript to a known-good point (loses data)
3. **Only REWIND when explicitly requested** or when REPAIR is impossible
4. **Verify after repair**: re-run diagnosis on the repaired file

## Output Format

Always report in this structure:
```
Session: <id>
Status: HEALTHY | NEEDS_REPAIR | CRITICAL
Issues found: <count>

Issue 1: [severity] <description>
  Line: <line_number in events.jsonl>
  Fix: <recommended action>

Repair plan: <summary of what will be done>
```
````

**Step 2: Commit**

```bash
git add agents/session-doctor.md
git commit -m "feat: session-doctor agent — diagnose and repair broken sessions"
```

---

### Task 11: Session Repair Recipe

**Files:**
- Create: `recipes/session-repair.yaml`

**Step 1: Create the recipe**

```bash
mkdir -p recipes
```

Create `recipes/session-repair.yaml`:

```yaml
name: session-repair
description: Diagnose and optionally repair a broken Amplifier session

steps:
  - name: diagnose
    agent: provider-doctor:session-doctor
    instruction: |
      Analyze session {{session_id}} for structural issues.

      Check for:
      - Orphaned tool calls (tool_use with no matching tool result)
      - Ordering violations (tool results before their calls)
      - Oversized transcripts (>500K characters)
      - Truncated or malformed events

      Report findings with severity levels and recommended actions.
      Set needs_repair=true if any critical or warning issues found.

  - name: repair
    agent: provider-doctor:session-doctor
    condition: "{{diagnose.needs_repair}}"
    instruction: |
      Apply the recommended repairs to session {{session_id}}.

      Steps:
      1. Create backup of events.jsonl
      2. Apply the minimal fix (inject synthetic results for orphaned calls)
      3. Verify the repair by re-analyzing the session
      4. Report: what was changed, backup location, verification result
```

**Step 2: Commit**

```bash
git add recipes/session-repair.yaml
git commit -m "feat: session-repair recipe — two-step diagnose + conditional repair"
```

---

## Group 4: Provider Health

### Task 12: Provider Health Agent

**Files:**
- Create: `agents/provider-health.md`

**Step 1: Create the agent**

Create `agents/provider-health.md`:

````markdown
---
meta:
  name: provider-health
  description: >
    Tests provider connectivity and responsiveness. Sends minimal test requests
    to each configured provider and reports latency, errors, and availability.
model_role: fast
---

You test provider health by sending minimal requests and reporting results.

## What To Test

For each provider in the failover chain (check behaviors/provider-resilience.yaml for the tier list):

1. **Connectivity**: Can we reach the API endpoint?
2. **Authentication**: Are credentials valid?
3. **Responsiveness**: How long does a minimal request take?
4. **Model availability**: Is the specific model available?

## How To Test

For each provider, send a minimal request: "Respond with exactly: OK"
- Measure wall-clock time
- Catch and classify any errors
- Report HTTP status codes when available

## Report Format

```
Provider Health Report
======================
Date: <timestamp>

| Provider  | Model             | Status | Latency | Details          |
|-----------|-------------------|--------|---------|------------------|
| anthropic | claude-opus-4-6   | OK     | 1.2s    |                  |
| anthropic | claude-sonnet-4-5 | OK     | 0.8s    |                  |
| openai    | gpt-5.4           | ERROR  | -       | 401 Unauthorized |

Summary: 2/3 providers healthy
Recommendation: Check OpenAI API key (OPENAI_API_KEY)
```
````

**Step 2: Commit**

```bash
git add agents/provider-health.md
git commit -m "feat: provider-health agent — test connectivity and latency"
```

---

### Task 13: Provider Diagnosis Recipe

**Files:**
- Create: `recipes/provider-diagnosis.yaml`

**Step 1: Create the recipe**

Create `recipes/provider-diagnosis.yaml`:

```yaml
name: provider-diagnosis
description: Test all configured providers and report health status

steps:
  - name: test-providers
    agent: provider-doctor:provider-health
    instruction: |
      Test each provider in the failover chain:

      Tier 1: Anthropic — claude-opus-4-6
      Tier 2: Anthropic — claude-sonnet-4-5
      Tier 3: OpenAI — gpt-5.4

      For each:
      1. Send a minimal request ("Respond with exactly: OK")
      2. Measure response time
      3. Report: provider, model, status (ok/error), latency, error details

      Format results as a table.

  - name: recommend
    agent: provider-doctor:provider-health
    instruction: |
      Based on the test results from the previous step, provide:

      1. Which providers are healthy and which are not
      2. Whether the failover chain will work correctly
      3. Specific action items for any failing providers:
         - Missing or invalid API keys
         - Quota or rate limit issues
         - Model availability problems
         - Network connectivity issues
      4. Overall resilience assessment: if the primary provider goes down,
         will the failover chain recover the session?
```

**Step 2: Commit**

```bash
git add recipes/provider-diagnosis.yaml
git commit -m "feat: provider-diagnosis recipe — test all providers, report health"
```

---

## Group 5: Support Tooling

### Task 14: Support Template

**Files:**
- Create: `context/support-template.md`

**Step 1: Create the template**

```bash
mkdir -p context
```

Create `context/support-template.md`:

```markdown
# Support Ticket

**Date:** {{date}}
**Session ID:** {{session_id}}
**Project:** {{project}}
**Bundle:** {{bundle}}

## Error Observed
{{error_description}}

## Diagnosis
- Provider: {{provider}}
- Error type: {{error_type}}
- Retryable: {{retryable}}
- Failover attempted: {{failover_attempted}}
- Tiers tried: {{tiers_tried}}

## Session State
- Transcript size: {{transcript_size}}
- Turn count: {{turns}}
- Last successful provider call: {{last_success}}

## Provider Health
{{provider_health_results}}

## Steps to Reproduce
{{reproduction_steps}}

## Attachments
- [ ] Session metadata (metadata.json)
- [ ] Error logs (last 50 lines of events.jsonl)
- [ ] Provider diagnosis output
```

**Step 2: Commit**

```bash
git add context/support-template.md
git commit -m "feat: support ticket template with structured diagnosis fields"
```

---

### Task 15: Support Agent

**Files:**
- Create: `agents/support.md`

**Step 1: Create the agent**

Create `agents/support.md`:

```markdown
---
meta:
  name: support
  description: >
    Captures diagnosis information and generates structured support tickets.
    Runs provider health checks, session analysis, and formats everything
    into a support note ready for filing.
model_role: fast
---

You help users create support tickets for Amplifier issues. When invoked:

## Workflow

1. **Gather context**:
   - Ask what error or problem the user is experiencing
   - If they provide a session ID, note it for diagnosis
   - Check which project/bundle they're using

2. **Run diagnostics** (if possible):
   - Suggest running the `provider-diagnosis` recipe to test connectivity
   - If a session ID is provided, suggest running `session-repair` in diagnose-only mode
   - Capture all diagnostic output

3. **Fill the support template**:
   - Read the template from `context/support-template.md`
   - Fill in all available fields from the diagnosis
   - Mark unknown fields as "Not available"

4. **Save the ticket**:
   - Write the filled template to `docs/support/YYYY-MM-DD-<topic>.md`
   - Create the `docs/support/` directory if it doesn't exist

5. **Summarize for the user**:
   - Show the key findings
   - Explain what information was captured
   - Suggest next steps (share the ticket file, contact support channel, etc.)

## Important

- Always include the raw error message and stack trace if available
- Include the provider health check results — they're the most useful diagnostic
- Be specific about which tier in the failover chain failed and why
- Don't speculate about causes — report what the diagnostics show
```

**Step 2: Commit**

```bash
git add agents/support.md
git commit -m "feat: support agent — generates structured support tickets with diagnosis"
```

---

### Task 16: Final — Push and Verify

**Step 1: Run all tests one final time**

```bash
cd ~/dev/amplifier-bundle-provider-doctor
python -m pytest tests/ -v
```
Expected: All tests pass.

**Step 2: Verify file structure**

```bash
find . -not -path './.git/*' -not -path './.venv/*' -not -name '.git' -not -name '.venv' | sort
```

Expected output should include:
```
./agents/provider-health.md
./agents/session-doctor.md
./agents/support.md
./behaviors/provider-resilience.yaml
./bundle.md
./context/support-template.md
./modules/provider-failover/provider_failover/__init__.py
./modules/provider-failover/provider_failover/failover.py
./modules/provider-failover/pyproject.toml
./pytest.ini
./recipes/provider-diagnosis.yaml
./recipes/session-repair.yaml
./tests/conftest.py
./tests/test_context_length.py
./tests/test_failover.py
./tests/test_failup.py
./tests/test_retry.py
./tests/test_stream.py
```

**Step 3: Push**

```bash
git push origin main
```

---

## Summary

| Task | Component | Type | Files |
|------|-----------|------|-------|
| 1 | Project scaffold | Setup | pyproject.toml, __init__.py, failover.py, conftest.py, pytest.ini |
| 2 | Happy path — complete() | TDD | test_retry.py, failover.py |
| 3 | Retry with backoff | TDD | test_retry.py, failover.py |
| 4 | Multi-tier fallback | TDD | test_failover.py |
| 5 | Fail-up probing | TDD | test_failup.py, failover.py |
| 6 | stream() proxy | TDD | test_stream.py, failover.py |
| 7 | ContextLengthError | TDD | test_context_length.py, failover.py |
| 8 | mount() function | Wiring | __init__.py |
| 9 | Bundle + behavior | YAML | bundle.md, provider-resilience.yaml |
| 10 | Session doctor agent | Markdown | session-doctor.md |
| 11 | Session repair recipe | YAML | session-repair.yaml |
| 12 | Provider health agent | Markdown | provider-health.md |
| 13 | Provider diagnosis recipe | YAML | provider-diagnosis.yaml |
| 14 | Support template | Markdown | support-template.md |
| 15 | Support agent | Markdown | support.md |
| 16 | Final verification + push | Ops | — |

**Total: 16 tasks, 6 test files, ~15 source files, 1 commit per task.**
