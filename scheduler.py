"""
Job Scraper Scheduler for Job Portal
Fetches jobs automatically and stores in PostgreSQL database with alerts

Usage:
    python scheduler.py                              # Run once
    python scheduler.py --daemon                     # Run continuously every N hours
    python scheduler.py --cron                       # Print cron command to set up
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import remote_job_scraper as rjs
import postgres_db
import alerts as alert_module

# Configuration file
CONFIG_FILE = "scraper_config.json"

# Default config
DEFAULT_CONFIG = {
    "sources": [
        "remotive", "remoteok", "himalayas", "jobicy", "weworkremotely",
        "internshala", "unstop", "firstnaukri", "angellist",
        "devto", "upwork", "toptal"
    ],
    "filters": {
        "work_type": ["Remote", "Hybrid"],
        "countries": ["India"],
        "job_types": ["Full-time", "Internship"],
        "keywords": [],
    },
    "alerts": {
        "enabled": False,
        "telegram": None,
        "email": None,
        "slack": None,
    },
    "schedule": {
        "interval_hours": 8,
        "send_alert_if_new": True,
        "alert_after_hours": 24,
    }
}


def load_config():
    """Load or create config file."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    else:
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"✓ Created {CONFIG_FILE}. Edit it to customize filters and alerts.")
        return DEFAULT_CONFIG


def run_once(config):
    """Fetch jobs once and store in MySQL database with alerts."""
    print(f"\n{'='*70}")
    print(f"🚀 Job Scraper Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    # Initialize MySQL database
    postgres_db.init_database()

    # Build scraper list
    sources = {s.__name__.replace("scrape_", ""): s for s in rjs.SCRAPERS}
    enabled = [sources[name] for name in config["sources"] if name in sources]

    print(f"📌 Enabled sources: {', '.join([s.__name__.replace('scrape_', '') for s in enabled])}\n")

    # Fetch jobs
    all_jobs = []
    status = {}

    for scraper in enabled:
        name = scraper.__name__.replace("scrape_", "")
        print(f"  ⏳ Fetching {name}...", end=" ", flush=True)
        try:
            results = scraper()
            print(f"✅ {len(results)} jobs")
            all_jobs.extend(results)
            status[name] = {"success": True, "count": len(results)}
        except Exception as e:
            print(f"❌ {str(e)[:50]}")
            status[name] = {"success": False, "error": str(e)[:50]}

    # Dedupe
    jobs = rjs.dedupe(all_jobs)
    print(f"\n📊 After dedup: {len(jobs)} unique jobs\n")

    # Apply filters
    filtered = []
    for j in jobs:
        # Work type filter
        if config["filters"]["work_type"]:
            if j.get("work_type") not in config["filters"]["work_type"]:
                continue

        # Country filter
        if config["filters"]["countries"]:
            job_countries = set(j.get("country", "").split(";"))
            if not job_countries & set(config["filters"]["countries"]):
                continue

        # Job type filter
        if config["filters"]["job_types"]:
            job_types = {t.strip() for t in j.get("job_type", "").split(",")}
            if not job_types & set(config["filters"]["job_types"]):
                continue

        # Keywords filter
        if config["filters"]["keywords"]:
            text = (j.get("title", "") + " " + j.get("company", "")).lower()
            if not any(k.lower() in text for k in config["filters"]["keywords"]):
                continue

        filtered.append(j)

    print(f"🎯 After filters: {len(filtered)} matching jobs\n")

    # Store in MySQL database
    insert_result = postgres_db.insert_jobs(filtered)
    new_count = insert_result["inserted"]
    skipped = insert_result["skipped"]

    print(f"💾 Database update:")
    print(f"   - New jobs added: {new_count}")
    print(f"   - Duplicates skipped: {skipped}\n")

    # Log fetch operation
    postgres_db.log_fetch(config["sources"], len(jobs), status)

    # Send alerts if enabled and there are new jobs
    if config["alerts"]["enabled"] and new_count > 0:
        print(f"📬 Sending alerts for {new_count} new jobs...")

        alert_config = {}
        if config["alerts"].get("telegram"):
            alert_config["telegram"] = config["alerts"]["telegram"]
        if config["alerts"].get("email"):
            alert_config["email"] = config["alerts"]["email"]
        if config["alerts"].get("slack"):
            alert_config["slack"] = config["alerts"]["slack"]

        if alert_config:
            try:
                # Get recently added jobs
                recent_jobs_result = postgres_db.get_jobs(page=1, limit=new_count)
                alert_jobs = recent_jobs_result["jobs"]

                if alert_jobs:
                    results = alert_module.send_alert(alert_jobs, alert_config)
                    print(f"   Results: {results}\n")
            except Exception as e:
                print(f"   ❌ Error sending alerts: {e}\n")
        else:
            print(f"   ⚠️  Alerts enabled but no channels configured.\n")

    # Get and display statistics
    stats = postgres_db.get_statistics()
    print(f"📈 Database Statistics:")
    print(f"   Total jobs: {stats['total']}")
    print(f"   By work type: {stats['by_work_type']}")
    print(f"   By country: {list(stats['by_country'].keys())[:5]}...")
    print(f"   By source: {stats['by_source']}\n")

    print(f"{'='*70}\n")
    return new_count


def daemon_mode(config):
    """Run continuously on schedule."""
    interval = config["schedule"]["interval_hours"] * 3600

    print(f"\n🔄 Starting daemon mode. Running every {config['schedule']['interval_hours']} hours.")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            run_once(config)
            print(f"⏰ Next run in {config['schedule']['interval_hours']} hours...\n")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\n✋ Daemon stopped.")


def print_cron_command(config):
    """Print cron command for scheduling."""
    interval = config["schedule"]["interval_hours"]

    if interval == 1:
        cron = "0 * * * *"
    elif interval == 6:
        cron = "0 0,6,12,18 * * *"
    elif interval == 8:
        cron = "0 0,8,16 * * *"
    elif interval == 12:
        cron = "0 0,12 * * *"
    else:
        cron = "0 */6 * * *"

    script_path = os.path.abspath(__file__)

    print(f"\n📋 To set up automatic job scraping every {interval} hours:\n")
    print(f"1. Open crontab:")
    print(f"   crontab -e\n")
    print(f"2. Add this line:")
    print(f"   {cron} cd {os.path.dirname(script_path)} && python {script_path} >> scheduler.log 2>&1\n")
    print(f"3. Verify it's working:")
    print(f"   tail -f scheduler.log\n")


def main():
    parser = argparse.ArgumentParser(description="Job Portal - Automated Scraper Scheduler")
    parser.add_argument("--daemon", action="store_true", help="Run continuously every N hours")
    parser.add_argument("--cron", action="store_true", help="Print cron setup command")
    parser.add_argument("--config", default=CONFIG_FILE, help="Config file path")
    args = parser.parse_args()

    config = load_config()

    if args.cron:
        print_cron_command(config)
    elif args.daemon:
        daemon_mode(config)
    else:
        run_once(config)


if __name__ == "__main__":
    main()
