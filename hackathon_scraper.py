"""
Hackathon scraper
------------------
Pulls currently-open hackathon listings from Devpost's public API
(https://devpost.com/api/hackathons) - confirmed working and
unauthenticated as of this writing. Other candidate sources (Unstop's
hackathon category specifically) were checked and found blocked
(403 Forbidden from CloudFront) even though Unstop's internship category
works fine for remote_job_scraper.py - so Devpost is the only source
wired in until another one is confirmed to have real public access.
"""

import html
import logging
import re
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (job-scraper; personal use)"}
TIMEOUT = 30

FIELDS = ["source", "title", "organizer", "location", "prize_amount",
          "themes", "registrations_count", "submission_dates",
          "time_left", "url"]


def _clean(text: Any) -> str:
    text = html.unescape(str(text or ""))
    return re.sub(r"<[^>]+>", "", text).strip()


def _hackathon(
    source: str,
    title: str,
    organizer: str,
    *,
    location: str = "",
    prize_amount: str = "",
    themes: Any = None,
    registrations_count: Any = "",
    submission_dates: str = "",
    time_left: str = "",
    url: str = "",
) -> Dict[str, str]:
    return {
        "source": source,
        "title": _clean(title),
        "organizer": _clean(organizer),
        "location": _clean(location) or "Online",
        "prize_amount": _clean(prize_amount),
        "themes": ", ".join(_clean(t) for t in (themes or [])),
        "registrations_count": str(registrations_count or ""),
        "submission_dates": _clean(submission_dates),
        "time_left": _clean(time_left),
        "url": url or "",
    }


def scrape_devpost_hackathons(max_pages: int = 6) -> List[Dict[str, Any]]:
    """Fetch currently-open hackathons from Devpost's public API, up to
    max_pages (9 per page per Devpost's own pagination, so 6 pages = up to
    ~54 hackathons - comfortably covers the ~48 open at any given time)."""
    hackathons = []
    for page in range(1, max_pages + 1):
        try:
            r = requests.get(
                "https://devpost.com/api/hackathons",
                params={"status[]": "open", "page": page},
                headers=HEADERS, timeout=TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning(f"Devpost request failed on page {page}: {e}")
            break

        batch = data.get("hackathons", [])
        if not batch:
            break

        for h in batch:
            loc = (h.get("displayed_location") or {}).get("location", "")
            hackathons.append(_hackathon(
                "Devpost", h.get("title"), h.get("organization_name"),
                location=loc,
                prize_amount=h.get("prize_amount"),
                themes=[t.get("name") for t in (h.get("themes") or [])],
                registrations_count=h.get("registrations_count"),
                submission_dates=h.get("submission_period_dates"),
                time_left=h.get("time_left_to_submission"),
                url=h.get("url"),
            ))

        total_count = (data.get("meta") or {}).get("total_count", 0)
        if page * 9 >= total_count:
            break

    logger.info(f"Devpost: {len(hackathons)} open hackathons")
    return hackathons


SCRAPERS = [scrape_devpost_hackathons]
