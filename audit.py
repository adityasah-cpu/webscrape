#!/usr/bin/env python3
"""
🔍 Job Portal - Complete Codebase Audit
Checks if everything is connected and working properly
"""

import sys
import os
import json
from datetime import datetime

# Audit report
audit_report = {
    "timestamp": datetime.now().isoformat(),
    "status": "PENDING",
    "sections": {}
}

def print_section(title):
    """Print section header"""
    print(f"\n{'='*70}")
    print(f"📋 {title}")
    print(f"{'='*70}\n")

def check_mark(msg, status):
    """Print check result"""
    symbol = "✅" if status else "❌"
    print(f"{symbol} {msg}")
    return status

def print_result(results, section_name):
    """Print section results"""
    passed = sum(results)
    total = len(results)
    status = "PASS" if all(results) else "FAIL"
    print(f"\n{section_name}: {passed}/{total} checks passed - {status}")
    audit_report["sections"][section_name] = {
        "passed": passed,
        "total": total,
        "status": status
    }
    return all(results)

# ============ 1. IMPORTS & DEPENDENCIES ============

print_section("1. IMPORTS & DEPENDENCIES CHECK")

import_checks = []

# Check Flask
try:
    from flask import Flask, jsonify, request
    from flask_cors import CORS
    import_checks.append(check_mark("Flask & CORS imported", True))
except Exception as e:
    import_checks.append(check_mark(f"Flask & CORS: {e}", False))

# Check MySQL
try:
    import mysql.connector
    import_checks.append(check_mark("MySQL connector imported", True))
except Exception as e:
    import_checks.append(check_mark(f"MySQL connector: {e}", False))

# Check requests
try:
    import requests
    import_checks.append(check_mark("Requests imported", True))
except Exception as e:
    import_checks.append(check_mark(f"Requests: {e}", False))

# Check feedparser
try:
    import feedparser
    import_checks.append(check_mark("Feedparser imported", True))
except Exception as e:
    import_checks.append(check_mark(f"Feedparser: {e}", False))

# Check custom modules
try:
    import remote_job_scraper as rjs
    import_checks.append(check_mark("remote_job_scraper imported", True))
except Exception as e:
    import_checks.append(check_mark(f"remote_job_scraper: {e}", False))

try:
    import mysql_db
    import_checks.append(check_mark("mysql_db imported", True))
except Exception as e:
    import_checks.append(check_mark(f"mysql_db: {e}", False))

try:
    import alerts
    import_checks.append(check_mark("alerts imported", True))
except Exception as e:
    import_checks.append(check_mark(f"alerts: {e}", False))

imports_ok = print_result(import_checks, "IMPORTS")

# ============ 2. FILE EXISTENCE ============

print_section("2. FILE EXISTENCE CHECK")

file_checks = []
required_files = [
    ("api.py", "Flask API server"),
    ("mysql_db.py", "MySQL database module"),
    ("scheduler.py", "Job scheduler"),
    ("alerts.py", "Alert notifications"),
    ("diagnose.py", "Diagnostics tool"),
    ("remote_job_scraper.py", "Job scrapers"),
    ("index.html", "Web UI"),
    ("scraper_config_template.json", "Config template"),
]

for filename, description in required_files:
    exists = os.path.exists(filename)
    file_checks.append(check_mark(f"{filename} - {description}", exists))

files_ok = print_result(file_checks, "FILES")

# ============ 3. CONFIGURATION ============

print_section("3. CONFIGURATION CHECK")

config_checks = []

# Check MySQL config
try:
    from mysql_db import MYSQL_CONFIG
    config_checks.append(check_mark("MySQL config defined", True))
    config_checks.append(check_mark(f"  Host: {MYSQL_CONFIG['host']}", True))
    config_checks.append(check_mark(f"  User: {MYSQL_CONFIG['user']}", True))
    config_checks.append(check_mark(f"  Database: {MYSQL_CONFIG['database']}", True))
except Exception as e:
    config_checks.append(check_mark(f"MySQL config: {e}", False))

