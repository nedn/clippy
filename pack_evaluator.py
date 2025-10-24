"""
Evaluator for the pack.py speed optimization example.

This evaluator runs the candidate program on a benchmark directory and
compares its stdout to a golden file.

Metrics:
- correctness_score: 1.0 if diff is empty, 0.0 otherwise.
- execution_time: Wall clock time for the script to run.
- speed_score: 1.0 / (1.0 + execution_time).
- combined_score: correctness_score * speed_score.
"""

import subprocess
import time
import os
import tempfile
import traceback
from pathlib import Path
from openevolve.evaluation_result import EvaluationResult

# --- Constants ---
BENCHMARK_DIR = os.path.join(os.path.dirname(__file__), 'benchmark_data')
FOLDER_TO_PACK = os.path.join(BENCHMARK_DIR, "openevolve")
GOLDEN_FILE = os.path.join(BENCHMARK_DIR,
                           "golden_openevolve_pack.txt")

# Max time allowed for the pack.py script itself to run
EVALUATION_TIMEOUT = 60 # 60 seconds

def _create_error_result(e, stage="main", stderr=None, diff=None):
    """Helper function to create a standardized EvaluationResult for errors."""
    error_type = type(e).__name__
    error_message = str(e)

    if stderr is None and hasattr(e, 'stderr'):
        stderr = e.stderr
    if diff is None and hasattr(e, 'stdout'): # diff might be in stdout
        diff = e.stdout

    return EvaluationResult(
        metrics={
            "correctness_score": 0.0,
            "speed_score": 0.0,
            "execution_time": float(EVALUATION_TIMEOUT),
            "combined_score": 0.0,
            "error": error_type,
        },
        artifacts={
            "status": "Error",
            "error_type": error_type,
            "error_message": error_message,
            "full_traceback": traceback.format_exc(),
            "stderr": stderr[:1000] if stderr else "N/A",
            "diff": diff[:1000] if diff else "N/A",
        }
    )

def _run_evaluation(program_path):
    """
    Core logic to run and evaluate a single program.
    """
    folder_to_pack = Path(FOLDER_TO_PACK)
    golden_path = Path(GOLDEN_FILE)

    # --- 1. Pre-run checks ---
    if not folder_to_pack.is_dir():
        return _create_error_result(FileNotFoundError(f"Benchmark directory not found: {FOLDER_TO_PACK}"))
    if not golden_path.is_file():
        return _create_error_result(FileNotFoundError(f"Golden file not found: {GOLDEN_FILE}"))

    # Create a temporary file to store the script's output for diffing
    # We use a named file path that we can pass to `diff`
    with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as temp_out:
        output_path = temp_out.name

    try:
        # --- 2. Run the candidate program ---
        # The pack.py script writes to stdout when not in a TTY,
        # so we capture stdout.
        cmd = ["python3", program_path, str(folder_to_pack)]

        start_time = time.monotonic()

        proc = subprocess.run(
            cmd,
            capture_output=True, # Capture stdout and stderr
            text=True,
            timeout=EVALUATION_TIMEOUT,
            encoding='utf-8',
            errors='ignore' # Avoid decode errors from potential garbage in stderr
        )

        end_time = time.monotonic()
        execution_time = end_time - start_time

        # Check for runtime crash
        if proc.returncode != 0:
            return _create_error_result(
                Exception(f"Script crashed with return code {proc.returncode}"),
                stderr=proc.stderr
            )

        # Write the captured stdout to our temp file for diffing
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(proc.stdout)

        # --- 3. Run diff for correctness check ---
        diff_cmd = ["diff", "-u", str(golden_path), output_path]

        diff_proc = subprocess.run(
            diff_cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )

        diff_output = diff_proc.stdout

        # Correctness is binary: 1.0 if files are identical (no diff), 0.0 otherwise
        correctness_score = 1.0 if not diff_output else 0.0

        # --- 4. Calculate scores ---

        # Speed score: 1.0 / (1.0 + time).
        # This creates a score between 0 and 1, where faster is higher.
        speed_score = 1.0 / (1.0 + execution_time)

        # Combined score: Must be 100% correct.
        # If correctness is 0, the whole score is 0.
        combined_score = correctness_score * speed_score

        return EvaluationResult(
            metrics={
                "correctness_score": correctness_score,
                "speed_score": speed_score,
                "execution_time": execution_time,
                "combined_score": combined_score,
            },
            artifacts={
                "status": "Success" if correctness_score == 1.0 else "DiffMismatch",
                "execution_time_s": f"{execution_time:.4f}",
                # Include stderr for debugging (e.g., "Processed X files...")
                "stderr": proc.stderr[:1000],
                # Include the first 2000 chars of the diff, if any
                "diff": diff_output[:2000]
            }
        )

    except subprocess.TimeoutExpired as e:
        return _create_error_result(e, stderr="Process timed out.")
    except Exception as e:
        return _create_error_result(e)
    finally:
        # Clean up the temp file
        if os.path.exists(output_path):
            os.remove(output_path)



# --- Public API Functions ---

def evaluate(program_path):
    """
    Full evaluation entry point.
    For this problem, it's identical to the staged evaluations.
    """
    return _run_evaluation(program_path)

def evaluate_stage1(program_path):
    """
    First stage evaluation.
    """
    return _run_evaluation(program_path)

def evaluate_stage2(program_path):
    """
    Second stage evaluation.
    """
    return _run_evaluation(program_path)


if __name__ == "__main__":
  print(_run_evaluation('pack.py'))
