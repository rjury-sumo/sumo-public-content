#!/usr/bin/env python3
"""
Integration tests for get_estimated_usage.py

Tests all major functionality using real API calls with environment variables.
Run with: python3 test_integration.py
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def print_test(msg):
    print(f"\n{YELLOW}TEST:{RESET} {msg}")

def print_pass(msg):
    print(f"{GREEN}✓ PASS:{RESET} {msg}")

def print_fail(msg):
    print(f"{RED}✗ FAIL:{RESET} {msg}")

def run_command(cmd, check_success=True):
    """Run a command and return output"""
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if check_success and result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
        return None

    return result

def test_env_vars():
    """Test that required environment variables are set"""
    print_test("Checking environment variables")

    required_vars = ['SUMO_ACCESS_ID', 'SUMO_ACCESS_KEY', 'SUMO_ENDPOINT']
    missing = []

    for var in required_vars:
        if not os.environ.get(var):
            missing.append(var)

    if missing:
        print_fail(f"Missing environment variables: {', '.join(missing)}")
        print("  Please set: SUMO_ACCESS_ID, SUMO_ACCESS_KEY, SUMO_ENDPOINT")
        return False

    print_pass("All required environment variables are set")
    return True

def test_single_query_summary():
    """Test single query with summary output"""
    print_test("Single query with summary output")

    cmd = [
        'python3', 'get_estimated_usage.py',
        '--query=_index=sumologic_audit',
        '--from-time=-1h',
        '--to-time=now',
        '--output=summary'
    ]

    result = run_command(cmd)
    if result is None:
        print_fail("Command failed")
        return False

    if 'Estimated data to scan:' in result.stdout:
        print_pass("Summary output generated successfully")
        print(f"  Output: {result.stdout.strip()}")
        return True
    else:
        print_fail("Expected output not found")
        print(f"  Output: {result.stdout}")
        return False

def test_single_query_json():
    """Test single query with JSON output"""
    print_test("Single query with JSON output")

    cmd = [
        'python3', 'get_estimated_usage.py',
        '--query=_index=sumologic_audit',
        '--from-time=-1h',
        '--to-time=now',
        '--output=json'
    ]

    result = run_command(cmd)
    if result is None:
        print_fail("Command failed")
        return False

    try:
        data = json.loads(result.stdout)
        if 'estimatedUsageDetails' in data:
            print_pass("JSON output generated successfully")
            return True
        else:
            print_fail("Expected JSON structure not found")
            return False
    except json.JSONDecodeError as e:
        print_fail(f"Invalid JSON output: {e}")
        return False

def test_single_query_table():
    """Test single query with table output"""
    print_test("Single query with table output")

    cmd = [
        'python3', 'get_estimated_usage.py',
        '--query=_index=sumologic_audit',
        '--from-time=-1h',
        '--to-time=now',
        '--output=table'
    ]

    result = run_command(cmd)
    if result is None:
        print_fail("Command failed")
        return False

    if '=== Estimated Usage ===' in result.stdout:
        print_pass("Table output generated successfully")
        return True
    else:
        print_fail("Expected table format not found")
        return False

def test_by_view_endpoint():
    """Test by-view endpoint with breakdown"""
    print_test("By-view endpoint with partition breakdown")

    cmd = [
        'python3', 'get_estimated_usage.py',
        '--query=_index=sumologic_audit',
        '--from-time=-1h',
        '--to-time=now',
        '--by-view',
        '--output=summary'
    ]

    result = run_command(cmd)
    if result is None:
        print_fail("Command failed")
        return False

    if 'Breakdown by view/partition:' in result.stdout or 'Estimated data to scan:' in result.stdout:
        print_pass("By-view endpoint works correctly")
        print(f"  Output:\n{result.stdout}")
        return True
    else:
        print_fail("Expected breakdown output not found")
        return False

def test_batch_mode_summary():
    """Test batch mode with summary output"""
    print_test("Batch mode with summary output")

    # Create a temporary YAML file
    yaml_content = """queries:
  - name: "Test Query 1"
    query: "_index=sumologic_audit"
    from: "-1h"
    to: "now"
    timezone: "UTC"
    byView: true

  - name: "Test Query 2"
    query: "_sourceCategory=*"
    from: "-1h"
    to: "now"
    timezone: "UTC"
    byView: false
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        yaml_file = f.name

    try:
        cmd = [
            'python3', 'get_estimated_usage.py',
            f'--batch-file={yaml_file}',
            '--output=summary'
        ]

        result = run_command(cmd)
        if result is None:
            print_fail("Command failed")
            return False

        if '=== Batch Estimated Usage Report ===' in result.stdout and 'Total queries: 2' in result.stdout:
            print_pass("Batch mode summary output works")
            print(f"  Output:\n{result.stdout}")
            return True
        else:
            print_fail("Expected batch summary not found")
            print(f"  Output: {result.stdout}")
            print(f"  Stderr: {result.stderr}")
            return False
    finally:
        os.unlink(yaml_file)

