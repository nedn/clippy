# Comprehensive Test Plan for `pack` Script


#### **1. Introduction and Objective**

The objective of this test plan is to verify the correctness, reliability, and performance of the `pack` script. The plan focuses on ensuring that all features—including file discovery, filtering, parallel processing, and output generation—function as expected under a variety of conditions.

This plan outlines two distinct test scripts:
*   `test_pack.py`: A comprehensive functional test suite using Python's built-in `unittest` framework. It will contain unit, integration, and end-to-end functional tests.
*   `test_pack_perf.py`: A dedicated performance testing script to measure and analyze the script's execution time and scalability, particularly the benefits of parallel processing.

All tests will be implemented using Python's standard `unittest`, `tempfile`, `subprocess`, and `time` libraries.

#### **2. Testing Scope**

**In-Scope:**
*   Unit testing of individual helper functions (`parse_size`, `is_likely_non_text`, etc.).
*   Integration testing of the file collection and filtering logic.
*   End-to-end functional testing of the command-line interface and its arguments.
*   Verification of output to both standard output (stdout) and files.
*   Error handling for invalid inputs and file system issues.
*   End-to-end performance benchmarking of parallel file reading.

**Out-of-Scope:**
*   Testing the `tiktoken` library's tokenization algorithm. We will mock its presence or absence.
*   Exhaustive testing across different operating systems (tests will be designed to be OS-agnostic).
*   Testing in environments with complex file permission schemes beyond basic read errors.

#### **3. Test Environment and Setup**

All tests will be self-contained and will not modify the user's actual file system. The `tempfile` module will be used to create a temporary directory structure for each test or test suite. This structure will be automatically cleaned up after the tests are completed.

A typical test setup will involve creating a temporary directory with a structure like this:
```
/tmp/test_pack_xyz/
├── project/
│   ├── src/
│   │   ├── main.py
│   │   ├── utils.py
│   │   └── data.json
│   ├── tests/
│   │   ├── test_main.py
│   │   └── test_utils.py
│   ├── .git/
│   │   └── config
│   ├── README.md
│   ├── large_log_file.log  (> 5MB)
│   ├── image.png           (binary file)
│   └── empty_file.txt
└── another_file.txt
```

---

### **4. Functional Test Script: `test_pack.py`**

This script will contain all functional tests, organized by category into distinct `unittest.TestCase` classes. This modular structure allows for clarity and selective test execution.

#### **4.1. Test Script Structure and Execution**

The `test_pack.py` file will be structured with multiple classes inheriting from `unittest.TestCase`.

```python
# test_pack.py
import unittest
import argparse
import sys
# ... other imports for tempfile, subprocess, etc.

class TestUnitFunctions(unittest.TestCase):
    # All unit tests for helper functions will go here.
    def test_parse_size(self): ...
    def test_is_likely_non_text(self): ...
    def test_should_ignore(self): ...

class TestIntegration(unittest.TestCase):
    # Tests for the interaction of different components.
    def test_collect_results_default(self): ...
    def test_collect_results_with_patterns(self): ...

class TestE2EFunctional(unittest.TestCase):
    # End-to-end tests using the subprocess module.
    def setUp(self):
        # Create temporary directory and files before each E2E test.
        ...
    def tearDown(self):
        # Clean up the temporary directory.
        ...
    def test_basic_operation_to_file(self): ...
    def test_piped_output_to_stdout(self): ...
    def test_argument_handling_include(self): ...
    # ... other E2E tests

if __name__ == '__main__':
    # Add a command-line flag to select test classes.
    parser = argparse.ArgumentParser(description="Run tests for the pack script.")
    parser.add_argument(
        '--level',
        choices=['unit', 'integration', 'e2e', 'all'],
        default='all',
        help='Select which class of tests to run.'
    )
    args, remaining_argv = parser.parse_known_args()

    # Create a TestSuite
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()

    if args.level in ['unit', 'all']:
        suite.addTests(loader.loadTestsFromTestCase(TestUnitFunctions))
    if args.level in ['integration', 'all']:
        suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    if args.level in ['e2e', 'all']:
        suite.addTests(loader.loadTestsFromTestCase(TestE2EFunctional))

    # Run the tests
    runner = unittest.TextTestRunner()
    # Pass the remaining arguments (like -v for verbose) to the runner
    sys.argv = [sys.argv[0]] + remaining_argv
    runner.run(suite)
```
**Execution Examples:**
*   Run all tests: `python test_pack.py`
*   Run only unit tests: `python test_pack.py --level unit`
*   Run only E2E tests with verbose output: `python test_pack.py --level e2e -v`

#### **4.2. Class: `TestUnitFunctions`**

*   **`test_parse_size()`**
    *   **Test Case 1:** Valid inputs with various units (e.g., `'1024'`, `'1.5M'`, `'2G'`).
    *   **Test Case 2:** Case-insensitivity (e.g., `'5mb'`, `'10K'`).
    *   **Test Case 3:** Inputs with no units (defaults to bytes).
    *   **Test Case 4:** Invalid inputs (e.g., `'abc'`, `'10X'`) to ensure `ValueError` is raised.
