"""
Diagnostic script - test each scraper independently
Helps identify which sources are working and which are failing
"""

import sys
import time

# Test each scraper
def test_scrapers():
    import remote_job_scraper as rjs
    
    sources = {s.__name__.replace("scrape_", ""): s for s in rjs.SCRAPERS}
    
    print("=" * 60)
    print("JOB SCRAPER DIAGNOSTIC")
    print("=" * 60)
    print(f"\nTesting {len(sources)} sources...\n")
    
    working = []
    failed = []
    
    for name, scraper in sources.items():
        print(f"Testing {name}...", end=" ", flush=True)
        try:
            results = scraper()
            if results:
                print(f"✅ {len(results)} jobs")
                working.append((name, len(results)))
            else:
                print("⚠️  0 jobs (no data)")
                failed.append((name, "No data returned"))
        except Exception as e:
            error_msg = str(e)[:50]  # First 50 chars of error
            print(f"❌ {error_msg}")
            failed.append((name, error_msg))
        time.sleep(0.5)  # Be polite to servers
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    print(f"\n✅ Working ({len(working)}):")
    for name, count in sorted(working, key=lambda x: -x[1]):
        print(f"   {name}: {count} jobs")
    
    if failed:
        print(f"\n❌ Failed ({len(failed)}):")
        for name, error in failed:
            print(f"   {name}: {error}")
    else:
        print("\n🎉 ALL SOURCES WORKING!")
    
    print("\n" + "=" * 60)
    
    return len(working), len(failed)


def check_dependencies():
    """Check if required packages are installed"""
    print("\nChecking dependencies...")
    print("-" * 60)
    
    packages = {
        "requests": "HTTP requests",
        "feedparser": "RSS feeds",
        "pandas": "Data handling",
        "streamlit": "Web UI",
    }
    
    missing = []
    for pkg, desc in packages.items():
        try:
            __import__(pkg)
            print(f"✅ {pkg}: {desc}")
        except ImportError:
            print(f"❌ {pkg}: {desc} - MISSING")
            missing.append(pkg)
    
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print(f"\nTo install: pip install {' '.join(missing)}")
        return False
    return True


def test_network():
    """Test basic network connectivity"""
    print("\nChecking network connectivity...")
    print("-" * 60)
    
    import requests
    
    test_urls = [
        ("Google DNS", "https://8.8.8.8"),
        ("Remotive", "https://remotive.com/api/remote-jobs"),
        ("Internshala", "https://internshala.com/api/v2/internship_search_results/"),
    ]
    
    for name, url in test_urls:
        try:
            r = requests.get(url, timeout=5)
            status = r.status_code
            if 200 <= status < 300:
                print(f"✅ {name}: {status} OK")
            else:
                print(f"⚠️  {name}: {status} (may be blocked)")
        except requests.exceptions.Timeout:
            print(f"❌ {name}: Timeout (slow connection)")
        except requests.exceptions.ConnectionError:
            print(f"❌ {name}: Connection error (blocked/down)")
        except Exception as e:
            print(f"❌ {name}: {str(e)[:40]}")


def main():
    print("\n🔍 Job Scraper Diagnostic Tool\n")
    
    # Check dependencies
    if not check_dependencies():
        print("\n⚠️  Install missing packages and try again.")
        sys.exit(1)
    
    # Check network
    test_network()
    
    # Test scrapers
    print("\n")
    working, failed = test_scrapers()
    
    # Recommendations
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    
    if working > 0:
        print(f"\n✅ Good news! {working} sources are working.")
        if failed > 0:
            print(f"⚠️  {failed} sources failed. This can happen if:")
            print("   • The website changed its API")
            print("   • Your IP is rate-limited")
            print("   • The site is temporarily down")
            print(f"\n💡 Try again in a few minutes, or use only the {working} working sources.")
    else:
        print("\n❌ All sources failed. Possible causes:")
        print("   1. Internet connection issue (check network test above)")
        print("   2. All job sites are down or blocked")
        print("   3. Your ISP/network is blocking these sites")
        print("\n💡 Solutions:")
        print("   • Check your internet connection")
        print("   • Try again in a few minutes")
        print("   • Try from a different network (mobile hotspot)")
        print("   • Check if your ISP blocks job board APIs")
    
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
