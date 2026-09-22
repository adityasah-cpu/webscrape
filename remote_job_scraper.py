"""
Job Scraper (remote, hybrid & onsite)
-------------------------------------
Pulls jobs from public APIs / RSS feeds, detects work type (Remote/Hybrid/Onsite),
country/region, job type and category, removes duplicates, and saves to jobs.csv.

Setup:
    pip install requests feedparser

Run from terminal:
    python remote_job_scraper.py                 # all jobs
    python remote_job_scraper.py python react    # only jobs whose title matches any keyword

Or use the web UI:  streamlit run app.py
"""

import csv
import html
import os
import re
import sys
import time
from datetime import datetime, timezone

import feedparser
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (job-scraper; personal use)"}
TIMEOUT = 30
OUTPUT_FILE = "jobs.csv"

# Company "slugs" from careers URLs, e.g. boards.greenhouse.io/<slug>, jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>
GREENHOUSE_COMPANIES = ["gitlab", "airbnb", "stripe"]
LEVER_COMPANIES = ["netflix", "plaid"]
ASHBY_COMPANIES = ["notion", "ramp"]

# Adzuna: country-wide job search (remote + hybrid + onsite). Free keys at https://developer.adzuna.com
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
ADZUNA_COUNTRIES = ["in"]
ADZUNA_QUERY = ""
ADZUNA_PAGES = 2
ADZUNA_SUPPORTED = {
    "at": "Austria", "au": "Australia", "be": "Belgium", "br": "Brazil", "ca": "Canada",
    "ch": "Switzerland", "de": "Germany", "es": "Spain", "fr": "France", "gb": "United Kingdom",
    "in": "India", "it": "Italy", "mx": "Mexico", "nl": "Netherlands", "nz": "New Zealand",
    "pl": "Poland", "sg": "Singapore", "us": "United States", "za": "South Africa",
}

# AngelList / Wellfound: API key optional (limited requests without it)
ANGELLIST_API_KEY = os.getenv("ANGELLIST_API_KEY", "")

# Upwork and Toptal: these are public boards, no keys needed
# But Upwork has rate limits, so be respectful

# Internshala: Free public API, India-focused
INTERNSHALA_PAGES = 3

# Unstop: Scrapes public job board
UNSTOP_PAGES = 2

# FirstNaukri: RSS + web (public)
# Dev.to: Public API

FIELDS = ["source", "title", "company", "work_type", "country", "location",
          "job_type", "category", "salary", "date", "start_date", "end_date", "url"]


# ---------------- Helpers ----------------

def flatten(vals):
    out = []
    for v in vals:
        if v is None or v == "":
            continue
        if isinstance(v, (list, tuple, set)):
            out.extend(flatten(v))
        elif isinstance(v, dict):
            out.extend(flatten(v.values()))
        else:
            out.append(str(v))
    return out


def clean(text):
    text = html.unescape(str(text or ""))
    return re.sub(r"<[^>]+>", "", text).strip()


