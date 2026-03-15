-- Add latency and source columns for hook-based telemetry.
--
-- latency_ms: request-to-error duration in milliseconds (NULL if unmeasured)
-- source:     "failover" (from FailoverProvider) or "hook" (from hooks-telemetry)
--
-- Run this in Supabase Dashboard > SQL Editor.

alter table provider_errors add column if not exists latency_ms int;
alter table provider_errors add column if not exists source text default 'failover';
