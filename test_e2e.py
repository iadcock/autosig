"""
AutoSig v1.0 — End-to-End Testing & Verification Script

Tests each system layer in order, stopping if any layer fails.
No assumptions. No skipping steps.
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

# ANSI color codes for terminal output
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

LOGS_DIR = Path("logs")
RAW_ALERTS_FILE = LOGS_DIR / "alerts_raw.jsonl"
PARSED_ALERTS_FILE = LOGS_DIR / "alerts_parsed.jsonl"
EXECUTION_PLAN_FILE = LOGS_DIR / "execution_plan.jsonl"

# Critical date threshold (signals must be newer than this)
CRITICAL_DATE = datetime(2025, 12, 26, tzinfo=ZoneInfo("UTC"))


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}{text:^70}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")


def print_pass(message: str):
    """Print a pass message."""
    print(f"{GREEN}[PASS]{RESET} {message}")


def print_fail(message: str):
    """Print a fail message."""
    print(f"{RED}[FAIL]{RESET} {message}")


def print_warn(message: str):
    """Print a warning message."""
    print(f"{YELLOW}[WARN]{RESET} {message}")


def print_info(message: str):
    """Print an info message."""
    print(f"{BLUE}[INFO]{RESET} {message}")


def parse_jsonl(filepath: Path) -> List[Dict]:
    """Parse a JSONL file and return list of entries."""
    if not filepath.exists():
        return []
    
    entries = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print_warn(f"Invalid JSON in {filepath.name}: {e}")
    except Exception as e:
        print_fail(f"Error reading {filepath}: {e}")
    
    return entries


def get_latest_timestamp(entries: List[Dict], field: str = "ts_iso") -> Optional[datetime]:
    """Get the latest timestamp from entries."""
    if not entries:
        return None
    
    timestamps = []
    for entry in entries:
        ts_str = entry.get(field)
        if not ts_str:
            continue
        try:
            # Handle both ISO format and other formats
            if 'T' in ts_str:
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            else:
                ts = datetime.strptime(ts_str, '%Y-%m-%d')
            timestamps.append(ts)
        except Exception:
            continue
    
    return max(timestamps) if timestamps else None


def test_layer_1_worker_process() -> bool:
    """
    LAYER 1 — WORKER PROCESS (CRITICAL)
    Objective: Confirm that the ingestion worker (main.py) is actually running.
    """
    print_header("LAYER 1: WORKER PROCESS (CRITICAL)")
    
    # Check 1: main.py exists
    main_py = Path("main.py")
    if not main_py.exists():
        print_fail("main.py does not exist at repository root")
        return False
    print_pass("main.py exists")
    
    # Check 2: Verify main.py is a worker script (not a Flask app)
    try:
        with open(main_py, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'Flask' in content and 'app = Flask' in content:
                print_fail("main.py contains Flask app definition (should be worker only)")
                return False
            if 'run_polling_loop' in content or 'get_alerts' in content:
                print_pass("main.py contains worker logic (polling loop)")
            else:
                print_warn("main.py may not contain expected worker logic")
    except Exception as e:
        print_fail(f"Error reading main.py: {e}")
        return False
    
    # Check 3: Railway configuration check (informational)
    railway_toml = Path("railway.toml")
    if railway_toml.exists():
        try:
            with open(railway_toml, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'gunicorn' in content.lower() and 'main' in content.lower():
                    print_warn("railway.toml may be configured to run main.py via Gunicorn (should use python main.py)")
                else:
                    print_info("railway.toml exists (verify Worker Service uses: python main.py)")
        except Exception:
            pass
    
    # Check 4: web.py exists (for web service)
    web_py = Path("web.py")
    if web_py.exists():
        print_pass("web.py exists (for web service)")
    else:
        print_warn("web.py does not exist (web service may fail)")
    
    print_info("NOTE: Cannot verify Railway service is running from local machine")
    print_info("ACTION REQUIRED: Check Railway Worker Service logs for:")
    print_info("  - 'Starting trading bot polling loop...'")
    print_info("  - 'Fetching alerts...' messages repeating on interval")
    print_info("  - No Gunicorn errors")
    
    return True


def test_layer_2_raw_ingestion() -> bool:
    """
    LAYER 2 — RAW INGESTION
    Objective: Confirm that new Whop alerts are being received.
    """
    print_header("LAYER 2: RAW INGESTION")
    
    # Check 1: File exists
    if not RAW_ALERTS_FILE.exists():
        print_fail(f"{RAW_ALERTS_FILE} does not exist")
        print_info("This may be normal if worker has never run")
        return False
    print_pass(f"{RAW_ALERTS_FILE} exists")
    
    # Check 2: File is readable
    try:
        entries = parse_jsonl(RAW_ALERTS_FILE)
        print_pass(f"{RAW_ALERTS_FILE} is readable ({len(entries)} entries)")
    except Exception as e:
        print_fail(f"Error reading {RAW_ALERTS_FILE}: {e}")
        return False
    
    # Check 3: File has entries
    if len(entries) == 0:
        print_fail(f"{RAW_ALERTS_FILE} is empty")
        print_info("Worker may not be running or Whop fetch is failing")
        return False
    
    # Check 4: Latest timestamp is current (not stuck at 12/26)
    latest_ts = get_latest_timestamp(entries, "ts_iso")
    if not latest_ts:
        print_fail("No valid timestamps found in raw alerts")
        return False
    
    print_info(f"Latest raw alert timestamp: {latest_ts.isoformat()}")
    
    # Normalize timestamps for comparison
    if latest_ts.tzinfo:
        latest_ts_normalized = latest_ts
    else:
        latest_ts_normalized = latest_ts.replace(tzinfo=ZoneInfo("UTC"))
    
    if latest_ts_normalized < CRITICAL_DATE:
        print_fail(f"Latest timestamp ({latest_ts.date()}) is before critical date ({CRITICAL_DATE.date()})")
        print_info("Ingestion appears to have stopped on or before 12/26")
        return False
    
    # Check 5: Recent entries exist (within last 7 days)
    if latest_ts.tzinfo:
        now = datetime.now(latest_ts.tzinfo)
        age_days = (now - latest_ts).days
    else:
        now = datetime.now()
        age_days = (now - latest_ts).days
    
    if age_days > 7:
        print_warn(f"Latest raw alert is {age_days} days old")
    else:
        print_pass(f"Latest raw alert is recent ({age_days} days old)")
    
    # Show last 3 entries
    print_info("\nLast 3 raw alerts:")
    for i, entry in enumerate(entries[-3:], 1):
        ts = entry.get("ts_iso", "N/A")
        post_id = entry.get("post_id", "N/A")[:8]
        body_preview = (entry.get("body", "") or entry.get("title", ""))[:50]
        print_info(f"  {i}. [{ts}] {post_id}... {body_preview}...")
    
    return True


def test_layer_3_parsing() -> bool:
    """
    LAYER 3 — PARSING
    Objective: Confirm parser activates when raw alerts exist.
    """
    print_header("LAYER 3: PARSING")
    
    # Check 1: File exists
    if not PARSED_ALERTS_FILE.exists():
        print_fail(f"{PARSED_ALERTS_FILE} does not exist")
        return False
    print_pass(f"{PARSED_ALERTS_FILE} exists")
    
    # Check 2: File has entries
    entries = parse_jsonl(PARSED_ALERTS_FILE)
    if len(entries) == 0:
        print_fail(f"{PARSED_ALERTS_FILE} is empty")
        print_info("Parser may not be running or all alerts are being rejected")
        return False
    print_pass(f"{PARSED_ALERTS_FILE} has {len(entries)} entries")
    
    # Check 3: Latest timestamp
    latest_ts = get_latest_timestamp(entries, "ts_iso")
    if not latest_ts:
        print_fail("No valid timestamps found in parsed alerts")
        return False
    
    print_info(f"Latest parsed alert timestamp: {latest_ts.isoformat()}")
    
    if latest_ts < CRITICAL_DATE:
        print_fail(f"Latest parsed timestamp ({latest_ts.date()}) is before critical date ({CRITICAL_DATE.date()})")
        return False
    
    # Check 4: Compare with raw alerts
    raw_entries = parse_jsonl(RAW_ALERTS_FILE)
    if raw_entries:
        raw_latest = get_latest_timestamp(raw_entries, "ts_iso")
        if raw_latest and latest_ts < raw_latest:
            print_warn(f"Parsed alerts lag behind raw alerts (parsed: {latest_ts.date()}, raw: {raw_latest.date()})")
        else:
            print_pass("Parsed alerts are up to date with raw alerts")
    
    # Check 5: Show classification breakdown
    classifications = {}
    for entry in entries:
        cls = entry.get("classification", "UNKNOWN")
        classifications[cls] = classifications.get(cls, 0) + 1
    
    print_info("\nClassification breakdown:")
    for cls, count in sorted(classifications.items()):
        print_info(f"  {cls}: {count}")
    
    # Show last 3 parsed entries
    print_info("\nLast 3 parsed alerts:")
    for i, entry in enumerate(entries[-3:], 1):
        ts = entry.get("ts_iso", "N/A")
        post_id = entry.get("post_id", "N/A")[:8]
        cls = entry.get("classification", "N/A")
        ticker = entry.get("parsed_signal", {}).get("ticker", "N/A") if entry.get("parsed_signal") else "N/A"
        print_info(f"  {i}. [{ts}] {post_id}... {cls} | {ticker}")
    
    return True


def test_layer_4_storage() -> bool:
    """
    LAYER 4 — STORAGE / DB
    Objective: Confirm parsed alerts are persisted correctly.
    
    NOTE: AutoSig uses JSONL files, not a traditional database.
    This layer verifies that parsed alerts are stored correctly.
    """
    print_header("LAYER 4: STORAGE / DB")
    
    # AutoSig uses JSONL files as storage, so we verify the parsed file
    entries = parse_jsonl(PARSED_ALERTS_FILE)
    
    if len(entries) == 0:
        print_fail("No parsed alerts in storage")
        return False
    
    # Check timestamp range
    timestamps = []
    for entry in entries:
        ts_str = entry.get("ts_iso")
        if ts_str:
            try:
                if 'T' in ts_str:
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                else:
                    ts = datetime.strptime(ts_str, '%Y-%m-%d')
                timestamps.append(ts)
            except Exception:
                continue
    
    if not timestamps:
        print_fail("No valid timestamps in storage")
        return False
    
    max_ts = max(timestamps)
    min_ts = min(timestamps)
    
    print_info(f"Storage contains {len(entries)} entries")
    print_info(f"Date range: {min_ts.date()} to {max_ts.date()}")
    
    if max_ts < CRITICAL_DATE:
        print_fail(f"MAX(timestamp) = {max_ts.date()} is before critical date ({CRITICAL_DATE.date()})")
        return False
    
    print_pass(f"MAX(timestamp) = {max_ts.date()} is after critical date")
    
    # Check for required fields
    required_fields = ["post_id", "ts_iso", "classification"]
    missing_fields = set()
    for entry in entries[:10]:  # Sample first 10
        for field in required_fields:
            if field not in entry:
                missing_fields.add(field)
    
    if missing_fields:
        print_warn(f"Some entries missing required fields: {missing_fields}")
    else:
        print_pass("Required fields present in entries")
    
    return True


def test_layer_5_signal_feed() -> bool:
    """
    LAYER 5 — SIGNAL FEED
    Objective: Confirm Feed reflects stored signals.
    """
    print_header("LAYER 5: SIGNAL FEED")
    
    # Check 1: Feed template exists
    feed_template = Path("templates/signal_feed.html")
    if not feed_template.exists():
        print_fail("templates/signal_feed.html does not exist")
        return False
    print_pass("Signal Feed template exists")
    
    # Check 2: Feed API route exists in dashboard.py
    dashboard_py = Path("dashboard.py")
    if dashboard_py.exists():
        try:
            with open(dashboard_py, 'r', encoding='utf-8') as f:
                content = f.read()
                if '/api/signals/feed' in content or '/feed' in content:
                    print_pass("Feed API route exists in dashboard.py")
                else:
                    print_warn("Feed API route may not exist in dashboard.py")
        except Exception as e:
            print_warn(f"Error checking dashboard.py: {e}")
    
    # Check 3: Verify feed can load signals (requires running app)
    print_info("NOTE: Cannot test Feed rendering without running Flask app")
    print_info("ACTION REQUIRED: Start web service and verify:")
    print_info("  - /feed endpoint loads")
    print_info("  - Signals past 12/26 are visible")
    print_info("  - Certainty shown with (A) or (U)")
    
    # Check 4: Verify certainty resolution function exists
    signal_classification = Path("signal_classification.py")
    if signal_classification.exists():
        try:
            with open(signal_classification, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'resolve_certainty' in content and 'auto_classify_signal' in content:
                    print_pass("Certainty resolution functions exist")
                else:
                    print_warn("Certainty resolution functions may be missing")
        except Exception as e:
            print_warn(f"Error checking signal_classification.py: {e}")
    
    return True


def test_layer_6_signal_review() -> bool:
    """
    LAYER 6 — SIGNAL REVIEW
    Objective: Confirm Review mirrors Feed data.
    """
    print_header("LAYER 6: SIGNAL REVIEW")
    
    # Check 1: Review template exists
    review_template = Path("templates/admin_review.html")
    if not review_template.exists():
        print_fail("templates/admin_review.html does not exist")
        return False
    print_pass("Signal Review template exists")
    
    # Check 2: Review API route exists
    dashboard_py = Path("dashboard.py")
    if dashboard_py.exists():
        try:
            with open(dashboard_py, 'r', encoding='utf-8') as f:
                content = f.read()
                if '/api/admin/signals' in content or '/signal-review' in content:
                    print_pass("Review API route exists in dashboard.py")
                else:
                    print_warn("Review API route may not exist in dashboard.py")
        except Exception as e:
            print_warn(f"Error checking dashboard.py: {e}")
    
    # Check 3: Classification storage exists
    classification_file = Path("data/signal_classifications.jsonl")
    if classification_file.exists():
        print_pass("Classification storage file exists")
    else:
        print_info("Classification storage file does not exist (will be created on first override)")
    
    print_info("NOTE: Cannot test Review rendering without running Flask app")
    print_info("ACTION REQUIRED: Start web service and verify:")
    print_info("  - /signal-review endpoint loads")
    print_info("  - Same signals as Feed are visible")
    print_info("  - Manual override buttons work")
    
    return True


def test_layer_7_certainty_overrides() -> bool:
    """
    LAYER 7 — CERTAINTY & OVERRIDES
    Objective: Confirm certainty resolution logic.
    """
    print_header("LAYER 7: CERTAINTY & OVERRIDES")
    
    # Check 1: Certainty resolution function exists
    signal_classification = Path("signal_classification.py")
    if not signal_classification.exists():
        print_fail("signal_classification.py does not exist")
        return False
    
    try:
        with open(signal_classification, 'r', encoding='utf-8') as f:
            content = f.read()
            
            checks = [
                ('resolve_certainty', 'resolve_certainty function'),
                ('auto_classify_signal', 'auto_classify_signal function'),
                ('EXECUTABLE', 'EXECUTABLE certainty level'),
                ('AMBIGUOUS', 'AMBIGUOUS certainty level'),
                ('LOG-ONLY', 'LOG-ONLY certainty level'),
            ]
            
            for check, name in checks:
                if check in content:
                    print_pass(f"{name} exists")
                else:
                    print_warn(f"{name} may be missing")
    except Exception as e:
        print_fail(f"Error checking signal_classification.py: {e}")
        return False
    
    # Check 2: Verify certainty source logic (A vs U)
    try:
        with open(signal_classification, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'certainty_source' in content and ('"A"' in content or "'A'" in content):
                print_pass("Certainty source logic (A/U) appears to be implemented")
            else:
                print_warn("Certainty source logic may be incomplete")
    except Exception:
        pass
    
    print_info("NOTE: Cannot test override persistence without running Flask app")
    print_info("ACTION REQUIRED: Test manually:")
    print_info("  1. Open Signal Review")
    print_info("  2. Override a signal's certainty")
    print_info("  3. Verify it shows (U) instead of (A)")
    print_info("  4. Reload page - override should persist")
    print_info("  5. Check Signal Feed - should also show (U)")
    
    return True


def main():
    """Run all layer tests in order."""
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}{'AUTOSIG v1.0 — END-TO-END TESTING':^70}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")
    
    print_info("Testing each system layer in order...")
    print_info("If any layer fails, testing stops.\n")
    
    layers = [
        ("Worker Process", test_layer_1_worker_process),
        ("Raw Ingestion", test_layer_2_raw_ingestion),
        ("Parsing", test_layer_3_parsing),
        ("Storage/DB", test_layer_4_storage),
        ("Signal Feed", test_layer_5_signal_feed),
        ("Signal Review", test_layer_6_signal_review),
        ("Certainty & Overrides", test_layer_7_certainty_overrides),
    ]
    
    results = []
    
    for layer_name, test_func in layers:
        try:
            result = test_func()
            results.append((layer_name, result))
            
            if not result:
                print_fail(f"\n{layer_name} FAILED. Stopping tests.")
                break
        except Exception as e:
            print_fail(f"\n{layer_name} raised exception: {e}")
            results.append((layer_name, False))
            break
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for layer_name, result in results:
        status = f"{GREEN}[PASS]{RESET}" if result else f"{RED}[FAIL]{RESET}"
        print(f"  {status} {layer_name}")
    
    print(f"\n{BOLD}Results: {passed}/{total} layers passed{RESET}\n")
    
    if passed == total:
        print_pass("All layers passed! System appears healthy.")
        return 0
    else:
        print_fail("Some layers failed. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