COUNTRY_ALIASES = {
    "India": ["india", "bangalore", "bengaluru", "hyderabad", "mumbai", "pune", "chennai", "delhi",
              "new delhi", "gurgaon", "gurugram", "noida", "kolkata", "ahmedabad", "kochi", "vijayawada"],
    "United States": ["united states", "usa", "u.s.", "new york", "san francisco", "seattle", "austin",
                      "boston", "chicago", "los angeles", "denver", "atlanta", "miami"],
    "United Kingdom": ["united kingdom", "uk", "england", "scotland", "wales", "london", "manchester", "edinburgh"],
    "Canada": ["canada", "toronto", "vancouver", "montreal", "ottawa", "calgary"],
    "Germany": ["germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln"],
    "France": ["france", "paris", "lyon"],
    "Netherlands": ["netherlands", "holland", "amsterdam", "rotterdam"],
    "Spain": ["spain", "madrid", "barcelona"],
    "Portugal": ["portugal", "lisbon", "porto"],
    "Italy": ["italy", "milan", "rome"],
    "Ireland": ["ireland", "dublin"],
    "Poland": ["poland", "warsaw", "krakow", "kraków"],
    "Sweden": ["sweden", "stockholm"],
    "Switzerland": ["switzerland", "zurich", "zürich", "geneva"],
    "Austria": ["austria", "vienna"],
    "Belgium": ["belgium", "brussels"],
    "Denmark": ["denmark", "copenhagen"],
    "Norway": ["norway", "oslo"],
    "Finland": ["finland", "helsinki"],
    "Ukraine": ["ukraine", "kyiv"],
    "Romania": ["romania", "bucharest"],
    "Australia": ["australia", "sydney", "melbourne", "brisbane"],
    "New Zealand": ["new zealand", "auckland"],
    "Singapore": ["singapore"],
    "Japan": ["japan", "tokyo"],
    "Philippines": ["philippines", "manila"],
    "Indonesia": ["indonesia", "jakarta"],
    "Malaysia": ["malaysia", "kuala lumpur"],
    "Vietnam": ["vietnam", "ho chi minh", "hanoi"],
    "Pakistan": ["pakistan", "karachi", "lahore"],
    "Bangladesh": ["bangladesh", "dhaka"],
    "Sri Lanka": ["sri lanka", "colombo"],
    "United Arab Emirates": ["united arab emirates", "uae", "dubai", "abu dhabi"],
    "Israel": ["israel", "tel aviv"],
    "Brazil": ["brazil", "brasil", "são paulo", "sao paulo"],
    "Mexico": ["mexico", "méxico", "mexico city"],
    "Argentina": ["argentina", "buenos aires"],
    "Colombia": ["colombia", "bogota", "bogotá"],
    "South Africa": ["south africa", "cape town", "johannesburg"],
    "Nigeria": ["nigeria", "lagos"],
    "Kenya": ["kenya", "nairobi"],
    "Egypt": ["egypt", "cairo"],
}
REGION_ALIASES = {
    "Worldwide": ["worldwide", "anywhere", "global", "globally", "any location", "anywhere in the world"],
    "Europe": ["europe", "eu", "european"],
    "EMEA": ["emea"],
    "LATAM": ["latam", "latin america", "south america"],
    "APAC": ["apac", "asia pacific", "asia-pacific"],
    "North America": ["north america"],
    "Americas": ["americas"],
}
_PATTERNS = [
    (name, re.compile(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])"))
    for name, aliases in {**COUNTRY_ALIASES, **REGION_ALIASES}.items()
    for alias in aliases
]
_US_CODE = re.compile(r"\bUS\b|\bUSA\b")


def detect_countries(*texts):
    raw = " ".join(flatten(texts))
    low = raw.lower()
    found = {name for name, pat in _PATTERNS if pat.search(low)}
    if _US_CODE.search(raw):
        found.add("United States")
    return "; ".join(sorted(found))


def classify_work_type(*texts, default="Onsite"):
    t = " ".join(flatten(texts)).lower()
    if "hybrid" in t:
        return "Hybrid"
    if "remote" in t or "work from home" in t or "wfh" in t or "anywhere" in t:
        return "Remote"
    return default


def norm_workplace(value):
    v = str(value or "").lower().replace("-", "").replace("_", "").replace(" ", "")
    return {"remote": "Remote", "hybrid": "Hybrid", "onsite": "Onsite", "inoffice": "Onsite"}.get(v)


def norm_job_type(*vals):
    t = " ".join(flatten(vals)).lower().replace("_", " ").replace("-", " ")
    types = []
    if "full" in t or "permanent" in t:
        types.append("Full-time")
    if "part" in t:
        types.append("Part-time")
    if "contract" in t or "temporary" in t or "temp" in t.split():
        types.append("Contract")
    if "freelance" in t:
        types.append("Freelance")
    if "intern" in t:
        types.append("Internship")
    return ", ".join(types) or "Unspecified"


def fmt_salary(lo, hi=None, currency=""):
    def n(x):
        try:
            return f"{int(float(x)):,}"
        except (TypeError, ValueError):
            return ""
    lo, hi = n(lo), n(hi)
    if not lo and not hi:
        return ""
    rng = f"{lo}-{hi}" if lo and hi and lo != hi else (lo or hi)
    return f"{rng} {currency or ''}".strip()


def epoch_to_date(ts):
    try:
        ts = int(ts)
        if ts > 10**12:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return ""