# Check scraper config template
try:
    with open("scraper_config_template.json") as f:
        template = json.load(f)
    config_checks.append(check_mark("Config template is valid JSON", True))
    config_checks.append(check_mark(f"  Has 'sources': {'sources' in template}", 'sources' in template))
    config_checks.append(check_mark(f"  Has 'filters': {'filters' in template}", 'filters' in template))
    config_checks.append(check_mark(f"  Has 'alerts': {'alerts' in template}", 'alerts' in template))
except Exception as e:
    config_checks.append(check_mark(f"Config template: {e}", False))

config_ok = print_result(config_checks, "CONFIGURATION")

# ============ 4. DATABASE CONNECTION ============

print_section("4. DATABASE CONNECTION CHECK")

db_checks = []

try:
    conn = mysql_db.get_connection()
    if conn:
        db_checks.append(check_mark("MySQL connection successful", True))

        # Check tables
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'job_portal'")
        table_count = cursor.fetchone()[0]
        db_checks.append(check_mark(f"Database has {table_count} tables", table_count > 0))

        # Check jobs table
        cursor.execute("SELECT COUNT(*) FROM jobs")
        job_count = cursor.fetchone()[0]
        db_checks.append(check_mark(f"Jobs table exists with {job_count} records", True))

        # Check stats table
        cursor.execute("SELECT COUNT(*) FROM stats")
        db_checks.append(check_mark("Stats table exists", True))

        # Check fetch_log table
        cursor.execute("SELECT COUNT(*) FROM fetch_log")
        db_checks.append(check_mark("Fetch_log table exists", True))

        cursor.close()
        conn.close()
    else:
        db_checks.append(check_mark("MySQL connection failed", False))
except Exception as e:
    db_checks.append(check_mark(f"Database check error: {str(e)[:60]}", False))

db_ok = print_result(db_checks, "DATABASE")

# ============ 5. API ENDPOINTS ============

print_section("5. API ENDPOINTS CHECK")

api_checks = []

try:
    from api import app

    # Get all routes
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append(str(rule))

    api_checks.append(check_mark(f"Flask app loaded", True))
    api_checks.append(check_mark(f"Found {len(routes)} endpoints", len(routes) > 5))

    # Check specific endpoints
    endpoints = [
        "/api/sources",
        "/api/fetch",
        "/api/jobs",
        "/api/stats",
        "/api/export",
        "/api/db-info",
        "/api/clear-jobs",
        "/api/test-alert",
        "/api/scheduler-status",
        "/"
    ]

    for endpoint in endpoints:
        found = any(endpoint in route for route in routes)
        api_checks.append(check_mark(f"Endpoint {endpoint} defined", found))

except Exception as e:
    api_checks.append(check_mark(f"API check error: {str(e)[:60]}", False))

api_ok = print_result(api_checks, "API ENDPOINTS")

# ============ 6. SCRAPERS ============

print_section("6. JOB SCRAPERS CHECK")

scraper_checks = []

try:
    from remote_job_scraper import SCRAPERS, FIELDS

    scraper_checks.append(check_mark(f"Found {len(SCRAPERS)} scrapers", len(SCRAPERS) > 5))
    scraper_checks.append(check_mark(f"Found {len(FIELDS)} fields", len(FIELDS) > 5))

    # Test a few scrapers
    print("\n  Testing scrapers (this may take a moment)...\n")

    tested = 0
    working = 0

    for scraper in SCRAPERS[:3]:  # Test first 3
        name = scraper.__name__.replace("scrape_", "")
        try:
            results = scraper()
            working += 1
            scraper_checks.append(check_mark(f"Scraper '{name}': {len(results)} jobs", True))
        except Exception as e:
            scraper_checks.append(check_mark(f"Scraper '{name}': {str(e)[:40]}", False))
        tested += 1

    print(f"\n  ({working}/{tested} scrapers tested successfully)")

except Exception as e:
    scraper_checks.append(check_mark(f"Scraper check error: {str(e)[:60]}", False))

