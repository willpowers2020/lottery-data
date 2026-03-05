#!/usr/bin/env python3
"""
Legacy Test Runner
==================
Runs all existing test scripts as subprocesses and reports results.
Requires Flask server running at http://localhost:5001.

Usage:
    python tests/run_all.py
"""

import subprocess
import sys
import time
import requests

BASE_URL = "http://localhost:5001"

# Tests that need stdin piped (they use input())
INTERACTIVE_TESTS = {
    "test_cluster_year.py",
    "test_focus_profile.py",
    "test_mld_duplicates.py",
    "test_truth_table.py",
    "test_tt_2019.py",
    "test_tt_broad.py",
    "test_intersection.py",
    "test_cy_vs_monthly.py",
    "test_cluster_year_deep.py",
}

# Tests that don't need stdin
DIRECT_TESTS = [
    "test_true_rbtl_v2.py",
    "test_true_rbtl.py",
    "crossfire_test.py",
    "test_pick5_feb25.py",
    "test_pick5_all_states.py",
    "test_rebuild_safe.py",
]

# Tests requiring special args
SPECIAL_ARGS = {
    "crossfire_test.py": ["--date", "2019-10-09", "--tod", "midday"],
}

# Skip these (archived old versions)
SKIP = {
    "test_true_rbtl_v2_old0212261132.py",
    "test_true_rbtl_v2_old0212261150.py",
    "test_true_rbtl_v2_old0212261201.py",
    "test_true_rbtl_v2_old0212261208.py",
}

STDIN_DEFAULTS = "http://localhost:5001\nmongo_v2\n"


def check_server():
    """Verify Flask server is running."""
    try:
        r = requests.get(f"{BASE_URL}/api/db-status?db=mongo_v2", timeout=5)
        r.raise_for_status()
        data = r.json()
        print(f"  Server OK: {data['records']:,} records, mode={data['mode']}")
        return True
    except Exception as e:
        print(f"  Server NOT reachable at {BASE_URL}: {e}")
        return False


def run_test(test_file, timeout=180):
    """Run a single test file and return (passed, output)."""
    cmd = [sys.executable, f"tests/{test_file}"]
    if test_file in SPECIAL_ARGS:
        cmd.extend(SPECIAL_ARGS[test_file])

    stdin_data = STDIN_DEFAULTS if test_file in INTERACTIVE_TESTS else None

    try:
        result = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**__import__("os").environ, "PYTHONPATH": "src"},
        )
        output = result.stdout + result.stderr
        # Check for errors
        has_error = (
            result.returncode != 0
            or "Traceback" in output
            or "EXCEPTION" in output
            or "ERROR" in output.upper().split("ERROR")[0][-20:] if "ERROR" in output.upper() else False
        )
        return not has_error, output, result.returncode
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {timeout}s", -1
    except Exception as e:
        return False, str(e), -1


def main():
    print("=" * 60)
    print("  Legacy Test Runner")
    print("=" * 60)
    print()

    print("Checking server...")
    if not check_server():
        print("\nStart the server first: PYTHONPATH=src python3 app.py")
        sys.exit(1)
    print()

    all_tests = sorted(set(DIRECT_TESTS) | INTERACTIVE_TESTS - SKIP)
    results = []

    for i, test_file in enumerate(all_tests, 1):
        if test_file in SKIP:
            continue
        print(f"[{i}/{len(all_tests)}] {test_file}...", end=" ", flush=True)
        start = time.time()
        passed, output, code = run_test(test_file)
        elapsed = time.time() - start
        status = "PASS" if passed else "FAIL"
        print(f"{status} ({elapsed:.1f}s)")
        results.append((test_file, passed, elapsed, code))

    # Summary
    print()
    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)
    passed_count = sum(1 for _, p, _, _ in results if p)
    failed_count = len(results) - passed_count

    for test_file, passed, elapsed, code in results:
        icon = "PASS" if passed else "FAIL"
        print(f"  {icon}  {test_file} ({elapsed:.1f}s, exit={code})")

    print()
    print(f"  Total: {len(results)} | Passed: {passed_count} | Failed: {failed_count}")
    print("=" * 60)

    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    main()