def job(source, title, company, *, work_type="Remote", location="", country="",
        job_type="", category="", salary="", date="", start_date="", end_date="", url=""):
    location = clean(", ".join(flatten([location])))
    return {
        "source": source,
        "title": clean(title),
        "company": clean(company),
        "work_type": work_type,
        "country": country or detect_countries(location) or "Unspecified",
        "location": location or ("Remote" if work_type == "Remote" else ""),
        "job_type": job_type or "Unspecified",
        "category": clean(category),
        "salary": salary or "",
        "date": str(date or "")[:10],
        "start_date": str(start_date or "")[:10],
        "end_date": str(end_date or "")[:10],
        "url": url or "",
    }


def get_json(url, **kwargs):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    r.raise_for_status()
    return r.json()


# ---------------- Remote-only job boards ----------------

def scrape_remotive():
    data = get_json("https://remotive.com/api/remote-jobs")
    return [
        job("Remotive", j.get("title"), j.get("company_name"),
            location=j.get("candidate_required_location"),
            job_type=norm_job_type(j.get("job_type")), category=j.get("category"),
            salary=j.get("salary"), date=j.get("publication_date"), url=j.get("url"))
        for j in data.get("jobs", [])
    ]


def scrape_remoteok():
    data = get_json("https://remoteok.com/api")
    jobs = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue  # first item is a legal notice
        jobs.append(job("RemoteOK", j.get("position"), j.get("company"),
                        location=j.get("location"),
                        salary=fmt_salary(j.get("salary_min"), j.get("salary_max"), "USD"),
                        date=j.get("date"), url=j.get("url")))
    return jobs


def scrape_himalayas(max_pages=10):
    jobs = []
    for page in range(max_pages):
        data = get_json("https://himalayas.app/jobs/api", params={"limit": 20, "offset": page * 20})
        batch = data.get("jobs", [])
        if not batch:
            break
        for j in batch:
            locs = flatten([j.get("locationRestrictions")])
            jobs.append(job("Himalayas", j.get("title"), j.get("companyName"),
                            location=", ".join(locs) or "Anywhere",
                            country=detect_countries(locs) if locs else "Worldwide",
                            job_type=norm_job_type(j.get("employmentType")),
                            category=" | ".join(flatten([j.get("categories")])[:3]),
                            salary=fmt_salary(j.get("minSalary"), j.get("maxSalary"), j.get("currency")),
                            date=epoch_to_date(j.get("pubDate")),
                            url=j.get("applicationLink") or j.get("guid")))
        time.sleep(1)
    return jobs


def scrape_jobicy():
    data = get_json("https://jobicy.com/api/v2/remote-jobs", params={"count": 100})
    return [
        job("Jobicy", j.get("jobTitle"), j.get("companyName"),
            location=j.get("jobGeo"), job_type=norm_job_type(j.get("jobType")),
            category=" | ".join(clean(c) for c in flatten([j.get("jobIndustry")])),
            salary=fmt_salary(j.get("annualSalaryMin"), j.get("annualSalaryMax"), j.get("salaryCurrency")),
            date=j.get("pubDate"), url=j.get("url"))
        for j in data.get("jobs", [])
    ]


def scrape_weworkremotely():
    feed = feedparser.parse("https://weworkremotely.com/remote-jobs.rss")
    jobs = []
    for e in feed.entries:
        company, _, title = e.get("title", "").partition(": ")
        if not title:
            company, title = "", company
        date = time.strftime("%Y-%m-%d", e.published_parsed) if e.get("published_parsed") else ""
        jobs.append(job("WeWorkRemotely", title, company,
                        location=e.get("region", "Anywhere"),
                        job_type=norm_job_type(e.get("type")),
                        category=e.get("category", ""), date=date, url=e.get("link")))
    return jobs


# ---------------- Boards with remote + hybrid + onsite jobs ----------------

def scrape_arbeitnow(max_pages=5):
    jobs = []
    for page in range(1, max_pages + 1):
        data = get_json("https://www.arbeitnow.com/api/job-board-api", params={"page": page})
        batch = data.get("data", [])
        if not batch:
            break
        for j in batch:
            wt = "Remote" if j.get("remote") else classify_work_type(j.get("title"), j.get("location"))
            jobs.append(job("Arbeitnow", j.get("title"), j.get("company_name"),
                            work_type=wt, location=j.get("location"),
                            job_type=norm_job_type(j.get("job_types")),
                            category=" | ".join(flatten([j.get("tags")])[:3]),
                            date=epoch_to_date(j.get("created_at")), url=j.get("url")))
        time.sleep(1)
    return jobs


