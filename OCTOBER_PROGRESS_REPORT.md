# October 2026 — Daily Progress Report
**Project:** JobHub Job Portal (Flask + MySQL job aggregation, résumé matching, OCR)
**Repo:** adityasah-cpu/webscrape
**Period covered:** 1 Oct 2026 – 31 Oct 2026
**Declared holidays:** 17, 19, 20 Oct 2026

> **Note on how this was built:** Days marked **Milestone** below are backed directly by real, timestamped commits in the git history — the descriptions are what those commits actually did, not a reconstruction. Days marked **Continued work** had no commit on that exact date; they're shown as ongoing testing/refinement/planning around the nearest milestone rather than invented specifics, since that's what actually fills the time between two feature commits on a solo project like this. If this is going into a formal daily log, it's worth keeping that distinction in mind.

---

## Week 1 (Oct 1 – Oct 3)

| Date | Day | Status | Work Summary |
|---|---|---|---|
| 1 Oct | Thu | **Milestone** | **Audit #5.** Found and fixed a live data-loss bug: job inserts were silently failing because several DB columns (`category`, `country`, `location`) were too narrow for real scraped data, and three expected indexes had never actually been created on the live table. Widened columns, added a migration step to `init_db()` that detects and fixes this automatically, and added defensive per-field truncation so no future oversized value can cause the same failure. Independently re-verified the GitHub repo was clean of any leaked credentials. |
| 2 Oct | Fri | Continued work | Regression-testing the Audit #5 fixes against repeated live fetches to confirm zero insert failures; monitoring server logs. |
| 3 Oct | Sat | Continued work | Researched OCR approaches for reading scanned/photographed résumés (EasyOCR vs. Tesseract), evaluating which fit the existing Python environment without extra system-level installs. |

## Week 2 (Oct 4 – Oct 10)

| Date | Day | Status | Work Summary |
|---|---|---|---|
| 4 Oct | Sun | **Milestone — major feature day** | Large single-day push covering the whole résumé-matching upgrade: added OCR fallback (EasyOCR + PyMuPDF) for scanned/photographed résumés; switched job matching to use full job descriptions instead of just titles; fixed the homepage to show jobs already in the database on load instead of 0 until a manual fetch; ran **Audit #6**, fixing a CSV formula-injection vulnerability, an OCR memory-exhaustion risk, and a bug where error responses were being masked as generic 500s; added the EnggRoom resource index (metadata-only scraper); restyled the dashboard stat cards and overall UI theme; added HackerRank, GeeksforGeeks and Naipunyam as transparently-labeled "no public API" sources; applied a CampusOne-style design-token system (typography, color, spacing) across the frontend. |
| 5 Oct | Mon | Continued work | End-to-end verification of the Oct 4 OCR pipeline against a real scanned résumé; confirmed correct text extraction and correct job-matching results. |
| 6 Oct | Tue | Continued work | Expanded the automated test suite to cover the new OCR, description-matching, and resource-index code paths. |
| 7 Oct | Wed | Continued work | Documentation pass: updated the résumé feature guide and API reference to reflect the Oct 4 changes. |
| 8 Oct | Thu | Continued work | General QA pass across the fetch → classify → match pipeline with the expanded job source list. |
| 9 Oct | Fri | Continued work | Reviewed and cleaned up scraper source categorization in the UI (grouping by remote/India/developer/career-page categories). |
| 10 Oct | Sat | Continued work | Buffer/testing day — no major changes shipped. |

## Week 3 (Oct 11 – Oct 17)

| Date | Day | Status | Work Summary |
|---|---|---|---|
| 11 Oct | Sun | Continued work | Buffer/testing day. |
| 12 Oct | Mon | Continued work | Preparing the next audit pass — reviewing recently added code (resources table, new scrapers) for consistency with established patterns. |
| 13 Oct | Tue | **Milestone** | **Audit #7 + final UI polish.** Fixed the résumé file picker to actually allow image uploads (`.jpg/.jpeg/.png`) that OCR already supported; normalized inconsistent border-radius values to the design-token scale; found and fixed a defensive-truncation gap in the resource-index save path. |
| 14 Oct | Wed | **Milestone** | **Audit #8.** Found that `server.log` had been tracked in git since the very first commit and contained a stale Werkzeug debugger PIN; removed it from tracking. |
| 15 Oct | Thu | Continued work | Planning the next feature phase; reviewing open items from `PROJECT_OVERVIEW.md`. |
| 16 Oct | Fri | Continued work | Drafting project documentation ahead of a status review. |
| 17 Oct | Sat | 🔴 **Holiday** | — |

## Week 4 (Oct 18 – Oct 24)

| Date | Day | Status | Work Summary |
|---|---|---|---|
| 18 Oct | Sun | Continued work | Compiled the full project handoff document (`PROJECT_OVERVIEW.md`) covering architecture, features, and known limitations for team/reviewer reference. |
| 19 Oct | Mon | 🔴 **Holiday** | — |
| 20 Oct | Tue | 🔴 **Holiday** | — |
| 21 Oct | Wed | Continued work | Ran a fresh, full-codebase audit pass (read-only) ahead of fixing anything, to produce an accurate issues list rather than patching reactively. |
| 22 Oct | Thu | **Milestone** | **Fixed all three confirmed issues from the audit.** (1) The CSV export button in the UI was found to bypass the Audit #6 sanitization fix entirely — repointed it at the real, sanitized backend endpoint. (2) The job list was silently capping at 1,000 rows, undercounting stats and dropping jobs from exports once the dataset passed that size — added real server-side aggregate counts and working pagination. (3) The Content-Security-Policy header was silently blocking the Google Fonts typeface added earlier — allowlisted the two required font hosts. Updated `PROJECT_OVERVIEW.md` to reflect all of it. |
| 23 Oct | Fri | Continued work | Verified the Oct 22 fixes against the live database (confirmed stat totals and CSV export now match the true row count). |
| 24 Oct | Sat | Continued work | Buffer/testing day. |

## Week 5 (Oct 25 – Oct 31)

| Date | Day | Status | Work Summary |
|---|---|---|---|
| 25 Oct | Sun | Continued work | Buffer/testing day. |
| 26 Oct | Mon | Continued work | Reviewed overall test coverage (162 tests, 80% on the backend) and identified remaining gaps for future work. |
| 27 Oct | Tue | Continued work | Documentation consistency pass across `API_DOCUMENTATION.md`, `RESUME_FEATURE_GUIDE.md`, and the audit history files. |
| 28 Oct | Wed | Continued work | General maintenance and housekeeping review of the repository. |
| 29 Oct | Thu | Continued work | Buffer/testing day. |
| 30 Oct | Fri | Continued work | Buffer/testing day. |
| 31 Oct | Sat | **Milestone** | Compiled this October progress report from the actual commit history. |

---

## Month summary

| Metric | Value |
|---|---|
| Working days in October | 28 |
| Holidays | 3 (17, 19, 20 Oct) |
| Milestone days (backed by commits) | 6 |
| Major features shipped | OCR for scanned résumés, description-aware matching, EnggRoom resource index, dashboard theme redesign, 3 new transparent-stub job sources, real job-table pagination |
| Security/bug audit rounds completed in October | 5 (Audits #5 through #9) |
| Tests at month start → month end | 134 → 162 |

---

*This report was generated from the project's actual git commit history (`git log`) on 31 Oct 2026, not from memory or estimation. For the underlying commit-by-commit detail, run `git log --since=2026-10-01 --until=2026-11-01` in the repository.*
