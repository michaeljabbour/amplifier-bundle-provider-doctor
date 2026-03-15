# Bundle Cache Corruption: Wrong Bundle Content in Amplifier Cache

**Date:** 2026-03-15
**Severity:** Critical — blocks all sessions using the affected bundle
**Symptom:** `Configuration must specify session.orchestrator` on session resume
**Root cause:** Recipe force-pushed wrong repo content to a bundle's GitHub remote

---

## What Happened

A recipe (`subagent-driven-development`) executed in the wrong working directory.
The recipe was building `amplifier-bundle-provider-doctor` but ran inside the
`amplifier-bundle-autoharness` repo (which is the source for `harness-machine`).

This caused a cascade of failures:

1. **Wrong commit target** — provider-doctor files were committed into the
   autoharness repo's git history
2. **Wrong remote push** — the recipe force-pushed to the autoharness remote
   (`github.com/michaeljabbour/amplifier-bundle-harness-machine`), overwriting
   the entire harness-machine repo with provider-doctor content
3. **Cache poisoned** — `amplifier bundle update harness-machine` re-fetched
   from GitHub, pulling the corrupted content into
   `~/.amplifier/cache/amplifier-bundle-harness-machine-*/`
4. **Sessions broken** — any session using `bundle: harness-machine` failed
   because the cached `bundle.md` was actually provider-doctor's config, which
   has no `session.orchestrator` defined

The error message was:

```
Error resuming session: Configuration must specify session.orchestrator
```

This was misleading — the bundle *does* define an orchestrator, but the cached
copy was from a completely different bundle.

---

## How to Diagnose

### Step 1: Check the cached bundle identity

```bash
head -5 ~/.amplifier/cache/amplifier-bundle-<name>-*/bundle.md
```

If the `name:` field doesn't match the expected bundle name, the cache is
corrupted. For example:

```yaml
# CORRUPTED — expected harness-machine, got provider-doctor
bundle:
  name: provider-doctor    # <- wrong!
```

### Step 2: Check the GitHub remote

```bash
curl -s https://raw.githubusercontent.com/<owner>/amplifier-bundle-<name>/main/bundle.md | head -5
```

If the remote also shows the wrong bundle name, the GitHub repo itself was
overwritten — not just the local cache.

### Step 3: Find the correct source

Check local clones for the original content:

```bash
# Search for repos with the correct bundle name
grep -r "name: <expected-name>" ~/dev/*/bundle.md
```

The local repo may still have the correct content even if the remote was
overwritten (force-push doesn't affect local clones that weren't pulled).

---

## How to Fix

### If the GitHub remote is corrupted

1. **Find the correct local source:**
   ```bash
   # The local clone still has the right content
   cd ~/dev/amplifier-bundle-<correct-local-repo>
   head -5 bundle.md  # verify name: matches expected
   ```

2. **Force-push the correct code back to GitHub:**
   ```bash
   git push origin main --force
   ```

3. **Clear the poisoned cache and re-fetch:**
   ```bash
   rm -rf ~/.amplifier/cache/amplifier-bundle-<name>-*
   amplifier bundle remove <name>
   amplifier bundle add git+https://github.com/<owner>/amplifier-bundle-<name>@main --app
   ```

4. **Verify the fix:**
   ```bash
   head -5 ~/.amplifier/cache/amplifier-bundle-<name>-*/bundle.md
   # Should show the correct name now
   ```

### If only the local cache is corrupted

Skip steps 1-2 above. Just clear and re-fetch:

```bash
rm -rf ~/.amplifier/cache/amplifier-bundle-<name>-*
amplifier bundle update <name>
```

---

## Actual Fix Applied (2026-03-15)

```bash
# 1. Verified local clone had correct content
cd ~/dev/amplifier-bundle-autoharness
head -5 bundle.md  # name: harness-machine

# 2. Force-pushed correct code to GitHub
git push origin main --force

# 3. Cleared cache and re-registered
rm -rf ~/.amplifier/cache/amplifier-bundle-harness-machine-*
amplifier bundle remove harness-machine
amplifier bundle add git+https://github.com/michaeljabbour/amplifier-bundle-harness-machine@main --app

# 4. Verified
head -5 ~/.amplifier/cache/amplifier-bundle-harness-machine-*/bundle.md
# bundle:
#   name: harness-machine
```

---

## Prevention

- **Verify `working_dir` before recipe execution.** If a recipe is building
  bundle X, confirm the working directory is the correct repo for bundle X,
  not some other bundle's repo.
- **Check git remote before force-push.** Run `git remote -v` and confirm the
  remote URL matches the repo you intend to push to.
- **Never force-push in recipes without safeguards.** Consider adding a
  pre-push check that compares `bundle.md` name against the repo name in the
  remote URL.
- **Monitor bundle cache identity.** After `bundle update`, spot-check that
  `head -5 ~/.amplifier/cache/*/bundle.md` shows expected bundle names.