def scrape_adzuna():
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        raise RuntimeError("Adzuna API keys missing (free at developer.adzuna.com)")
    jobs = []
    for cc in ADZUNA_COUNTRIES:
        for page in range(1, ADZUNA_PAGES + 1):
            params = {"app_id": ADZUNA_APP_ID, "app_key": ADZUNA_APP_KEY, "results_per_page": 50}
            if ADZUNA_QUERY:
                params["what"] = ADZUNA_QUERY
            data = get_json(f"https://api.adzuna.com/v1/api/jobs/{cc}/search/{page}", params=params)
            results = data.get("results", [])
            if not results:
                break
            for j in results:
                loc = (j.get("location") or {}).get("display_name", "")
                jobs.append(job("Adzuna", j.get("title"), (j.get("company") or {}).get("display_name"),
                                work_type=classify_work_type(j.get("title"), j.get("description"), loc),
                                location=loc, country=ADZUNA_SUPPORTED.get(cc, cc.upper()),
                                job_type=norm_job_type(j.get("contract_time"), j.get("contract_type")),
                                category=(j.get("category") or {}).get("label", ""),
                                salary=fmt_salary(j.get("salary_min"), j.get("salary_max")),
                                date=j.get("created"), url=j.get("redirect_url")))
            time.sleep(1)
    return jobs


# ---------------- Company career pages (all work types) ----------------

def scrape_greenhouse():
    jobs = []
    for co in GREENHOUSE_COMPANIES:
        try:
            data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{co}/jobs")
        except Exception as e:
            print(f"   ! Greenhouse/{co}: {e}")
            continue
        for j in data.get("jobs", []):
            loc = (j.get("location") or {}).get("name", "")
            jobs.append(job("Greenhouse", j.get("title"), co,
                            work_type=classify_work_type(loc, j.get("title")),
                            location=loc, date=j.get("updated_at"), url=j.get("absolute_url")))
    return jobs


def scrape_lever():
    jobs = []
    for co in LEVER_COMPANIES:
        try:
            data = get_json(f"https://api.lever.co/v0/postings/{co}", params={"mode": "json"})
        except Exception as e:
            print(f"   ! Lever/{co}: {e}")
            continue
        for j in data:
            cats = j.get("categories") or {}
            loc = cats.get("location", "")
            wt = norm_workplace(j.get("workplaceType")) or classify_work_type(loc, j.get("text"))
            jobs.append(job("Lever", j.get("text"), co, work_type=wt, location=loc,
                            job_type=norm_job_type(cats.get("commitment")),
                            category=cats.get("team", ""),
                            date=epoch_to_date(j.get("createdAt")), url=j.get("hostedUrl")))
    return jobs


def scrape_ashby():
    jobs = []
    for co in ASHBY_COMPANIES:
        try:
            data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{co}")
        except Exception as e:
            print(f"   ! Ashby/{co}: {e}")
            continue
        for j in data.get("jobs", []):
            loc = j.get("location", "")
            wt = (norm_workplace(j.get("workplaceType"))
                  or ("Remote" if j.get("isRemote") else classify_work_type(loc, j.get("title"))))
            addr_country = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry", "")
            jobs.append(job("Ashby", j.get("title"), co, work_type=wt, location=loc,
                            country=detect_countries(loc, addr_country),
                            job_type=norm_job_type(j.get("employmentType")),
                            category=j.get("department", ""),
                            date=j.get("publishedAt"), url=j.get("jobUrl")))
    return jobs


# ============ NEW SOURCES: Freshers, Internships, India-focused ============

def scrape_internshala(max_pages=None):
    """Internshala: largest internship platform in India. Free API."""
    if max_pages is None:
        max_pages = INTERNSHALA_PAGES
    jobs = []
    for page in range(max_pages):
        try:
            data = get_json(
                "https://internshala.com/api/v2/internship_search_results/",
                params={"offset": page * 20, "limit": 20, "search_filter": "work_from_home"}
            )
        except Exception:
            break
        results = data.get("internships", [])
        if not results:
            break
        for j in results:
            jobs.append(job("Internshala", j.get("title"), j.get("company_name"),
                            work_type="Remote",
                            location=j.get("location_string", "Remote"),
                            country="India",
                            job_type="Internship",
                            category=j.get("profile", ""),
                            salary=fmt_salary(j.get("stipend_min"), j.get("stipend_max"), "₹"),
                            date=j.get("start_date", "")[:10],
                            url=f"https://internshala.com/internship/{j.get('id')}"
                            if j.get("id") else ""))
        time.sleep(1)
    return jobs


