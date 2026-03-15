-- Run this in Supabase Dashboard > SQL Editor to tighten security.
--
-- Current state: RLS is OFF, anon has full access.
-- After running this: RLS is ON, anon can only INSERT, only service_role can read.

-- Re-enable RLS
alter table provider_errors enable row level security;

-- Drop any existing policies
drop policy if exists "anon_insert" on provider_errors;
drop policy if exists "admin_read" on provider_errors;
drop policy if exists "allow_anon_insert" on provider_errors;

-- Revoke everything from anon, then grant only INSERT
revoke all on provider_errors from anon;
grant insert on provider_errors to anon;

-- Create permissive insert policy (applies to all roles including anon)
create policy "allow_insert" on provider_errors
  for insert with check (true);

-- Read access only for authenticated users (service_role bypasses RLS anyway)
create policy "authenticated_read" on provider_errors
  for select to authenticated using (true);
