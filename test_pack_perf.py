# test_pack_perf.py
import time
import subprocess
import tempfile
import os
from pathlib import Path
import sys

def setup_performance_test_directory(base_dir, num_files, file_size_kb):
    """Creates a directory structure with many files for testing."""
    print(f"Setting up test directory with {num_files} files of {file_size_kb}KB each...")
    base_path = Path(base_dir)
    content = "a" * (file_size_kb * 1024)
    
    for i in range(num_files):
        # Distribute files into subdirectories to avoid having too many files in one dir
        subdir = base_path / f"subdir_{i % 10}"
        subdir.mkdir(exist_ok=True)
        (subdir / f"file_{i}.txt").write_text(content)
    print("Setup complete.")

def run_benchmark(description, command_args):
    """Runs the pack script with given args and measures time."""
    pack_script_path = Path(__file__).parent / "pack.py"
    command = [sys.executable, str(pack_script_path)] + command_args
    
    print(f"--- Running: {description} ---")
    start_time = time.perf_counter()
    
    result = subprocess.run(
        command,
        check=False, # Don't raise exception on non-zero exit
        capture_output=True # Suppress output during benchmark
    )
    
    end_time = time.perf_counter()
    
    if result.returncode != 0:
        print(f"Error running pack script for '{description}'")
        print(f"Stderr: {result.stderr.decode('utf-8', 'ignore')}")
        return float('inf') # Return a large number to indicate failure

    duration = end_time - start_time
    print(f"Execution Time: {duration:.4f} seconds\n")
    return duration

def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Scenario 1: I/O Bound - Many small files
        print("="*20 + " SCENARIO: 1000 small files (4KB each) " + "="*20)
        scenario1_dir = tmp_path / "scenario1"
        scenario1_dir.mkdir()
        setup_performance_test_directory(scenario1_dir, num_files=1000, file_size_kb=4)

        run_benchmark("Baseline (1 worker)", [str(scenario1_dir), '--workers', '1'])
        run_benchmark("Parallel (2 workers)", [str(scenario1_dir), '--workers', '2'])
        run_benchmark("Parallel (4 workers)", [str(scenario1_dir), '--workers', '4'])
        if os.cpu_count() and os.cpu_count() > 4:
            run_benchmark(f"Parallel ({os.cpu_count()} workers)", [str(scenario1_dir), '--workers', str(os.cpu_count())])
        
        print("\n" + "="*60 + "\n")

        # Scenario 2: Fewer, Larger Files
        print("="*20 + " SCENARIO: 50 larger files (1MB each) " + "="*20)
        scenario2_dir = tmp_path / "scenario2"
        scenario2_dir.mkdir()
        setup_performance_test_directory(scenario2_dir, num_files=50, file_size_kb=1024)

        run_benchmark("Baseline (1 worker)", [str(scenario2_dir), '--workers', '1'])
        run_benchmark("Parallel (2 workers)", [str(scenario2_dir), '--workers', '2'])
        run_benchmark("Parallel (4 workers)", [str(scenario2_dir), '--workers', '4'])
        if os.cpu_count() and os.cpu_count() > 4:
            run_benchmark(f"Parallel ({os.cpu_count()} workers)", [str(scenario2_dir), '--workers', str(os.cpu_count())])


if __name__ == "__main__":
    main()