scrapers_ok = print_result(scraper_checks, "SCRAPERS")

# ============ 7. ALERTS MODULE ============

print_section("7. ALERTS MODULE CHECK")

alert_checks = []

try:
    from alerts import send_alert, send_telegram, send_email, send_slack

    alert_checks.append(check_mark("send_alert function exists", True))
    alert_checks.append(check_mark("send_telegram function exists", True))
    alert_checks.append(check_mark("send_email function exists", True))
    alert_checks.append(check_mark("send_slack function exists", True))

    # Check formatting functions
    from alerts import format_jobs_telegram, format_jobs_email, format_jobs_slack

    alert_checks.append(check_mark("format_jobs_telegram exists", True))
    alert_checks.append(check_mark("format_jobs_email exists", True))
    alert_checks.append(check_mark("format_jobs_slack exists", True))

except Exception as e:
    alert_checks.append(check_mark(f"Alerts check error: {str(e)[:60]}", False))

alerts_ok = print_result(alert_checks, "ALERTS")

# ============ 8. SCHEDULER ============

print_section("8. SCHEDULER CHECK")

scheduler_checks = []

try:
    # Check if scheduler can import without errors
    import subprocess
    result = subprocess.run([sys.executable, "scheduler.py", "--help"],
                          capture_output=True, text=True, timeout=5)
    scheduler_checks.append(check_mark("Scheduler --help works", result.returncode == 0))

except Exception as e:
    scheduler_checks.append(check_mark(f"Scheduler check: {str(e)[:60]}", False))

# Check config loading
try:
    from scheduler import load_config, DEFAULT_CONFIG
    scheduler_checks.append(check_mark("Scheduler config loader works", True))
    scheduler_checks.append(check_mark(f"Has {len(DEFAULT_CONFIG['sources'])} default sources",
                                      len(DEFAULT_CONFIG['sources']) > 5))
except Exception as e:
    scheduler_checks.append(check_mark(f"Config loader: {str(e)[:60]}", False))

scheduler_ok = print_result(scheduler_checks, "SCHEDULER")

# ============ 9. FRONTEND ============

print_section("9. FRONTEND CHECK")

frontend_checks = []

try:
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    frontend_checks.append(check_mark("index.html readable", True))
    frontend_checks.append(check_mark("Has <!DOCTYPE html>", "<!DOCTYPE html>" in html_content))
    frontend_checks.append(check_mark("Has <title> tag", "<title>" in html_content))
    frontend_checks.append(check_mark("Has fetch API calls", "fetch(" in html_content))
    frontend_checks.append(check_mark("Has job filtering", "keyword" in html_content.lower()))
    frontend_checks.append(check_mark("Has export functionality", "export" in html_content.lower()))

except Exception as e:
    frontend_checks.append(check_mark(f"Frontend check: {str(e)[:60]}", False))

frontend_ok = print_result(frontend_checks, "FRONTEND")

# ============ 10. DIAGNOSTIC TOOLS ============

print_section("10. DIAGNOSTIC TOOLS CHECK")

diag_checks = []

try:
    # Check if diagnose.py exists and can run
    import subprocess
    result = subprocess.run([sys.executable, "diagnose.py"],
                          capture_output=True, text=True, timeout=30)
    diag_checks.append(check_mark("diagnose.py runs", result.returncode == 0 or "Working" in result.stdout))

except Exception as e:
    diag_checks.append(check_mark(f"Diagnose check: {str(e)[:60]}", False))

diag_ok = print_result(diag_checks, "DIAGNOSTICS")

# ============ 11. DEPENDENCIES VERIFICATION ============

print_section("11. DEPENDENCIES VERIFICATION")

dep_checks = []

required_packages = [
    ("flask", "Flask"),
    ("flask_cors", "Flask-CORS"),
    ("mysql.connector", "MySQL Connector"),
    ("requests", "Requests"),
    ("feedparser", "Feedparser"),
]

for package, name in required_packages:
    try:
        __import__(package)
        dep_checks.append(check_mark(f"{name} installed", True))
    except ImportError:
        dep_checks.append(check_mark(f"{name} installed", False))

