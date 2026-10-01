# Security & Code Audit #5
**Date:** 2026-10-01

## GitHub repository password check — Clean

Per explicit request, independently verified via a **fresh clone from GitHub** (not relying on any local cache):

| Check | Result |
|---|---|
| Old password (`aditya@2004`) anywhere in any of the 23 commits | **0 occurrences** |
| Temporary rotation password anywhere in history | **0 occurrences** |
| Broad scan for other secret patterns (API keys, DB connection strings, private keys) across all history | Only placeholder/example values found (`"your-app-password"`, generic `postgres` default) — nothing real |
| `.env` tracked at any point, ever | No |
| Any `.pem`/`.key`/credential-shaped file currently tracked | No |

**The repository is clean of exposed credentials, past and present.**

---

## Codebase findings — 2 real, currently-active bugs found and fixed

### 1. 🔴 Jobs were being silently and permanently lost on every fetch (data loss, currently happening)
**File:** `api.py`

Caught this live in the server logs: `category`/`country` columns (`VARCHAR(100)`) were too narrow for real scraped data (e.g. Himalayas jobs with multi-tag categories, multi-country postings), causing MySQL error 1406 ("Data too long for column") on a meaningful fraction of inserts — verified **6 failed inserts in a single 181-job fetch** before the fix. Each failure was caught per-row and logged, but the job was gone for good: next fetch, same URL, same oversized value, same failure, forever.

**Root cause investigation surfaced more schema drift than expected:** `country` was actually `VARCHAR(100)` live (narrower than even the old code's `VARCHAR(255)` DDL), and the table was missing `idx_source`/`idx_work_type`/`idx_country` entirely — all three index-creation statements had silently never run against this table, in addition to the already-known column-width problem.

**Fix (two layers, since the first attempt alone wasn't sufficient):**
1. Widened `category`/`country`/`location` to `VARCHAR(500)` in both the base DDL (fresh installs) and a migration in `init_db()` for existing databases — this caught the first run's mistake too: the migration assumed `idx_country` already existed and tried to unconditionally `DROP INDEX idx_country`, which crashed startup entirely against the real database (which didn't have that index). Fixed by checking `SHOW INDEX FROM jobs` first and only dropping/recreating what's actually present, then separately ensuring all three expected indexes exist if missing.
2. **Even VARCHAR(500) wasn't enough** — one Himalayas job's joined location list still exceeded it after the width fix. Rather than guessing an ever-larger number (which just delays the same failure mode), added defensive **truncation at the application layer**: every field is truncated to its column's known max length before insert, in `save_jobs_to_db()`. This makes the entire bug class permanently impossible regardless of what any current or future scraper produces, for every field, not just the three that happened to overflow so far.

**Verified live, end to end:** re-fetched Himalayas 3 times through this investigation — before any fix: 6 failures per fetch; after the width fix alone: 1 failure (the oversized location); after adding truncation: **0 failures, 173/173 jobs saved**.

### 2. 🟡 `/api/fetch`'s `total_stored` count didn't reflect actual persistence
**File:** `api.py`

`save_jobs_to_db()` returned a bare `True`/`False` for the whole batch; `/api/fetch`'s response used `len(jobs)` (the attempted count) for `total_stored`, so even before fixing #1, the API response always claimed full success regardless of how many rows had actually failed to insert. Fixed: `save_jobs_to_db()` now returns `{"saved": N, "failed": N}`; the response reports `total_stored` (actual) and a new `failed_to_store` field, with a server-side warning logged whenever any row fails.

---

## Re-verified, no regressions
Security headers (CSP, Permissions-Policy, X-Frame-Options), rate limiting, SQL parameterization, `alerts.py`'s SSRF guard and escaping, and the threading fix from Audit #4 — all confirmed still intact.

## Tests
138 passing (was 134), +4 new/rewritten covering the index-migration edge case (missing index vs. present-and-needs-recreating), truncation behavior, and the saved/failed count tracking. Coverage 85% (up from 84%).
