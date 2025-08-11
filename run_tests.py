#!/usr/bin/env python3
"""
Test runner for SmarterVote tests that can run without external API calls.

This script runs all the tests that don't require external dependencies
and provides a summary of test coverage and results.
"""

import os
import sys
import time
import subprocess
from pathlib import Path


def print_banner(title):
    """Print a formatted banner."""
    print(f"\n{'=' * 60}")
    print(f"🧪 {title}")
    print('=' * 60)


def run_test_file(test_file):
    """Run a single test file and return success status."""
    print(f"\n🔍 Running: {test_file}")
    
    try:
        start_time = time.time()
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent
        )
        duration = time.time() - start_time
        
        if result.returncode == 0:
            print(f"✅ {test_file} PASSED ({duration:.2f}s)")
            return True, duration, result.stdout
        else:
            print(f"❌ {test_file} FAILED ({duration:.2f}s)")
            print(f"Error output:\n{result.stderr}")
            return False, duration, result.stderr
            
    except Exception as e:
        print(f"❌ {test_file} ERROR: {e}")
        return False, 0, str(e)


def main():
    """Run all available tests."""
    print_banner("SmarterVote Test Suite - No External API Dependencies")
    
    # List of test files that can run without external dependencies
    test_files = [
        "test_code_quality.py",
        "test_pipeline_logic.py", 
        "test_integration.py"
    ]
    
    results = []
    total_duration = 0
    
    print(f"📋 Running {len(test_files)} test files...")
    
    for test_file in test_files:
        if Path(test_file).exists():
            success, duration, output = run_test_file(test_file)
            results.append((test_file, success, duration, output))
            total_duration += duration
        else:
            print(f"⚠️  {test_file} not found, skipping...")
            results.append((test_file, False, 0, "File not found"))
    
    # Summary
    print_banner("Test Results Summary")
    
    passed_tests = [r for r in results if r[1]]
    failed_tests = [r for r in results if not r[1]]
    
    print(f"📊 Test Results:")
    print(f"   ✅ Passed: {len(passed_tests)}/{len(results)}")
    print(f"   ❌ Failed: {len(failed_tests)}/{len(results)}")
    print(f"   ⏱️  Total Duration: {total_duration:.2f}s")
    
    if passed_tests:
        print(f"\n✅ Passing Tests:")
        for test_file, _, duration, _ in passed_tests:
            print(f"   • {test_file} ({duration:.2f}s)")
    
    if failed_tests:
        print(f"\n❌ Failed Tests:")
        for test_file, _, duration, output in failed_tests:
            print(f"   • {test_file} ({duration:.2f}s)")
    
    # Test coverage analysis
    print_banner("Test Coverage Analysis")
    
    # Count Python files in key directories
    key_dirs = ["pipeline/app", "services", "shared"]
    total_py_files = 0
    
    for directory in key_dirs:
        if Path(directory).exists():
            py_files = list(Path(directory).rglob("*.py"))
            py_files = [f for f in py_files if not f.name.startswith("test_")]
            total_py_files += len(py_files)
            print(f"📁 {directory}: {len(py_files)} Python files")
    
    print(f"\n📈 Coverage Overview:")
    print(f"   📁 Total Python files: {total_py_files}")
    print(f"   🧪 Test files: {len([r for r in results if r[1]])}")
    print(f"   📊 Test coverage focus: Core business logic and integration")
    
    print(f"\n🎯 Test Strategy:")
    print(f"   • Code quality checks: Syntax, imports, async patterns")
    print(f"   • Business logic tests: Environment detection, query generation")
    print(f"   • Integration tests: Publishing, API fallbacks, data handling")
    print(f"   • No external dependencies: No AI APIs, no ChromaDB, no external services")
    
    # Overall status
    success_rate = len(passed_tests) / len(results) * 100 if results else 0
    
    print_banner("Final Status")
    
    if success_rate >= 100:
        print("🎉 ALL TESTS PASSED!")
        print("✅ Test suite is working correctly without external dependencies")
        return 0
    elif success_rate >= 75:
        print("⚠️  MOSTLY PASSING")
        print("🔧 Some tests need attention but core functionality works")
        return 1
    else:
        print("❌ TESTS NEED ATTENTION")
        print("🔧 Multiple test failures detected")
        return 2


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)