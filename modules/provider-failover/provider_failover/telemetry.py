"""Fire-and-forget provider error telemetry.

Reports provider errors to a community Supabase database for aggregate
analysis.  No PII, no prompts, no responses — just structured diagnostic
data about provider failures.

Telemetry is silently disabled if SUPABASE_URL or SUPABASE_ANON_KEY
environment variables are not set.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
import socket
import urllib.request
import uuid

logger = logging.getLogger(__name__)

# --- Machine fingerprint (computed once, hashed, no PII) -----------------


def _machine_hash() -> str:
    """SHA-256 hash of MAC address + hostname.  Not reversible."""
    mac = hex(uuid.getnode())
    hostname = socket.gethostname()
    return hashlib.sha256(f"{mac}:{hostname}".encode()).hexdigest()[:16]


_MACHINE_HASH = _machine_hash()
_OS_PLATFORM = platform.system().lower()  # 'darwin', 'linux', 'windows'
_OS_VERSION = platform.platform()  # 'macOS-26.3-arm64-arm-64bit'

# --- Auto-load .env from bundle root (no dependencies) -------------------


def _load_dotenv() -> None:
    """Load .env file from bundle root if it exists. No dependencies needed."""
    import pathlib as _pathlib

    current = _pathlib.Path(__file__).resolve()
    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.is_file():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    # Only set if not already in environment (don't override)
                    if key and key not in os.environ:
                        os.environ[key] = value
            break


_load_dotenv()

# --- Supabase config from env --------------------------------------------

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
_ENABLED = bool(_SUPABASE_URL and _SUPABASE_ANON_KEY)
_ENDPOINT = f"{_SUPABASE_URL}/rest/v1/provider_errors" if _ENABLED else ""
_EVENTS_ENDPOINT = (
    f"{_SUPABASE_URL}/rest/v1/telemetry_events" if _ENABLED else ""
)


# --- Sync HTTP POST (runs in a thread) -----------------------------------


def _post_sync(
    payload: dict,  # type: ignore[type-arg]
    endpoint: str | None = None,
) -> None:
    """Blocking POST to Supabase.  Runs in a thread via asyncio.to_thread."""
    url = endpoint or _ENDPOINT
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "apikey": _SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {_SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=2)  # noqa: S310 — URL is from env config


# --- Public async API: report_error (legacy, provider_errors table) -------


async def report_error(
    *,
    provider: str,
    model: str,
    tier_label: str | None = None,
    tier_index: int | None = None,
    error_type: str,
    error_message: str | None = None,
    status_code: int | None = None,
    retryable: bool | None = None,
    prompt_tokens: int | None = None,
    message_count: int | None = None,
    tool_count: int | None = None,
    has_streaming: bool | None = None,
    failover_from: str | None = None,
    failover_to: str | None = None,
    tiers_tried: int | None = None,
    client: str = "amplifier",
    bundle_name: str | None = None,
    latency_ms: int | None = None,
    source: str | None = None,
) -> None:
    """Fire-and-forget: report a provider error to the telemetry database.

    Never raises.  Never blocks longer than 2 seconds.  Silently no-ops
    if Supabase is not configured.
    """
    if not _ENABLED:
        return

    payload = {
        "machine_hash": _MACHINE_HASH,
        "provider": provider,
        "model": model,
        "tier_label": tier_label,
        "tier_index": tier_index,
        "error_type": error_type,
        "error_message": error_message,
        "status_code": status_code,
        "retryable": retryable,
        "prompt_tokens": prompt_tokens,
        "message_count": message_count,
        "tool_count": tool_count,
        "has_streaming": has_streaming,
        "failover_from": failover_from,
        "failover_to": failover_to,
        "tiers_tried": tiers_tried,
        "client": client,
        "bundle_name": bundle_name,
        "latency_ms": latency_ms,
        "source": source,
        "os_platform": _OS_PLATFORM,
        "os_version": _OS_VERSION,
    }
    # Strip None values so Supabase uses column defaults
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        await asyncio.wait_for(
            asyncio.to_thread(_post_sync, payload),
            timeout=2.0,
        )
        logger.debug(
            "telemetry: reported %s on %s/%s", error_type, provider, model
        )
    except Exception:
        # Silent — telemetry must never impact the session
        logger.debug(
            "telemetry: failed to report (silenced)", exc_info=True
        )

    # Also mirror to telemetry_events table for unified querying
    try:
        await report_event(
            event_type="provider:error",
            event_category="error",
            provider=provider,
            model=model,
            error_type=error_type,
            error_message=error_message,
            status_code=status_code,
            retryable=retryable,
            prompt_tokens=prompt_tokens,
            message_count=message_count,
            tool_count=tool_count,
            latency_ms=latency_ms,
            client=client,
            bundle_name=bundle_name,
            source=source or "failover",
        )
    except Exception:
        pass  # telemetry must never impact the session


# --- Public async API: report_event (new, telemetry_events table) ---------


async def report_event(
    *,
    event_type: str,
    event_category: str,
    provider: str | None = None,
    model: str | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    status_code: int | None = None,
    retryable: bool | None = None,
    attempt: int | None = None,
    max_retries: int | None = None,
    retry_delay: float | None = None,
    retry_after: float | None = None,
    throttle_reason: str | None = None,
    throttle_dimension: str | None = None,
    throttle_remaining: int | None = None,
    throttle_limit: int | None = None,
    throttle_ratio: float | None = None,
    tool_name: str | None = None,
    prompt_tokens: int | None = None,
    message_count: int | None = None,
    tool_count: int | None = None,
    latency_ms: int | None = None,
    execution_status: str | None = None,
    client: str = "amplifier",
    bundle_name: str | None = None,
    source: str = "hook",
) -> None:
    """Fire-and-forget: report any event to the telemetry_events table.

    Never raises.  Never blocks longer than 2 seconds.  Silently no-ops
    if Supabase is not configured.
    """
    if not _ENABLED:
        return

    payload = {
        "machine_hash": _MACHINE_HASH,
        "event_type": event_type,
        "event_category": event_category,
        "provider": provider,
        "model": model,
        "error_type": error_type,
        "error_message": error_message,
        "status_code": status_code,
        "retryable": retryable,
        "attempt": attempt,
        "max_retries": max_retries,
        "retry_delay": retry_delay,
        "retry_after": retry_after,
        "throttle_reason": throttle_reason,
        "throttle_dimension": throttle_dimension,
        "throttle_remaining": throttle_remaining,
        "throttle_limit": throttle_limit,
        "throttle_ratio": throttle_ratio,
        "tool_name": tool_name,
        "prompt_tokens": prompt_tokens,
        "message_count": message_count,
        "tool_count": tool_count,
        "latency_ms": latency_ms,
        "execution_status": execution_status,
        "client": client,
        "bundle_name": bundle_name,
        "source": source,
        "os_platform": _OS_PLATFORM,
        "os_version": _OS_VERSION,
    }
    # Strip None values so Supabase uses column defaults
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        await asyncio.wait_for(
            asyncio.to_thread(_post_sync, payload, _EVENTS_ENDPOINT),
            timeout=2.0,
        )
        logger.debug(
            "telemetry: reported event %s/%s",
            event_type,
            event_category,
        )
    except Exception:
        # Silent — telemetry must never impact the session
        logger.debug(
            "telemetry: failed to report event (silenced)", exc_info=True
        )
