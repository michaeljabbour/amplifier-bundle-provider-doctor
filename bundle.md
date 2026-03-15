---
bundle:
  name: provider-doctor
  version: 0.1.0
  description: |
    Provider resilience, session repair, and support tooling for Amplifier agents.
    Provides automatic provider failover across model tiers, session recovery
    from interrupted or corrupted runs, and diagnostic support for provider
    health monitoring. Keeps agents running through provider outages and
    context-length failures without manual intervention.

includes:
  - behavior: behaviors/provider-resilience.yaml

agents:
  declare:
    - name: session-doctor
      path: ./agents/session-doctor.md
    - name: provider-health
      path: ./agents/provider-health.md
    - name: support
      path: ./agents/support.md
---

# Provider Doctor

Resilience and recovery tooling for Amplifier agents — automatic provider failover,
session repair, and health diagnostics.

## Capabilities

### Provider Resilience

The `provider-resilience` behavior mounts a multi-tier failover provider that
automatically routes requests through a priority-ordered chain of providers.
When the primary provider fails or exhausts its context window, requests
cascade to the next available tier without session interruption.

Provider-level retry (transient errors, rate limits, backoff, jitter) is handled
by each provider internally via `retry_with_backoff()`. This module adds value
through **failover to different models/providers**, not through redundant retry
that would cause amplification.

Configured tiers (in priority order):

| Tier | Provider | Model | Label |
|------|----------|-------|-------|
| 1 | provider-anthropic | claude-opus-4-6 | opus |
| 2 | provider-anthropic | claude-sonnet-4-5 | sonnet |
| 3 | provider-openai | gpt-5.4 | openai-codex |

### Session Repair

The `session-doctor` agent diagnoses and repairs interrupted or corrupted
Amplifier sessions — fixing orphaned tool calls, ordering violations, and
incomplete assistant turns so sessions can be resumed cleanly.

### Provider Health

The `provider-health` agent monitors provider availability, measures latency
and error rates across configured providers, and surfaces actionable
diagnostics when a provider degrades or becomes unavailable.

### Support

The `support` agent provides user-facing guidance for diagnosing provider
errors, session failures, and configuration issues across the bundle.

## Available Agents

| Agent | Purpose |
|-------|---------|
| `provider-doctor:session-doctor` | Repairs interrupted or corrupted agent sessions |
| `provider-doctor:provider-health` | Monitors and diagnoses provider availability |
| `provider-doctor:support` | User-facing support and diagnostic guidance |
