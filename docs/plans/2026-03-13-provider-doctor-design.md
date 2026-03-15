# amplifier-bundle-provider-doctor — Design

## Goal

A single Amplifier bundle that makes sessions resilient to provider failures, recovers
broken sessions, and provides support tooling. Zero upstream changes required. Survives
`amplifier reset`.

## Background

### The Problem

Amplifier sessions are fragile in three ways:

1. **Provider failures kill sessions.** A 529 "overloaded" from Anthropic crashes the
   session with no retry, no failover. Meanwhile, curl and Claude Code work fine because
   they send smaller payloads and/or retry with backoff.

2. **Broken sessions are unrecoverable without manual surgery.** Orphaned tool calls,
   ordering violations, and oversized transcripts require hand-editing events.jsonl — a
   process that took 3 repair attempts and deep investigation to get right.

3. **No self-service support path.** When things go wrong, diagnosis requires deep
   ecosystem knowledge (which module failed, why, what the error taxonomy means). There's
   no structured way to capture diagnosis and queue support.

### Design Constraints

- **All changes local** — nothing in upstream amplifier repos
- **Survives `amplifier reset`** — lives in `~/dev/` or project `.amplifier/`, not in
  `~/.amplifier/cache/`
- **Composable** — works with any root bundle via `includes:`
- **No kernel or orchestrator changes** — pure bundle-level solution

## Architecture

```
amplifier-bundle-provider-doctor/
├── bundle.md                              # Root bundle (thin — includes behaviors)
├── behaviors/
│   └── provider-resilience.yaml           # Composable behavior: failover provider
├── modules/
│   └── provider-failover/                 # Python module: Provider protocol proxy
│       ├── pyproject.toml
│       └── provider_failover/
│           ├── __init__.py                # mount() entry point
│           └── failover.py                # FailoverProvider class
├── agents/
│   ├── session-doctor.md                  # Agent: diagnose + repair sessions
│   └── provider-health.md                 # Agent: test provider connectivity
├── recipes/
│   ├── session-repair.yaml                # Recipe: automated session diagnosis + repair
│   └── provider-diagnosis.yaml            # Recipe: test all providers, report status
├── context/
│   └── support-template.md                # Template for filing support tickets
└── docs/
    └── plans/
        └── 2026-03-13-provider-doctor-design.md  # This file
```

## Component 1: Provider Failover Module

### Concept

A Python module implementing the `Provider` protocol that proxies to a chain of real
providers. The orchestrator sees ONE provider. Failover is invisible.

### Failover Chain (Tiered, with Fail-Up)

```
Session starts
    │
    ▼
┌─ Tier 1: claude-opus-4-6 (primary) ◄──────────────────────┐
│  Retry 3x with backoff (2s, 4s, 8s)                       │
│  On 3 consecutive failures ──▶ fall to Tier 2              │
└─────────────────────────────────────────────────────────────┘
                                                    probe-up │
┌─ Tier 2: claude-sonnet-4-5 (same provider, lighter model)  │
│  Retry 3x with backoff (2s, 4s, 8s)                       │
│  On 3 consecutive failures ──▶ fall to Tier 3              │
│  Every Nth successful call ──▶ probe Tier 1 ───────────────┘
└─────────────────────────────────────────────────────────────┘
                                                    probe-up │
┌─ Tier 3: openai gpt-5.4 (different provider entirely)      │
│  Retry 3x with backoff (2s, 4s, 8s)                       │
│  On 3 consecutive failures ──▶ raise (all tiers exhausted) │
│  Every Nth successful call ──▶ probe Tier 2 ───────────────┘
└─────────────────────────────────────────────────────────────┘
```

### Fail-Up (Probe-Back) Logic

After falling to a lower tier, the provider periodically probes back up:

- **Probe interval**: Every 5 successful calls on the current tier, try the tier above
- **Probe is non-destructive**: If the probe fails, stay on current tier, reset probe
  counter. No penalty.
- **Probe succeeds**: Move back up, reset failure counters for the restored tier
- **Always aims for Tier 1**: The intended model is always the goal

### Retry Within a Tier

Each tier retries on `retryable` LLMErrors (ProviderUnavailableError, RateLimitError,
StreamError, LLMTimeoutError) using exponential backoff:

```
Attempt 1 → fail → wait 2s
Attempt 2 → fail → wait 4s
Attempt 3 → fail → wait 8s
All 3 failed → fall to next tier
```

Non-retryable errors (AuthenticationError, ContentFilterError) skip retry and fall
immediately.

### ContextLengthError Handling

ContextLengthError is special — falling to a different model won't help if the payload
is too large. On ContextLengthError:

1. Log a clear message: "Context window exceeded for {model}. Transcript too large."
2. If the next tier has a LARGER context window, try it
3. Otherwise, raise with an actionable message: "Start a new session."

### Provider Protocol Implementation

```python
class FailoverProvider:
    """Implements Provider protocol. Proxies to a chain of real providers."""

    @property
    def name(self) -> str:
        return f"failover({self._active_tier().label})"

    def get_info(self) -> ProviderInfo:
        return self._active_tier().provider.get_info()

    async def complete(self, request: ChatRequest, **kwargs) -> ChatResponse:
        return await self._call_with_failover("complete", request, **kwargs)

    async def stream(self, request: ChatRequest, **kwargs):
        # stream() is duck-typed, not in Provider protocol
        return await self._call_with_failover("stream", request, **kwargs)

    def parse_tool_calls(self, response: ChatResponse) -> list[ToolCall]:
        return self._active_tier().provider.parse_tool_calls(response)

    async def _call_with_failover(self, method, request, **kwargs):
        """Core failover logic — retry within tier, fall between tiers, probe up."""
        ...
```

