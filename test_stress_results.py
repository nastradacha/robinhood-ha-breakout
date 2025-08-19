#!/usr/bin/env python3
"""
Quick test script to check stress test results
"""

from utils.stress_testing import StressTestFramework

def main():
    framework = StressTestFramework()
    results = framework.run_all_tests()
    
    print("Detailed stress test results:")
    for r in framework.results:
        status = "PASS" if r.passed else f"FAIL - {r.error_message}"
        print(f"{r.test_name}: {status}")

if __name__ == "__main__":
    main()
