import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

class TestPackE2ESlow(unittest.TestCase):
    """
    End-to-end tests for the pack script. These tests are slow as they clone
    a repository from the internet.
    """
    repo_url = "https://github.com/SWE-bench/SWE-bench"
    commit_hash = "5cd4be9fb239716"
    temp_dir = None
    repo_path = None
    pack_script_path = None

    @classmethod
    def setUpClass(cls):
        """
        Set up the test environment by cloning the repository once for all tests.
        This is much more efficient than cloning for each test.
        """
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.repo_path = os.path.join(cls.temp_dir.name, 'SWE-bench')
        cls.pack_script_path = os.path.join(os.path.dirname(__file__), '..', 'pack.py')

        print(f"\nCloning {cls.repo_url} into {cls.repo_path}...")
        try:
            subprocess.run(
                ['git', 'clone', cls.repo_url, cls.repo_path],
                check=True, capture_output=True, text=True
            )
            print(f"Checking out commit {cls.commit_hash}...")
            subprocess.run(
                ['git', '-C', cls.repo_path, 'checkout', cls.commit_hash],
                check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as e:
            cls.tearDownClass()  # Ensure cleanup happens on failure
            raise RuntimeError(f"Failed to set up test repository:\n"
                               f"  Command: {' '.join(e.cmd)}\n"
                               f"  Stderr: {e.stderr}")
        except FileNotFoundError:
            cls.tearDownClass()
            raise RuntimeError("Git command not found. Please ensure git is installed and in your PATH.")

    @classmethod
    def tearDownClass(cls):
        """
        Clean up the temporary directory after all tests are done.
        """
        if cls.temp_dir:
            cls.temp_dir.cleanup()
            print("\nCleaned up temporary repository.")

    def _run_pack_and_assert_output(self, cli_args, golden_filename):
        """
        Helper method to run the pack script with given arguments and compare
        its output to a golden file.
        """
        golden_file_path = Path(__file__).parent / "golden_files" / golden_filename
        self.assertTrue(golden_file_path.exists(), f"Golden file not found: {golden_file_path}")

        command = [self.pack_script_path] + cli_args + [self.repo_path]

        try:
            print(f"Running command: {' '.join(command)}")
            result = subprocess.run(
                command,
                capture_output=True, text=True, check=True
            )
            actual_output = result.stdout
        except subprocess.CalledProcessError as e:
            self.fail(f"Pack script execution failed:\n"
                      f"  Command: {' '.join(e.cmd)}\n"
                      f"  Exit Code: {e.returncode}\n"
                      f"  Stdout: {e.stdout}\n"
                      f"  Stderr: {e.stderr}")

        with open(golden_file_path, 'r', encoding='utf-8') as f:
            expected_output = f.read()

        # Normalize line endings and strip whitespace for consistent comparison
        actual_lines = [line.strip() for line in actual_output.strip().splitlines()]
        expected_lines = [line.strip() for line in expected_output.strip().splitlines()]

        self.assertEqual(
            actual_lines,
            expected_lines,
            f"Output for '{' '.join(cli_args)}' does not match {golden_filename}."
        )

    def test_pack_token_size_output(self):
        """
        Tests the default behavior with the '-t' flag for token/size output.
        """
        self._run_pack_and_assert_output(
            cli_args=['-t'],
            golden_filename='swe-bench-5cd4be9fb239716_tokens.txt'
        )

    def test_pack_paths_only(self):
        """
        Tests the '--paths-only' flag to ensure only file paths are listed.
        """
        self._run_pack_and_assert_output(
            cli_args=['--paths-only'],
            golden_filename='swe-bench-5cd4be9fb239716_paths-only.txt'
        )

    def test_pack_include_python_files(self):
        """
        Tests the '--include' flag to pack only Python files.
        """
        self._run_pack_and_assert_output(
            cli_args=['-t', '--include', '*.py'],
            golden_filename='swe-bench-5cd4be9fb239716_include-py.txt'
        )

    def test_pack_exclude_yaml_files(self):
        """
        Tests the '--exclude' flag to exclude all YAML files.
        """
        self._run_pack_and_assert_output(
            cli_args=['-t', '--exclude', '*.yml'],
            golden_filename='swe-bench-5cd4be9fb239716_exclude-yml.txt'
        )
    
    def test_pack_max_file_size(self):
        """
        Tests the '--max-file-size' flag to exclude files larger than 10KB.
        """
        self._run_pack_and_assert_output(
            cli_args=['-t', '--max-file-size', '10K'],
            golden_filename='swe-bench-5cd4be9fb239716_max-10k.txt'
        )

if __name__ == '__main__':
    unittest.main()