def test_batch_mode_json():
    """Test batch mode with JSON output"""
    print_test("Batch mode with JSON output")

    yaml_content = """queries:
  - name: "JSON Test"
    query: "_index=sumologic_audit"
    from: "-1h"
    to: "now"
    timezone: "UTC"
    byView: false
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        yaml_file = f.name

    try:
        cmd = [
            'python3', 'get_estimated_usage.py',
            f'--batch-file={yaml_file}',
            '--output=json'
        ]

        result = run_command(cmd)
        if result is None:
            print_fail("Command failed")
            return False

        try:
            data = json.loads(result.stdout)
            if isinstance(data, list) and len(data) > 0:
                print_pass("Batch JSON output generated successfully")
                return True
            else:
                print_fail("Expected JSON array not found")
                return False
        except json.JSONDecodeError as e:
            print_fail(f"Invalid JSON output: {e}")
            return False
    finally:
        os.unlink(yaml_file)

def test_batch_mode_webview():
    """Test batch mode with webview HTML output"""
    print_test("Batch mode with webview HTML output")

    yaml_content = """queries:
  - name: "Webview Test"
    query: "_index=sumologic_audit"
    from: "-1h"
    to: "now"
    timezone: "UTC"
    byView: true
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as yaml_f:
        yaml_f.write(yaml_content)
        yaml_file = yaml_f.name

    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as html_f:
        html_file = html_f.name

    try:
        cmd = [
            'python3', 'get_estimated_usage.py',
            f'--batch-file={yaml_file}',
            '--output=webview',
            f'--output-file={html_file}'
        ]

        result = run_command(cmd)
        if result is None:
            print_fail("Command failed")
            return False

        # Check if HTML file was created
        if os.path.exists(html_file):
            with open(html_file, 'r') as f:
                html_content = f.read()

            if '<!DOCTYPE html>' in html_content and 'Sumo Logic Estimated Usage Report' in html_content:
                print_pass("Webview HTML report generated successfully")
                print(f"  HTML file created: {html_file}")
                print(f"  File size: {len(html_content)} bytes")
                return True
            else:
                print_fail("HTML content incomplete")
                return False
        else:
            print_fail("HTML file not created")
            return False
    finally:
        os.unlink(yaml_file)
        if os.path.exists(html_file):
            os.unlink(html_file)

def test_time_formats():
    """Test various time format inputs"""
    print_test("Various time format inputs")

    test_cases = [
        ('Relative time', '-2h', 'now'),
        ('Relative days', '-1d', 'now'),
    ]

    passed = 0
    for name, from_time, to_time in test_cases:
        cmd = [
            'python3', 'get_estimated_usage.py',
            '--query=_index=sumologic_audit',
            f'--from-time={from_time}',
            f'--to-time={to_time}',
            '--output=summary'
        ]

        result = run_command(cmd, check_success=False)
        if result and result.returncode == 0:
            print(f"  ✓ {name}: {from_time} to {to_time}")
            passed += 1
        else:
            print(f"  ✗ {name}: {from_time} to {to_time}")

    if passed == len(test_cases):
        print_pass(f"All {passed} time format tests passed")
        return True
    else:
        print_fail(f"Only {passed}/{len(test_cases)} time format tests passed")
        return False

def test_error_handling():
    """Test error handling for invalid inputs"""
    print_test("Error handling for invalid inputs")

    # Test missing required args
    cmd = [
        'python3', 'get_estimated_usage.py',
        '--query=_index=sumologic_audit',
        '--from-time=-1h'
        # Missing --to-time
    ]

    result = run_command(cmd, check_success=False)
    if result and result.returncode != 0:
        print_pass("Correctly rejects missing required arguments")
        return True
    else:
        print_fail("Should have failed with missing arguments")
        return False

def main():
    """Run all integration tests"""
    print("=" * 60)
    print("SUMO LOGIC ESTIMATED USAGE - INTEGRATION TESTS")
    print("=" * 60)

    # Check environment
    if not test_env_vars():
        print("\n" + "=" * 60)
        print(f"{RED}ABORTED: Environment variables not set{RESET}")
        print("=" * 60)
        sys.exit(1)

    # Run all tests
    tests = [
        ("Single Query - Summary", test_single_query_summary),
        ("Single Query - JSON", test_single_query_json),
        ("Single Query - Table", test_single_query_table),
        ("By-View Endpoint", test_by_view_endpoint),
        ("Batch Mode - Summary", test_batch_mode_summary),
        ("Batch Mode - JSON", test_batch_mode_json),
        ("Batch Mode - Webview", test_batch_mode_webview),
        ("Time Formats", test_time_formats),
        ("Error Handling", test_error_handling),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_fail(f"Test crashed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = f"{GREEN}✓ PASS{RESET}" if result else f"{RED}✗ FAIL{RESET}"
        print(f"{status}: {name}")

    print("=" * 60)
    if passed == total:
        print(f"{GREEN}ALL TESTS PASSED ({passed}/{total}){RESET}")
        sys.exit(0)
    else:
        print(f"{YELLOW}SOME TESTS FAILED ({passed}/{total} passed){RESET}")
        sys.exit(1)

if __name__ == '__main__':
    main()
