-- Create the broader telemetry_events table for ALL error/failure events
-- across the Amplifier ecosystem (not just provider errors).
--
-- Run this in Supabase Dashboard > SQL Editor.

create table if not exists telemetry_events (
  id            uuid default gen_random_uuid() primary key,
  created_at    timestamptz default now() not null,

  -- Machine fingerprint (hashed, no PII)
  machine_hash  text not null,

  -- Event identification
  event_type    text not null,           -- 'provider:error', 'tool:error', 'provider:retry', etc.
  event_category text not null,          -- 'error', 'retry', 'throttle', 'cancel', 'repair'

  -- Provider context (nullable — not all events are provider-related)
  provider      text,
  model         text,

  -- Error details
  error_type    text,                    -- 'ProviderUnavailableError', 'RateLimitError', etc.
  error_message text,                    -- truncated to 500 chars
  status_code   smallint,
  retryable     boolean,

  -- Retry context (for provider:retry events)
  attempt       smallint,
  max_retries   smallint,
  retry_delay   real,                    -- seconds
  retry_after   real,                    -- from Retry-After header

  -- Throttle context (for provider:throttle events)
  throttle_reason    text,               -- 'input_tokens_low', 'requests_low'
  throttle_dimension text,               -- 'requests', 'input_tokens', 'output_tokens'
  throttle_remaining int,
  throttle_limit     int,
  throttle_ratio     real,

  -- Tool context (for tool:error events)
  tool_name     text,

  -- Request metrics
  prompt_tokens int,
  message_count int,
  tool_count    int,
  latency_ms    int,

  -- Session/execution context
  execution_status text,                 -- 'success', 'error', 'cancelled', 'incomplete'

  -- Client context (no PII)
  client        text default 'amplifier',
  bundle_name   text,
  os_platform   text,
  os_version    text,
  source        text default 'hook'      -- 'hook', 'failover'
);

-- No RLS for now (tighten later with sql/001_tighten_rls.sql pattern)
-- Grant insert to anon so the hook can POST via the anon key
grant usage on schema public to anon;
grant insert on telemetry_events to anon;
