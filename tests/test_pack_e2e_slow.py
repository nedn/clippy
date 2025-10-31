import os
import shutil
import subprocess
import tempfile
import unittest

class TestPackE2ESlow(unittest.TestCase):
    """
    End-to-end test for the pack script.
    This test is slow as it clones a repository from the internet.
    """

    def test_pack_swe_bench_repo(self):
        """
        Tests the pack script by cloning the SWE-bench repository, checking out a
        specific commit, running the pack script on it, and comparing the output
        to a pre-generated golden file.
        """
        repo_url = "https://github.com/SWE-bench/SWE-bench"
        commit_hash = "5cd4be9fb239716"
        
        # The pack script is assumed to be in the parent directory of this test script.
        pack_script_path = os.path.join(os.path.dirname(__file__), '..', 'pack')
        
        # The expected output file is in the same directory as this test script.
        expected_output_path = os.path.join(os.path.dirname(__file__), 'swe-bench-5cd4be9fb239716.txt')

        # Create a temporary directory to clone the repo into.
        # Using a context manager ensures the directory is cleaned up automatically.
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = os.path.join(temp_dir, 'SWE-bench')

            try:
                # 1. Clone the repository
                print(f"Cloning {repo_url} into {repo_path}...")
                subprocess.run(
                    ['git', 'clone', repo_url, repo_path],
                    check=True, capture_output=True, text=True
                )

                # 2. Checkout the specific commit
                print(f"Checking out commit {commit_hash}...")
                subprocess.run(
                    ['git', '-C', repo_path, 'checkout', commit_hash],
                    check=True, capture_output=True, text=True
                )

                # 3. Run the pack script on the cloned repository
                # The '-t' flag is used to get the token and size output.
                print(f"Running pack script on {repo_path}...")
                result = subprocess.run(
                    [pack_script_path, '-t', repo_path],
                    capture_output=True, text=True, check=True
                )
                actual_output = result.stdout

            except subprocess.CalledProcessError as e:
                self.fail(f"A command failed:\n"
                          f"  Command: {' '.join(e.cmd)}\n"
                          f"  Exit Code: {e.returncode}\n"
                          f"  Stdout: {e.stdout}\n"
                          f"  Stderr: {e.stderr}")
            except FileNotFoundError:
                self.fail("Git command not found. Please ensure git is installed and in your PATH.")

            # 4. Read the expected output from the golden file
            with open(expected_output_path, 'r', encoding='utf-8') as f:
                expected_output = f.read()

            # 5. Compare the actual output with the expected output
            # We normalize by splitting into lines and stripping whitespace to avoid
            # issues with line endings or trailing/leading whitespace differences.
            actual_lines = [line.strip() for line in actual_output.strip().splitlines()]
            expected_lines = [line.strip() for line in expected_output.strip().splitlines()]
            
            self.assertEqual(
                actual_lines,
                expected_lines,
                "The output of the pack script does not match the expected content."
            )

if __name__ == '__main__':
    unittest.main()