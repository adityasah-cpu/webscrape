# Security & Code Audit #6
**Date:** 2026-10-04

## Vulnerabilities found and fixed

### 1. 🔴 CSV/Formula Injection in `/api/export` (CWE-1236)
**File:** `api.py`, `remote_job_scraper.py`

Job title/company/category/description come from 17 external, uncontrolled job boards. Neither `/api/export?format=csv` nor the standalone `python remote_job_scraper.py` CLI sanitized these values before writing them into a CSV. A malicious or compromised listing titled e.g. `=HYPERLINK("http://evil.com","click")` or `=cmd|'/C calc'!A1` would execute as a live formula the moment the exported CSV is opened in Excel, LibreOffice, or Google Sheets.

**Fix:** added `_csv_safe()` in `api.py` and an equivalent inline guard in `remote_job_scraper.py`'s CLI export — any field starting with `=`, `+`, `-`, `@`, tab, or CR gets a leading `'` prefix, which spreadsheet apps render as literal text instead of evaluating. Verified live against the real 1,605-row dataset export.

### 2. 🟡 Oversized/decompression-bomb images could exhaust memory via the OCR resume path
**File:** `api.py`

`_ocr_image_bytes()` passed uploaded image bytes straight to EasyOCR with no dimension check. `MAX_CONTENT_LENGTH` (5MB) only bounds the *compressed* upload size — a small file can still decode to an enormous pixel buffer (a "decompression bomb"), and EasyOCR's underlying decode isn't protected the way Pillow's default `Image.MAX_IMAGE_PIXELS` guard would be.

**Fix:** added `_validate_image_bytes()`, which opens the upload with Pillow first and rejects anything over 40 megapixels (`MAX_OCR_IMAGE_PIXELS`) or that isn't a valid image at all, before any OCR work begins.

### 3. 🟡 Flask's default 413 response broke the frontend, and was masked by broad `except Exception` anyway
**File:** `api.py`

Two compounding bugs:
- No `@app.errorhandler(413)` existed, so an oversized upload returned Werkzeug's default HTML error page — not the JSON the frontend's `fetch().json()` expects.
- Even after adding that handler, it never fired: Werkzeug raises `RequestEntityTooLarge` *inside* the request-parsing step (e.g. `request.files[...]`), which happens inside each route's own `try` block and was being caught by that route's generic `except Exception as e:` and converted into an unrelated 500. This was caught by a regression test written specifically to exercise it, which failed with `500` instead of the expected `413` until fixed.

**Fix:** added the JSON 413 handler, and added `except HTTPException: raise` ahead of the generic exception handler in the three routes that parse a request body (`/api/fetch`, `/api/match-resume`, `/api/test-alert`), so real HTTP exceptions propagate to their proper handler instead of being swallowed.

### 4. 🟡 `filter_jobs()` could crash on `None`-valued fields instead of filtering correctly
**File:** `api.py`

`keyword`/`work_type`/`country`/`job_type` filtering called `.lower()` directly on `job.get('field', '')`, which only supplies the `''` default when the *key is missing* — a row where the key exists but the value is `None` (legacy data, or any future code path that doesn't scrub it the way `job()`/`_truncate_for_column()` currently do) would raise `AttributeError` on `None.lower()`, caught by the route's broad exception handler and surfaced as a generic 500 instead of just working. Every other place in the codebase already uses the `(x.get(...) or '')` pattern for exactly this reason — this function was the one holdout.

**Fix:** switched to `(j.get('field') or '').lower()` consistently, matching the rest of the codebase's established convention.

## Re-verified, no regressions
All previously-fixed items from Audits #2–#5 re-checked and still intact: credentials in `.env` only, git history clean of any password, XSS escaping, SSRF guard on the Slack alert channel, rate limiting, SQL parameterization, security headers, schema auto-migration. `pip-audit` against `requirements.txt`: **zero known CVEs**.

## Known, already-accepted risk (not newly introduced, flagged for visibility)
`/api/test-alert` accepts an arbitrary `email`/`telegram`/`slack` config from the request body and reports back whether sending succeeded. Combined with no authentication on any endpoint (an accepted limitation for this local/academic project — see `PROJECT_STATUS_REPORT.md` §6), this means anyone who can reach the port could use it to test whether a given Gmail address/app-password combination is valid, or relay a message through an arbitrary Telegram bot token. Rate-limited to 5/hour (existing mitigation from Audit #3), which slows but doesn't eliminate this. Not exploitable from a malicious webpage in a browser (blocked by the existing `CORS_ORIGINS` allowlist triggering a failed preflight), only from something with direct network access to the port — the same threat model already accepted for the rest of the unauthenticated API. No code change made here since fixing it properly would mean removing the feature's actual purpose (letting a user test their own alert config); documented instead so it's a known, deliberate trade-off rather than a silent gap.

## Tests
150 passing (was 144). +6 new regression tests covering: CSV formula-injection neutralization, `_csv_safe()` unit behavior, oversized/invalid-image OCR rejection, the 413-returns-JSON-not-500 path, and `filter_jobs()` no longer crashing on `None`-valued fields.