*   **`test_is_likely_non_text()`**
    *   **Test Case 1:** Files with known binary extensions (e.g., `.png`, `.zip`).
    *   **Test Case 2:** Text file containing null bytes (`\0`).
    *   **Test Case 3:** Standard text file.
    *   **Test Case 4:** Empty file.
    *   **Test Case 5:** Mock `PermissionError` to ensure graceful handling.
*   **`test_should_ignore()`**
    *   **Test Case 1:** File larger than `max_file_size_bytes`.
    *   **Test Case 2:** Hidden file (e.g., `.env`).
    *   **Test Case 3:** File within a hidden directory (e.g., `.git/config`).
    *   **Test Case 4:** `include_pattern` (e.g., `'*.py'`).
    *   **Test Case 5:** `exclude_pattern` (e.g., `'*_test.py'`).
    *   **Test Case 6:** Likely binary file.

#### **4.3. Class: `TestIntegration`**
*   **`test_collect_results()`**
    *   **Test Case 1:** Call `collect_results` with default arguments on a test directory. Assert that the correct files and content are returned in sorted order.
    *   **Test Case 2:** Provide a mix of a file and a directory as input. Verify both are processed correctly and duplicates are handled.
    *   **Test Case 3:** Use complex include and exclude patterns to test filtering logic in an integrated scenario.

#### **4.4. Class: `TestE2EFunctional`**
These tests will use `subprocess.run` to execute `pack.py` as a command-line tool.

*   **Basic Operation**
    *   **Test Case 1 (Default behavior):** Run `python pack.py` in a test directory. Verify `output.txt` is created and has the correct concatenated content.
    *   **Test Case 2 (Piped output):** Run `python pack.py | cat`. Verify output is written to `stdout` and `output.txt` is not created.
*   **Argument Handling**
    *   **Test Case 3 (`--include`):** Run `python pack.py -i "*.py"`. Verify output contains only `.py` file content.
    *   **Test Case 4 (`--exclude`):** Run `python pack.py -e "tests/*"`. Verify output excludes files from the `tests` directory.
    *   **Test Case 5 (`--max-file-size`):** Run `python pack.py --max-file-size 1K`. Verify files larger than 1KB are excluded.
    *   **Test Case 6 (`--paths-only`):** Run `python pack.py --paths-only`. Verify output is a list of file paths only.
    *   **Test Case 7 (`--output-tokens-size-only`):** Run `python pack.py --output-tokens-size-only`. Verify output contains paths, token counts, and byte counts.

---

### **5. Performance Test Script: `test_pack_perf.py`**

This script will be a standalone executable responsible for benchmarking the `pack` script's performance under controlled conditions. It will not use the `unittest` framework.

#### **5.1. Objective and Methodology**

The primary goal is to measure execution time and validate the scalability improvements from parallel processing. The script will:
1.  Programmatically create a large, temporary directory with a configurable number of files and subdirectories.
2.  Use `subprocess.run` to execute the `pack.py` script against this directory with different arguments (e.g., varying worker counts).
3.  Use `time.perf_counter()` to precisely measure the execution time of each run.
4.  Print a clear, comparative report to the console.

#### **5.2. Script Structure**
```python
# test_pack_perf.py
import time
import subprocess
import tempfile
import os
from pathlib import Path

def setup_performance_test_directory(base_dir, num_files, file_size_kb):
    # Creates a directory structure with many files for testing.
    ...

def run_benchmark(description, command_args):
    # Runs the pack script with given args and measures time.
    print(f"--- Running: {description} ---")
    start_time = time.perf_counter()
    subprocess.run(
        ['python', 'pack.py'] + command_args,
        check=True,
        capture_output=True # Suppress output during benchmark
    )
    end_time = time.perf_counter()
    duration = end_time - start_time
    print(f"Execution Time: {duration:.4f} seconds\n")
    return duration

def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Scenario 1: I/O Bound - Many small files
        print("="*20 + " SCENARIO: 1000 small files (1KB each) " + "="*20)
        setup_performance_test_directory(tmpdir, num_files=1000, file_size_kb=1)

        run_benchmark("Baseline (1 worker)", [tmpdir, '--workers', '1'])
        run_benchmark("Parallel (2 workers)", [tmpdir, '--workers', '2'])
        run_benchmark("Parallel (4 workers)", [tmpdir, '--workers', '4'])

        # Scenario 2: Larger files
        # ... more scenarios ...

if __name__ == "__main__":
    main()
```

#### **5.3. Performance Test Cases**

*   **Test Case 1 (I/O Bound Scalability):**
    *   **Action:** Create a directory with a large number of small text files (e.g., 1,000 files of 4KB each).
    *   **Measurement:** Measure execution time with `--workers 1`, `--workers 2`, `--workers 4`, and `--workers <max_cpu_cores>`.
    *   **Expected Outcome:** Execution time should decrease significantly as the number of workers increases (up to the number of available CPU cores), demonstrating effective parallelization for I/O-bound tasks.
*   **Test Case 2 (Fewer, Larger Files):**
    *   **Action:** Create a directory with a moderate number of larger text files (e.g., 50 files of 1MB each).
    *   **Measurement:** Measure execution time with `--workers 1` vs. `--workers <max_cpu_cores>`.
    *   **Expected Outcome:** A noticeable, though potentially smaller, performance improvement should be observed, as reading larger files can also benefit from parallelism.