### Configuration

```yaml
providers:
  - module: provider-failover
    source: ./modules/provider-failover
    config:
      max_failures: 3          # consecutive failures before falling to next tier
      retry_base_delay: 2      # seconds (exponential: 2, 4, 8)
      probe_interval: 5        # successful calls before probing tier above
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

### Token Estimation (Absorbed from Closed PR #11)

The failover module logs estimated vs actual token counts when available (from provider
usage responses). This gives visibility into compaction accuracy without modifying
context-simple upstream. If the response includes `usage.input_tokens`, log:

```
[FAILOVER] Tier opus: request succeeded (input_tokens=142,350, est=~{chars/3})
```

This is observability, not enforcement — the context module still owns compaction.

## Component 2: Session Doctor Agent + Recipe

### Agent: session-doctor

An agent that diagnoses and repairs broken sessions. Wraps the session-analyst agent
with repair-specific instructions.

```yaml
# agents/session-doctor.md
---
meta:
  name: session-doctor
  description: >
    Diagnoses and repairs broken Amplifier sessions. Checks for orphaned tool calls,
    ordering violations, oversized transcripts, and other structural issues. Can
    perform repairs (inject synthetic results, rewind transcripts) with backup.
model_role: fast
---

You are a session repair specialist. When given a session ID:

1. Locate the session directory
2. Analyze transcript.jsonl for structural issues
3. Report findings with severity
4. If repair is requested, create a backup and apply the minimal fix
5. Verify the repair

Always create backups before any modification. Default to REPAIR (inject synthetic
entries) over REWIND (truncate). Only rewind when explicitly requested.
```

### Recipe: session-repair

```yaml
# recipes/session-repair.yaml
name: session-repair
description: Diagnose and repair a broken session

steps:
  - name: diagnose
    agent: provider-doctor:session-doctor
    instruction: |
      Analyze session {{session_id}} for structural issues.
      Report: orphaned tool calls, ordering violations, transcript size.
      Recommend: repair strategy (if needed).

  - name: repair
    agent: provider-doctor:session-doctor
    condition: "{{diagnose.needs_repair}}"
    instruction: |
      Apply the recommended repair to session {{session_id}}.
      Create backup first. Verify after repair.
```

## Component 3: Provider Health Agent + Recipe

### Agent: provider-health

Tests connectivity and responsiveness of configured providers.

```yaml
# agents/provider-health.md
---
meta:
  name: provider-health
  description: >
    Tests provider connectivity and responsiveness. Sends minimal test requests
    to each configured provider and reports latency, errors, and availability.
model_role: fast
---

You test provider health by sending minimal requests and reporting results.
For each provider: send "respond with OK", measure latency, report status.
```

### Recipe: provider-diagnosis

```yaml
# recipes/provider-diagnosis.yaml
name: provider-diagnosis
description: Test all configured providers and report health

steps:
  - name: test-providers
    agent: provider-doctor:provider-health
    instruction: |
      Test each provider in the failover chain:
      1. Send a minimal request ("respond with OK")
      2. Measure response time
      3. Report: provider, model, status (ok/error), latency, error details
      Format as a table.

  - name: report
    agent: provider-doctor:provider-health
    instruction: |
      Based on the test results, recommend:
      - Which providers are healthy
      - Whether the failover chain is correctly configured
      - Any action items (API keys, quotas, model availability)
```

## Component 4: @support Capabilities

### Support Template

A structured template for capturing diagnosis information when filing support:

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

### Support Agent

```yaml
# agents/support.md
---
meta:
  name: support
  description: >
    Captures diagnosis information and generates structured support tickets.
    Runs provider health checks, session analysis, and formats everything
    into a support note ready for filing.
model_role: fast
---

You help users create support tickets. When invoked:
1. Run provider-diagnosis recipe to test connectivity
2. If a session ID is provided, run session-repair recipe in diagnose-only mode
3. Capture all findings into the support template
4. Write the support note to docs/support/YYYY-MM-DD-<topic>.md
5. Summarize the ticket for the user
```

## Bundle Composition

### Root Bundle (thin)

```yaml
# bundle.md
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

- **Provider failover**: Tiered failover with retry, backoff, and fail-up
- **Session repair**: Diagnose and fix broken sessions
- **Provider health**: Test provider connectivity
- **Support**: Generate structured support tickets
```

### Behavior (composable)

```yaml
# behaviors/provider-resilience.yaml
bundle:
  name: provider-resilience
  version: 0.1.0

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

## How to Use

### Per-project (survives reset)

```yaml
# In your project's .amplifier/bundle.md or root bundle:
includes:
  - bundle: foundation
  - bundle: ~/dev/amplifier-bundle-provider-doctor
```

### Via source override (development)

```bash
amplifier source add provider-doctor ~/dev/amplifier-bundle-provider-doctor --local
```

### Session repair

```bash
# In a session:
"run the session-repair recipe for session abc123"

# Or invoke the agent directly:
"ask session-doctor to check session abc123"
```

### Provider health check

```bash
"run provider-diagnosis"
"check if anthropic is healthy"
```

### File a support ticket

```bash
"create a support ticket for the overloaded errors I've been seeing"
```

## What This Does NOT Touch

- No amplifier-core changes
- No orchestrator (loop-streaming) changes
- No context module (context-simple) changes
- No kernel changes
- No hook system changes
- No routing matrix changes
