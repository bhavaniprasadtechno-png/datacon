# Supabase JWT Signing Key Migration (HS256 → ES256) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note on task shape:** per the approved design (`docs/superpowers/specs/2026-07-28-supabase-jwt-signing-key-migration-design.md`), this plan has **zero application code changes** — it is a Supabase Dashboard operations runbook plus a verification pass. There is no test-driven-development cycle because there is no code to unit test; each task instead carries its own **precondition check → action → verification** cycle, which serves the same "prove it before moving on" purpose TDD steps normally serve.
>
> **Note on execution mode:** the Dashboard actions (Tasks 2, 3, 5) can only be performed by a human with Dashboard access — no Supabase CLI or MCP tool covers signing-key rotation (verified via `supabase --help`, `supabase gen --help`, `supabase projects --help`). A subagent cannot do these steps; the controller session coordinates directly with the user for those, and may dispatch a subagent only for the verification work in Task 4 that runs from the terminal (curl/decode).

**Goal:** Eliminate the ~1.1-1.2s latency on every API call by migrating the Supabase project's JWT signing key from the legacy symmetric HS256 secret to an asymmetric ES256 key, so `getClaims()` verifies tokens locally instead of round-tripping to Supabase's Auth server on every request.

**Architecture:** No code changes (see design doc, "Design → Components touched"). `api/src/auth/guards/supabase-auth.guard.ts:20` already calls `auth.getClaims(token)`, which auto-detects the JWT's `alg` header at verification time. The fix is entirely an infrastructure change: rotate the project's active signing key in the Supabase Dashboard (Project Settings → JWT Keys). Zero-downtime, fully reversible up to the final revoke step. The frontend (`web/src/api/client.ts`) is untouched — confirmed it performs no auth logic today, only attaches the session token it's given.

**Tech Stack:** Supabase Auth (GoTrue) JWT Keys system, `supabase-js` `auth.getClaims()`, Supabase Dashboard.

## Global Constraints