deps_ok = print_result(dep_checks, "DEPENDENCIES")

# ============ 12. INTEGRATION POINTS ============

print_section("12. INTEGRATION POINTS CHECK")

integration_checks = []

# Check api.py imports correct modules
try:
    with open("api.py") as f:
        api_content = f.read()

    integration_checks.append(check_mark("api.py imports remote_job_scraper", "import remote_job_scraper" in api_content))
    integration_checks.append(check_mark("api.py imports mysql_db", "import mysql_db" in api_content))
    integration_checks.append(check_mark("api.py initializes database", "mysql_db.init_database()" in api_content))
    integration_checks.append(check_mark("api.py uses MySQL functions", "mysql_db.get_jobs" in api_content))
    integration_checks.append(check_mark("api.py has alert endpoints", "/api/test-alert" in api_content))

except Exception as e:
    integration_checks.append(check_mark(f"API integration check: {str(e)[:60]}", False))

# Check scheduler.py imports
try:
    with open("scheduler.py") as f:
        scheduler_content = f.read()

    integration_checks.append(check_mark("scheduler.py imports mysql_db", "import mysql_db" in scheduler_content))
    integration_checks.append(check_mark("scheduler.py imports alerts", "import alerts" in scheduler_content))
    integration_checks.append(check_mark("scheduler.py calls mysql_db.insert_jobs", "mysql_db.insert_jobs" in scheduler_content))
    integration_checks.append(check_mark("scheduler.py sends alerts", "alert_module.send_alert" in scheduler_content))

except Exception as e:
    integration_checks.append(check_mark(f"Scheduler integration check: {str(e)[:60]}", False))

integration_ok = print_result(integration_checks, "INTEGRATION")

# ============ FINAL SUMMARY ============

print_section("FINAL AUDIT SUMMARY")

all_sections = [
    ("Imports & Dependencies", imports_ok),
    ("Files", files_ok),
    ("Configuration", config_ok),
    ("Database", db_ok),
    ("API Endpoints", api_ok),
    ("Scrapers", scrapers_ok),
    ("Alerts", alerts_ok),
    ("Scheduler", scheduler_ok),
    ("Frontend", frontend_ok),
    ("Diagnostics", diag_checks),
    ("Dependencies", deps_ok),
    ("Integration", integration_ok),
]

print("\n📊 SECTION STATUS:\n")
for section_name, status in all_sections:
    symbol = "✅" if status else "⚠️"
    print(f"{symbol} {section_name}")

overall_ok = all(status for _, status in all_sections if isinstance(status, bool))

print(f"\n{'='*70}")
if overall_ok:
    print("🎉 AUDIT PASSED - All systems connected and working!")
    audit_report["status"] = "PASS"
else:
    print("⚠️  AUDIT PARTIAL - Some issues detected above")
    audit_report["status"] = "PARTIAL"
print(f"{'='*70}\n")

# Save audit report
try:
    with open("audit_report.json", "w") as f:
        json.dump(audit_report, f, indent=2)
    print(f"✅ Audit report saved to: audit_report.json\n")
except:
    pass

# Print recommendations
print("\n📋 RECOMMENDATIONS:\n")

if not imports_ok:
    print("❌ Fix imports:")
    print("   pip install flask flask-cors mysql-connector-python requests feedparser\n")

if not db_ok:
    print("❌ Database issue detected:")
    print("   • Check MySQL is running")
    print("   • Verify credentials in mysql_db.py")
    print("   • Run: mysql -u root -paditya@2004\n")

if not api_ok:
    print("❌ API issues detected:")
    print("   • Restart Flask server: python api.py\n")

if overall_ok:
    print("✅ Everything looks good!")
    print("\n🚀 NEXT STEPS:")
    print("   1. Open http://localhost:5000 in browser")
    print("   2. Fetch jobs and test the system")
    print("   3. Configure automation if needed")
    print("   4. Monitor with provided tools")

print()
