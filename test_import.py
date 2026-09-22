#!/usr/bin/env python3
"""Test script to check for import errors"""

try:
    print("Testing imports...")

    print("1. Importing remote_job_scraper...")
    import remote_job_scraper as rjs
    print("   ✓ remote_job_scraper imported")
    print(f"   - SCRAPERS: {len(rjs.SCRAPERS)} scrapers found")
    print(f"   - FIELDS: {rjs.FIELDS}")

    print("\n2. Importing db...")
    import db
    print("   ✓ db imported")

    print("\n3. Importing Flask modules...")
    from flask import Flask, jsonify, request
    from flask_cors import CORS
    print("   ✓ Flask modules imported")

    print("\n4. Creating Flask app...")
    app = Flask(__name__)
    CORS(app)
    print("   ✓ Flask app created")

    print("\n5. Checking for index.html...")
    import os
    if os.path.exists("index.html"):
        print("   ✓ index.html found")
    else:
        print("   ✗ index.html NOT found")

    print("\n✓ All imports successful!")

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