(Copied verbatim from the design doc's "Execution constraints" section.)

- No code changes — migration only, not a `SupabaseAuthGuard`/`CurrentUserGuard` split.
- Dashboard steps (Migrate/Create/Rotate/Revoke) are performed by the user, not automated — no Supabase CLI or MCP tool covers this.
- Revoke requires an explicit user go-ahead after the wait window — never automatic.
- Project: `datacon-staging-ew`, ref `yicblouwgguhmfvwqdhm`, region `ap-southeast-1`.

---

### Task 1: Confirm current signing-key state and access-token TTL

**Files:** none (read-only Dashboard check)

**Interfaces:**
- Consumes: nothing
- Produces: `current_key_algorithm` (expected: HS256/legacy), `access_token_ttl_seconds` (expected default: 3600) — both used by Task 5's wait-time calculation.

- [ ] **Step 1: Navigate to JWT Keys settings**

Dashboard → project `datacon-staging-ew` → Settings → API → **JWT Keys** tab.

- [ ] **Step 2: Confirm precondition**

Expected: a single legacy secret shown, no algorithm badge or a plain "HS256"/"Legacy" label, no separate Standby/In Use/Previously Used keys yet. This confirms the root-cause diagnosis (symmetric key forcing `getClaims()` to fall back to network `getUser()` calls).

If this does NOT match (e.g. an ES256 key already exists and is In Use) — stop, the root cause may be different; re-open investigation instead of proceeding.

- [ ] **Step 3: Record access-token TTL**

Dashboard → Authentication → Sessions (or Auth settings) → note "Access token expiry" value in seconds. No `supabase/config.toml` exists in this repo (hosted-only project, confirmed via `Glob **/supabase/config.toml` → no results), so there is no local override to check — the Dashboard value is authoritative.

- [ ] **Step 4: Checkpoint**

Report back: current key algorithm, and TTL value. This TTL feeds directly into Task 5's wait duration.

---

### Task 2: Migrate legacy secret into the new keys system

**Files:** none

**Interfaces:**
- Consumes: `current_key_algorithm` = HS256 (from Task 1)
- Produces: project is now on the new JWT Keys system, HS256 secret is the "Current" key (no behavior change yet)

- [ ] **Step 1: Click Migrate**

Dashboard → Settings → API → JWT Keys → **"Migrate JWT secret"** button.

- [ ] **Step 2: Verify no behavior change**

Immediately after, hit any guarded endpoint (e.g. `GET /documents` with a valid bearer token) and confirm it still returns 200 with the same ~1.1-1.2s latency as before. This step should be a no-op for behavior — only confirms the migration didn't break anything.

- [ ] **Step 3: Checkpoint**

Confirm with user that the Dashboard now shows the legacy secret as the "Current" key under the new system, before proceeding to Task 3.

---

### Task 3: Create ES256 standby key and rotate

**Files:** none

**Interfaces:**
- Consumes: migrated key system state (from Task 2)
- Produces: new ES256 key in "In Use" state, old HS256 key in "Previously Used" state

- [ ] **Step 1: Create standby key**

JWT Keys panel → create new signing key → algorithm **ES256**. Confirm it appears with state **Standby**.

- [ ] **Step 2: Rotate**

Click **Rotate**. Confirm the ES256 key's state changes to **In Use**, and the old HS256 key's state changes to **Previously Used** (automatic on rotate — not a separate manual step).

- [ ] **Step 3: Checkpoint**

Report both keys' states back before moving to verification (Task 4).

---

### Task 4: Verify the fix

**Files:** none (verification only — this is the one task a subagent may run, given it's terminal-only work with no Dashboard access needed)

**Interfaces:**
- Consumes: rotated key state (from Task 3), `access_token_ttl_seconds` (from Task 1)
- Produces: confirmed latency fix, computed safe revoke time for Task 5

- [ ] **Step 1: Get a freshly-signed token**

User logs out/in again in the app (or waits for the client's silent token refresh) so the browser holds a token signed by the new ES256 key. User provides the token to the controller/subagent.

- [ ] **Step 2: Confirm the new token's algorithm**

```bash
echo "$ACCESS_TOKEN" | cut -d. -f1 | base64 -d
```

Expected output includes `"alg":"ES256"`. If it still shows `"alg":"HS256"`, the client is still holding an old token — go back to Step 1.

- [ ] **Step 3: Confirm latency dropped**

```bash
curl -s -o /dev/null -w "%{time_total}\n" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://<api-host>/documents
```

Expected: well under 200ms (previously ~1.1-1.2s). Repeat for `/users`, `/roles`, `/connectors`, `/catalog` to confirm the fix applies uniformly (matches the original diagnosis that all guarded routes shared the same bottleneck).

- [ ] **Step 4: Spot-check unrelated guarded routes didn't regress**

Repeat the same curl check against `/forecasts`, `/insights`, `/chat` — same guard pattern (`SupabaseAuthGuard` + `PermissionsGuard`), confirm they also return fast and correctly.

- [ ] **Step 5: Checkpoint**

Report latency numbers before/after for all checked routes. Do not proceed to Task 5 until this is confirmed working — Task 5 involves the irreversible revoke step.

---

### Task 5: Revoke the old HS256 key (gated — explicit go-ahead required)

**Files:** none

**Interfaces:**
- Consumes: verified fix (from Task 4), `access_token_ttl_seconds` (from Task 1)
- Produces: old HS256 key state = Revoked (project fully off the legacy secret)

- [ ] **Step 1: Compute safe wait window**

Wait time = `access_token_ttl_seconds` + buffer. Example: if TTL = 3600s (1h), wait **at least 1h15m** past the Task 3 rotation time before revoking, so no user still holding an unexpired HS256-signed token gets force-signed-out.

- [ ] **Step 2: Wait**

Do not proceed until the wait window from Step 1 has elapsed.

- [ ] **Step 3: Explicit check-in — REQUIRED before Step 4**

Ask the user directly: "Wait window has passed and the fix is confirmed working. Revoke the old HS256 key now?" Do not proceed on assumption or timeout — this must be an explicit yes from the user.

- [ ] **Step 4: Revoke**

Only after user confirms: Dashboard → JWT Keys → old HS256 key ("Previously Used") → **Revoke**.

- [ ] **Step 5: Final verification**

Re-run the Task 4 Step 3 latency checks once more, and confirm no active sessions broke (spot-check the app is still usable end-to-end: login, navigate to a guarded page).

- [ ] **Step 6: Checkpoint**

Report final state: old key Revoked, all routes verified fast, no regressions. Migration complete.

---

## Rollback (if anything breaks before Task 5 Step 4)

Every key state is reversible except permanent deletion (per Supabase's own docs). If the app breaks after Rotate (Task 3) but before Revoke (Task 5):
1. Dashboard → JWT Keys → move the ES256 key back to Standby.
2. Rotate again — this promotes the old HS256 key (still in "Previously Used", not yet revoked) back to "In Use".
3. This instantly restores the pre-migration behavior (slow, but working) while the ES256 key issue is investigated.

This rollback path is only available **before** Task 5's revoke — which is exactly why revoke is gated behind an explicit user check-in rather than a timer.