def scrape_unstop(max_pages=None):
    """Unstop (HackerEarth): fresher internships + early-career jobs."""
    if max_pages is None:
        max_pages = UNSTOP_PAGES
    jobs = []
    for page in range(1, max_pages + 1):
        try:
            # Unstop API for internships
            data = get_json(
                "https://unstop.com/api/public/opportunity/search",
                params={"page": page, "limit": 20, "category": "internships",
                        "search": "", "sort": "-posted_at"}
            )
        except Exception:
            break
        results = data.get("opportunities", [])
        if not results:
            break
        for opp in results:
            loc = (opp.get("locations") or [{}])[0].get("name", "Remote")
            category = (opp.get("categories") or [{}])[0].get("name", "")
            jobs.append(job("Unstop", opp.get("title"), opp.get("organization_name"),
                            work_type="Remote" if "remote" in opp.get("title", "").lower() else "Onsite",
                            location=loc,
                            country="India" if "india" in opp.get("title", "").lower() or loc.lower() in ["remote", "online"] else "Unspecified",
                            job_type="Internship",
                            category=category,
                            date=opp.get("posted_at", "")[:10],
                            url=f"https://unstop.com/o/{opp.get('id')}" if opp.get("id") else ""))
        time.sleep(1)
    return jobs


def scrape_firstnaukri():
    """FirstNaukri: built for freshers (0-3 years experience) in India."""
    jobs = []
    try:
        # FirstNaukri RSS feed for fresher jobs
        feed = feedparser.parse("https://www.firstnaukri.com/feed/jobs-fresher")
        for entry in feed.entries[:50]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            date = ""
            if entry.get("published_parsed"):
                date = time.strftime("%Y-%m-%d", entry.published_parsed)
            jobs.append(job("FirstNaukri", title, "",
                            location="India",
                            country="India",
                            job_type=norm_job_type("Full-time"),
                            date=date,
                            url=entry.get("link", "")))
    except Exception as e:
        print(f"   FirstNaukri: {e}")
    return jobs


def scrape_angellist():
    """AngelList (Wellfound): startup jobs, often open to freshers."""
    jobs = []
    headers_al = HEADERS.copy()
    if ANGELLIST_API_KEY:
        headers_al["Authorization"] = f"Bearer {ANGELLIST_API_KEY}"
    try:
        # AngelList jobs API
        for page in range(1, 4):
            params = {
                "filter_role_tags": ["engineering", "design", "business", "marketing"],
                "page": page,
                "page_size": 50
            }
            data = get_json("https://api.angellist.com/1/jobs", params=params, timeout=TIMEOUT)
            if not data:
                break
            for j in data:
                startup = j.get("startup") or {}
                jobs.append(job("AngelList", j.get("title"), startup.get("name", ""),
                                work_type="Remote" if j.get("remote") else "Onsite",
                                location=j.get("location", ""),
                                country=detect_countries(j.get("location", "")),
                                job_type=norm_job_type(j.get("job_type")),
                                category=j.get("tag_list", [{}])[0].get("name", "") if j.get("tag_list") else "",
                                date=j.get("created_at", "")[:10],
                                url=j.get("angellist_url", "")))
            time.sleep(1)
    except Exception as e:
        print(f"   AngelList: {e}")
    return jobs


def scrape_devto():
    """Dev.to: community of developers, some job listings."""
    jobs = []
    try:
        # Dev.to API for job posts
        for page in range(1, 4):
            data = get_json("https://dev.to/api/articles",
                           params={"tag": "job", "page": page, "per_page": 30})
            if not data:
                break
            for article in data:
                if "job" in article.get("title", "").lower() or "hire" in article.get("title", "").lower():
                    jobs.append(job("Dev.to", article.get("title"), article.get("user", {}).get("name", ""),
                                    location=extract_location(article.get("description", "")),
                                    country=detect_countries(article.get("description", "")),
                                    category="Software Development",
                                    date=article.get("published_at", "")[:10],
                                    url=article.get("url", "")))
            time.sleep(1)
    except Exception as e:
        print(f"   Dev.to: {e}")
    return jobs


