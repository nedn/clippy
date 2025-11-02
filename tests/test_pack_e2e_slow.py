import os
import shutil
import subprocess
import sys
import io
import tempfile
import unittest
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pack


class NonTTYStringIO(io.StringIO):
    """
    A StringIO wrapper that implements isatty() to return False.
    This ensures pack.main() treats stdout as non-TTY (piped) and writes to stdout.
    """
    def isatty(self):
        return False


class TestPackE2ESlow(unittest.TestCase):
    """
    End-to-end tests for the pack script. These tests are slow as they clone
    a repository from the internet.
    """
    repo_url = "https://github.com/SWE-bench/SWE-bench"
    commit_hash = "5cd4be9fb239716"
    temp_dir = None
    repo_path = None

    @classmethod
    def setUpClass(cls):
        """
        Set up the test environment by cloning the repository once for all tests.
        This is much more efficient than cloning for each test.
        """
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.repo_path = os.path.join(cls.temp_dir.name, 'SWE-bench')

        print(f"\nCloning {cls.repo_url} into {cls.repo_path}...")
        subprocess.run(
            ['git', 'clone', cls.repo_url, cls.repo_path],
            check=True, capture_output=True, text=True
        )
        print(f"Checking out commit {cls.commit_hash}...")
        subprocess.run(
            ['git', '-C', cls.repo_path, 'checkout', cls.commit_hash],
            check=True, capture_output=True, text=True
        )

    @classmethod
    def tearDownClass(cls):
        """
        Clean up the temporary directory after all tests are done.
        """
        if cls.temp_dir:
            cls.temp_dir.cleanup()
            print("\nCleaned up temporary repository.")

    def setUp(self):
        """
        Set up the test environment by creating a temporary output file.
        """
        self.test_output_file_path = str(os.path.join(self.temp_dir.name, "test_output.txt"))   
    
    def tearDown(self):
        """
        Clean up the temporary output file after each test.
        """
        Path(self.test_output_file_path).unlink(missing_ok=True)

    def _run_pack_and_assert_output(self, cli_args, golden_filename):
        """
        Helper method to run the pack script with given arguments and compare
        its output to a golden file.
        """
        golden_file_path = Path(__file__).parent / "golden_files" / golden_filename
        Path(self.test_output_file_path).unlink(missing_ok=True)

        # Build argv list: ['pack.py'] + cli_args + [repo_path]
        argv = ['pack.py'] + cli_args + ['-o', self.test_output_file_path] + [self.repo_path]
        print(f"Running pack.main with argv: {argv}")

        # Capture stdout by redirecting to StringIO
        # pack.main checks sys.stdout.isatty() - we need to make it non-TTY
        # so it writes to stdout instead of a file
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        try:
            sys.stdout = NonTTYStringIO()
            sys.stderr = NonTTYStringIO()
            pack.main(argv)
            stdout = sys.stdout.getvalue()
            stderr = sys.stderr.getvalue()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        with open(self.test_output_file_path, 'r', encoding='utf-8') as f:
            actual_output = f.read()

        with open(golden_file_path, 'r', encoding='utf-8') as f:
            expected_output = f.read()
        # Normalize line endings and strip whitespace for consistent comparison
        actual_lines = [line.strip() for line in actual_output.strip().splitlines()]
        expected_lines = [line.strip() for line in expected_output.strip().splitlines()]

        self.assertEqual(
            actual_lines,
            expected_lines,
            f"Output for '{' '.join(cli_args)}' does not match {golden_filename}.\n"
            f"stdout: {stdout}\n"
            f"stderr: {stderr}"
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
