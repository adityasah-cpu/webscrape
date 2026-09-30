# Security & Code Audit #4 — Post Multi-Platform Feature Update
**Date:** 2026-09-30
**Scope:** Focused pass on what changed in the last feature update (fetch-everything behavior, 11 newly-exposed scraper platforms, the new `experience_level` parameter surface, and the new frontend resume-prompt code), plus a quick re-verification that prior fixes are still intact.

---

## Findings — all fixed

### 1. 🟠 `epoch_to_date()` could crash and silently drop an entire scraper's job batch
**File:** `remote_job_scraper.py`

```python
def epoch_to_date(ts):
    try:
        ts = int(ts)
        ...
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError):   # too narrow
        return ""
```

`datetime.fromtimestamp()` raises **`OSError`** (confirmed on this app's actual Windows runtime) or `OverflowError` for out-of-range epoch values — negative-and-large, or absurdly large positive numbers. Neither is a `TypeError`/`ValueError`, so neither was caught. Reproduced directly:
```
epoch_to_date(-999999999999)      -> OSError: [Errno 22] Invalid argument   (NOT caught)
epoch_to_date(99999999999999999)  -> OSError: [Errno 22] Invalid argument   (NOT caught)
```

**Impact:** this function is called from `scrape_himalayas()`, `scrape_arbeitnow()`, and `scrape_lever()`, always **outside** any per-job try/except — only the top-level per-scraper catch in `/api/fetch` stops it from crashing the whole request, but that catch discards the *entire batch* from that source. One malformed timestamp anywhere in a 200-job response would silently lose all 200 jobs, not just the bad record. `scrape_lever` is one of the 11 scrapers exposed to users in the last update, so this is now meaningfully more likely to actually trigger than when it was unreachable from the UI.

**Fix:** broadened the except clause to `(TypeError, ValueError, OverflowError, OSError)`.

### 2. 🟠 `fmt_salary()` had the same class of bug
**File:** `remote_job_scraper.py`

```python
def n(x):
    try:
        return f"{int(float(x)):,}"
    except (TypeError, ValueError):   # too narrow
        return ""
```

`int(float('inf'))` raises `OverflowError`, not caught. Reproduced:
```
fmt_salary(float('inf'), 60000)  -> OverflowError (NOT caught)
```
Used by `scrape_himalayas`, `scrape_adzuna` (newly exposed), and `scrape_toptal` (newly exposed) — a job board API returning a sentinel/unbounded salary value (not far-fetched; "inf" or a max-int sentinel for "unlimited budget" shows up in real freelance-platform APIs) would have the same batch-loss effect as finding #1.

**Fix:** broadened to `(TypeError, ValueError, OverflowError)`.

Both verified fixed with direct reproduction (inf/nan/out-of-range values now degrade to `""` instead of raising) and 13 new regression tests.

### 3. 🟠 The Flask dev server was single-threaded — a slow fetch froze the entire app
**File:** `api.py`

`app.run(debug=flask_debug, port=5000)` had no `threaded=True`. Werkzeug's dev server defaults to single-threaded, meaning while one request is being handled, **no other request can be served at all** — not `/api/jobs`, not the static page, nothing.

This was always technically true, but with only 6 selectable sources and fetch discarding everything except fresher jobs, a fetch was fast enough that it was never really noticeable. Now: 17 sources are selectable, several do multi-page pagination with `time.sleep(1)` between pages (Internshala, Unstop, Adzuna, Toptal-adjacent loops), and nothing gets discarded — a multi-source fetch can now genuinely take tens of seconds to minutes. During that entire window the app would have been completely unresponsive to anything else.

**Fix:** added `threaded=True`. Safe to do — the only shared mutable state (the in-memory jobs cache) already uses its own `threading.Lock()`.

**Verified live:** fired a 3-source fetch that took **15.6 seconds**; a concurrent `GET /api/db-info` request during that window responded in **0.2 seconds** instead of waiting for the fetch to finish.

### 4. 🟡 `remote_job_scraper.py` had zero dedicated test coverage
Every helper function in this file (`fmt_salary`, `epoch_to_date`, `job()`, `dedupe()`, etc.) was previously only exercised indirectly through mocked `SCRAPERS`/`dedupe` in `test_api_endpoints.py` — meaning the two bugs above had no test surface that could have caught them. Added `tests/test_scraper_helpers.py` (19 tests) covering both fixes plus general coverage of the job factory and dedup logic.

---

## Re-verified still intact (no regressions)

- Security headers (CSP, Permissions-Policy, X-Frame-Options) unchanged and still present.
- All SQL still parameterized; the one known `CREATE DATABASE` identifier-validation mitigation from Audit #3 still in place.
- `alerts.py`'s SSRF guard and output escaping still intact.
- Frontend escaping (`escapeHtml`) already covers all data flowing through the newly-exposed scrapers — no separate frontend fix was needed since the escaping is applied generically to every job field regardless of source.
- Rate limiting on `/api/fetch`, `/api/match-resume`, `/api/clear-jobs`, `/api/test-alert` unchanged.

## Checked, no issue found

- Grepped fresh for `eval`/`exec`/`subprocess`/`pickle`/`os.system`/`shell=True`/`debug=True` across all four core files — clean.
- Reviewed all 8 newly-exposed scraper functions (Jobicy, WeWorkRemotely, Adzuna, Unstop, AngelList, Dev.to, Upwork, Toptal, Greenhouse, Lever, Ashby) for injection risks. `Greenhouse`/`Lever`/`Ashby` build request URLs from hardcoded company-name constants (not user input) — no injection surface. `Toptal`'s job URL is built from an API-supplied `slug` with no encoding, but it's appended to a fixed `https://www.toptal.com/jobs/` prefix, so it can't be used to redirect off-domain or inject a different scheme — low-severity code-quality note, not exploitable.
- The new `experience_level` parameter on both `/api/jobs` and `/api/match-resume` is a plain string compared against two literal values (`"fresher"`/`"experienced"`) — no injection surface, invalid values are handled gracefully (ignored as a filter on `/api/jobs`, rejected with 400 on `/api/match-resume`).

## Noted, not fixed (informational)

**`MAX_JOBS_FETCH` (5000-row cap on `load_jobs_from_db()`) is now much more likely to actually be reached.** Since `/api/fetch` no longer discards non-fresher jobs, the table grows far faster than before with every fetch. Current count: 1,431 rows (~29% of the cap) — not urgent, but worth knowing: if the table ever exceeds 5,000 rows, the oldest jobs silently stop appearing in `/api/jobs`, `/api/stats`, `/api/analytics`, and résumé matching (still in MySQL, just not read back) with no error or warning shown anywhere. Not fixed in this pass since there's substantial headroom today; flagging so it's not a surprise later. If it becomes relevant, the fix is either raising the cap, moving to real DB-level pagination, or adding a periodic cleanup of stale listings.

---

## Summary

| Severity | Count | Items |
|---|---|---|
| 🟠 Medium | 3 | Two batch-losing crash bugs in scraper helpers (epoch_to_date, fmt_salary), single-threaded server freezing the whole app during fetch |
| 🟡 Low | 1 | Missing test coverage for remote_job_scraper.py (now added) |
| ℹ️ Informational | 1 | MAX_JOBS_FETCH cap now more reachable given fetch-everything behavior |

All fixed and verified: **134/134 tests passing** (was 115, +19 new), live-verified the threading fix with a real concurrent-request test, live-verified both crash fixes with direct reproduction of the failure inputs.
