# Security & Code Audit #3 — Full Codebase
**Date:** 2026-09-29
**Scope:** Complete fresh pass over the entire codebase post-cleanup (dead files removed, git history scrubbed, `alerts.py` escaping fixed, dependencies synced). This report both re-verifies what's still open from Audit #2 and adds newly-found issues from a deeper line-by-line pass.

---

## Carried over from Audit #2 — still open

These were found previously, not yet fixed (you approved items 2 and 4 from that report; these are the rest):

| # | Finding | Location | Status |
|---|---|---|---|
| 1 | SSRF via `/api/test-alert`'s Slack `webhook_url` — no validation it's actually a Slack URL | `alerts.py:163` (`send_slack`) | 🔴 Open |
| 2 | `/api/test-alert` doubles as a Gmail credential-testing oracle — no rate limit, returns success/fail on arbitrary email/password | `alerts.py:84`, `api.py:966` | 🔴 Open |
| 3 | `app.run(debug=True, ...)` — Werkzeug interactive debugger enabled | `api.py:1075` | 🟠 Open |
| 4 | `CREATE DATABASE IF NOT EXISTS {db_name}` — unvalidated f-string identifier interpolation (low real risk, `db_name` is env-sourced not user input) | `api.py:140` | 🟡 Open |

*(Rotating the MySQL password is still the pending action item from Audit #2 as well — noting it here again since it's the most important one.)*

---

## New findings from this pass

### 🟠 5. `/api/jobs` pagination has no bounds/type validation — negative `page` returns wrong data, not an error
**File:** `api.py:822-823`, `filter_jobs()` at `api.py:426-430`

```python
page = int(request.args.get("page", 1))
limit = int(request.args.get("limit", 20))
...
start = (page - 1) * limit
end = start + limit
return { "jobs": filtered[start:end], ... }
```

Two distinct bugs, both stemming from missing validation (contrast with `/api/analytics` and `/api/match-resume`'s `top_n`, which both explicitly clamp and catch `ValueError`):

- **`page=-1` (or any negative value) silently returns real data instead of empty/error.** Python's negative list slicing means `filtered[start:end]` wraps to unrelated jobs rather than failing. Verified:
  ```python
  filtered = list(range(50)); limit = 20; page = -1
  start, end = (page-1)*limit, (page-1)*limit + limit   # -40, -20
  filtered[start:end]  # → [10..29] — real, wrong data, not an error
  ```
- **Non-numeric `page`/`limit` (e.g. `?page=abc`) raises an uncaught `ValueError`** at the `int()` call, which the route's outer `except Exception` catches and turns into a generic 500 "Failed to load jobs" — instead of gracefully falling back to a default like the analytics/resume endpoints do.

**Fix:** mirror the pattern already used in `/api/analytics`:
```python
try:
    page = max(int(request.args.get("page", 1)), 1)
    limit = min(max(int(request.args.get("limit", 20)), 1), 1000)
except (ValueError, TypeError):
    page, limit = 1, 20
```

No test currently covers this (`tests/test_helpers.py::TestFilterJobs` only tests positive pages).

### 🟡 6. `work_type` is inserted into the DOM unescaped as a CSS class name (currently safe only by convention, not enforcement)
**File:** `index.html:1413`, `1585`

```javascript
<span class="work-type-badge ${(job.work_type || "Remote").toLowerCase()}">${escapeHtml(job.work_type || "N/A")}</span>
```

The visible text is correctly escaped, but the same field used as a **class attribute value** is not — and this is set via `innerHTML`, so a value like `Remote"><script>...` would break out of the attribute if it ever reached the frontend. Traced this all the way back through `remote_job_scraper.py`: `work_type` is *always* produced by `classify_work_type()` or `norm_workplace()`, both of which only ever return one of `{"Remote", "Hybrid", "Onsite"}` (or a hardcoded literal) — so it's **not currently exploitable**, but that safety is an unenforced convention spread across 9+ independent scraper functions and the database column has no CHECK constraint or allowlist validation anywhere. One future scraper added carelessly (e.g. passing through a raw API field as `work_type` without running it through `classify_work_type`) would turn this into live, unescaped, database-stored XSS with no frontend change required to trigger it.

**Fix:** cheap and removes the fragile invariant entirely — `escapeHtml((job.work_type || "Remote").toLowerCase())` in both spots, or validate/allowlist `work_type` server-side before storage.

### 🟡 7. Two scrapers fail completely silently, with zero diagnostic trace
**File:** `remote_job_scraper.py:447` (`scrape_internshala`), `:480` (`scrape_unstop`)

```python
try:
    data = get_json(...)
except Exception:
    break
```

If Internshala or Unstop change their API in a way that breaks the request (auth requirement added, endpoint moved, response shape changed), these functions silently return `[]` — which looks identical to "ran fine, found 0 jobs" both in `/api/fetch`'s per-source `status` dict and in the logs. Every other scraper in the file at least does `except Exception as e: print(f"...: {e}")` before continuing. This is an operability gap, not a security issue: you'd have no way to tell "this source is broken" from "this source genuinely has nothing new" without manually testing it.

**Fix:** `except Exception as e: logger.warning(...); break` (or `print`, to match the rest of the file's current style — this file doesn't use the `logging` module at all yet, unlike `api.py`).

### 🟢 8. `alerts.py` still uses `print()` instead of `logging`
Every other error path in the active codebase (`api.py`) was moved to Python's `logging` module in an earlier pass; `alerts.py` (`print(f"Telegram error: {e}")` etc., 5 occurrences) and `remote_job_scraper.py` (`print(f"   ! Lever/{co}: {e}")` etc., scattered throughout) were not touched. Not a bug, just inconsistent with the rest of the codebase's error-observability approach — worth doing in the same pass as Finding #7 above since both are about the same file/observability gap.

### 🟢 9. `/api/db-info` exposes internal topology to any unauthenticated caller
**File:** `api.py:932-940`

Returns `"host": MYSQL_CONFIG['host']` and `"database": MYSQL_CONFIG['database']` to anyone who hits the endpoint — not credentials, but internal infrastructure detail. Consistent with the rest of the app's documented "no auth, local-use-only" posture (Audit #2 Finding #10), so not a new risk class, just worth listing so it's not missed if this app's exposure ever changes.

### 🟢 10. Stale documentation clutter — 20+ files still remain
**Files:** `AUDIT_FINAL_REPORT.txt`, `AUDIT_INDEX.md`, `AUDIT_REPORT_V2.md`, `AUDIT_SUMMARY.txt`, `AUDIT_V2_COMPLETE.txt`, `CONNECTION_MAP.md`, `CORPORATE_UI_FEATURES.txt`, `CORPORATE_UI_SETUP.md`, `FEATURE_COMPLETE.txt`, `IMPLEMENTATION_COMPLETE.md`, `MERGED_FEATURES.md`, `MODAL_FEATURE.md`, `MODAL_SUMMARY.txt`, `POSTGRESQL_SETUP.md`, `QUICK_START_MODAL.txt`, `REDIS_INTEGRATION_COMPLETE.txt`, `REDIS_SETUP.md`, `SETUP_COMPLETE.md`, `UI_COMPARISON.md`, `audit_report.json`, `audit_report_v2.json`, `audit_v2_output.txt`, `scraper_config_template.json`

None of these contained the leaked password (already checked, which is why Audit #2's cleanup left them alone), but they describe features that don't reflect the current app (Postgres migration that was reverted, Redis integration that's disabled, a "modal feature" implementation log, etc.). Pure clutter at this point — not a security issue, just noise that makes the repo harder to navigate and could confuse anyone (including a future me) about what's actually current. `API_DOCUMENTATION.md`, `RESUME_FEATURE_GUIDE.md`, `COMPREHENSIVE_AUDIT_REPORT.md`, `SECURITY_AUDIT_2.md`, and this file are the actually-current docs.

---

## What's already solid (verified, not re-litigated)

- SQL: every query except the one `CREATE DATABASE` line (#4 above) uses parameterized `%s`/`?` placeholders correctly.
- XSS: `index.html`'s job-title/company/domain/source rendering is properly escaped everywhere except the one class-name spot (#6).
- `alerts.py`'s email/Telegram/Slack formatters correctly escape job data and validate URLs (fixed in the last pass) — confirmed still intact.
- Resume upload: extension allowlist, size cap, in-memory-only processing (no disk writes), minimum-text-length gate — all still correct.
- Rate limiting on `/api/fetch`, `/api/match-resume`, `/api/clear-jobs` — correct and tested.
- `.env` is gitignored and was never tracked; the password is fully scrubbed from git history and verified via an independent fresh clone from GitHub.
- Test suite: 83/83 passing, 84% coverage on `api.py`.

---

## Summary & suggested order

| Severity | Count | Items |
|---|---|---|
| 🔴 Critical/High (carried over, unfixed) | 3 | SSRF, credential oracle, debug mode |
| 🟡 Medium | 3 | `/api/jobs` pagination bug, unenforced `work_type` XSS invariant, `CREATE DATABASE` interpolation (carried over) |
| 🟢 Low | 4 | Silent scraper failures, `print()` vs `logging` inconsistency, `/api/db-info` info exposure, stale doc clutter |

**Suggested next batch, if you want to keep going:**
1. Fix `/api/jobs` pagination bounds (#5) — quick, same pattern already used elsewhere in the file
2. Escape `work_type` in the two class-name spots (#6) — one-line fix each, removes a fragile invariant
3. The three carried-over items from Audit #2 (SSRF validation + rate limit on `/api/test-alert`, `debug=False` by default) — you hadn't approved these yet
4. Everything else (#7-10) is cheap cleanup, no urgency