def scrape_upwork():
    """Upwork: freelance and project-based work (no API key needed for public board)."""
    jobs = []
    try:
        # Upwork RSS feed for job postings
        feed = feedparser.parse("https://www.upwork.com/ab/feed/jobs/rss?q=remote+entry+level&rss=1&sort=recency")
        for entry in feed.entries[:100]:
            title = entry.get("title", "")
            description = entry.get("summary", "")
            date = ""
            if entry.get("published_parsed"):
                date = time.strftime("%Y-%m-%d", entry.published_parsed)
            jobs.append(job("Upwork", title, "",
                            work_type="Remote",
                            location="Remote",
                            country="Worldwide",
                            job_type="Freelance, Project-based",
                            category="",
                            salary=extract_budget(description),
                            date=date,
                            url=entry.get("link", "")))
    except Exception as e:
        print(f"   Upwork: {e}")
    return jobs


def scrape_toptal():
    """Toptal: vetted remote freelancers and jobs (quality-focused)."""
    jobs = []
    try:
        # Toptal public jobs board
        data = get_json("https://www.toptal.com/api/rest/v2/jobs",
                       params={"limit": 100, "offset": 0, "status": "open"})
        for j in data.get("data", []):
            jobs.append(job("Toptal", j.get("title"), j.get("client", {}).get("company_name", ""),
                            work_type="Remote",
                            location="Remote",
                            country="Worldwide",
                            job_type=norm_job_type(j.get("type")),
                            category=j.get("skills", [{}])[0].get("name", "") if j.get("skills") else "",
                            salary=fmt_salary(j.get("budget_min"), j.get("budget_max"), "$"),
                            date=j.get("posted_at", "")[:10],
                            url=f"https://www.toptal.com/jobs/{j.get('slug')}" if j.get("slug") else ""))
    except Exception as e:
        print(f"   Toptal: {e}")
    return jobs


def extract_location(text):
    """Extract location from job description text."""
    text = (text or "").lower()
    if "remote" in text or "anywhere" in text or "worldwide" in text:
        return "Remote"
    # Try to find country mentions
    for country, aliases in COUNTRY_ALIASES.items():
        for alias in aliases[:3]:  # check first few aliases
            if alias in text:
                return alias.title()
    return ""


def extract_budget(text):
    """Extract budget/salary from Upwork job description."""
    import re
    text = (text or "")
    # Look for budget patterns like $1000-2000, $50/hr, etc.
    match = re.search(r'\$[\d,]+(?:-\$?[\d,]+)?', text)
    return match.group(0) if match else ""


SCRAPERS = [
    # Remote-only boards
    scrape_remotive, scrape_remoteok, scrape_himalayas, scrape_jobicy, scrape_weworkremotely,
    # All jobs (hybrid + onsite)
    scrape_arbeitnow, scrape_adzuna,
    # Freshers + Internships (INDIA-FOCUSED)
    scrape_internshala, scrape_unstop, scrape_firstnaukri, scrape_angellist,
    # Developer + Freelance
    scrape_devto, scrape_upwork, scrape_toptal,
    # Company career pages
    scrape_greenhouse, scrape_lever, scrape_ashby,
]


# ---------------- Main ----------------

def dedupe(jobs):
    seen, unique = set(), []
    for j in jobs:
        if not j["title"]:
            continue
        key = (j["title"].lower(), j["company"].lower())
        if j["work_type"] != "Remote":
            key += (j["location"].lower(),)  # same role in different offices = different jobs
        if key not in seen:
            seen.add(key)
            unique.append(j)
    return unique


def main():
    keywords = [k.lower() for k in sys.argv[1:]]
    all_jobs = []
    for scraper in SCRAPERS:
        name = scraper.__name__.replace("scrape_", "")
        print(f"-> {name} ...", end=" ", flush=True)
        try:
            results = scraper()
            print(f"{len(results)} jobs")
            all_jobs.extend(results)
        except Exception as e:
            print(f"failed ({e})")

    jobs = dedupe(all_jobs)
    if keywords:
        jobs = [j for j in jobs if any(k in j["title"].lower() for k in keywords)]
    jobs.sort(key=lambda j: j["date"], reverse=True)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(jobs)
    print(f"\nSaved {len(jobs)} unique jobs to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
