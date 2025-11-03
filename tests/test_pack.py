# test_pack.py
import unittest
import argparse
import sys
import os
import tempfile
import subprocess
from pathlib import Path
import shutil

# Add the parent directory to the path so we can import pack
sys.path.insert(0, os.path.join(
    os.path.abspath(os.path.dirname(__file__)), ".."))

import pack

class TestUnitFunctions(unittest.TestCase):
    # All unit tests for helper functions will go here.
    def test_parse_size(self):
        self.assertEqual(pack.parse_size('1024'), 1024)
        self.assertEqual(pack.parse_size('1.5M'), int(1.5 * 1024**2))
        self.assertEqual(pack.parse_size('2G'), 2 * 1024**3)
        self.assertEqual(pack.parse_size('5mb'), 5 * 1024**2)
        self.assertEqual(pack.parse_size('10K'), 10 * 1024)
        self.assertEqual(pack.parse_size('10'), 10)
        with self.assertRaises(ValueError):
            pack.parse_size('abc')
        with self.assertRaises(ValueError):
            pack.parse_size('10X')

    def test_is_likely_non_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            
            # Test case 1: Files with known binary extensions
            bin_ext_file = p / "test.png"
            bin_ext_file.touch()
            self.assertTrue(pack.is_likely_non_text(bin_ext_file))

            # Test case 2: Text file containing null bytes
            null_byte_file = p / "null.txt"
            with open(null_byte_file, 'wb') as f:
                f.write(b'hello\0world')
            self.assertTrue(pack.is_likely_non_text(null_byte_file))

            # Test case 3: Standard text file
            text_file = p / "text.txt"
            text_file.write_text("hello world")
            self.assertFalse(pack.is_likely_non_text(text_file))

            # Test case 4: Empty file
            empty_file = p / "empty.txt"
            empty_file.touch()
            self.assertFalse(pack.is_likely_non_text(empty_file))

    def test_should_ignore(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            
            # Setup directory structure
            (root_dir / ".git").mkdir()
            (root_dir / ".git" / "config").write_text("git config")
            (root_dir / "src").mkdir()
            (root_dir / "src" / "main.py").write_text("print('hello')")
            (root_dir / "src" / "main_test.py").write_text("assert True")
            (root_dir / ".env").write_text("SECRET=123")
            large_file = root_dir / "large.log"
            large_file.write_text("a" * 2000) # 2000 bytes
            binary_file = root_dir / "image.png"
            binary_file.write_text("not really a png")


            # Test Case 1: File larger than max_file_size_bytes
            should_ignore_result, reason = pack.should_ignore(large_file, root_dir, "*", "", 1000)
            self.assertTrue(should_ignore_result)
            self.assertIn("File too large", reason)
            
            should_ignore_result, reason = pack.should_ignore(large_file, root_dir, "*", "", 3000)
            self.assertFalse(should_ignore_result)
            self.assertEqual(reason, "Not ignored")

            # Test Case 2: Hidden file
            should_ignore_result, reason = pack.should_ignore(root_dir / ".env", root_dir, "*", "", 5000)
            self.assertTrue(should_ignore_result)
            self.assertEqual(reason, "Is a hidden file")

            # Test Case 3: File within a hidden directory
            should_ignore_result, reason = pack.should_ignore(root_dir / ".git" / "config", root_dir, "*", "", 5000)
            self.assertTrue(should_ignore_result)
            self.assertEqual(reason, "Is in a hidden directory")

            # Test Case 4: include_pattern
            should_ignore_result, reason = pack.should_ignore(root_dir / "src" / "main.py", root_dir, "*.py", "", 5000)
            self.assertFalse(should_ignore_result)
            self.assertEqual(reason, "Not ignored")
            
            should_ignore_result, reason = pack.should_ignore(root_dir / "src" / "main.py", root_dir, "*.txt", "", 5000)
            self.assertTrue(should_ignore_result)
            self.assertIn("Does not match include pattern", reason)

            # Test Case 5: exclude_pattern
            should_ignore_result, reason = pack.should_ignore(root_dir / "src" / "main_test.py", root_dir, "*", "*_test.py", 5000)
            self.assertTrue(should_ignore_result)
            self.assertIn("Matches exclude pattern", reason)
            
            should_ignore_result, reason = pack.should_ignore(root_dir / "src" / "main.py", root_dir, "*", "*_test.py", 5000)
            self.assertFalse(should_ignore_result)
            self.assertEqual(reason, "Not ignored")

            # Test Case 6: Likely binary file
            should_ignore_result, reason = pack.should_ignore(binary_file, root_dir, "*", "", 5000)
            self.assertTrue(should_ignore_result)
            self.assertEqual(reason, "Is likely non text")

class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.tmpdir.name)
        
        # Create a test directory structure
        (self.root_dir / "project").mkdir()
        self.project_dir = self.root_dir / "project"
        (self.project_dir / "src").mkdir()
        (self.project_dir / "src" / "main.py").write_text("main content")
        (self.project_dir / "src" / "utils.py").write_text("utils content")
        (self.project_dir / "tests").mkdir()
        (self.project_dir / "tests" / "test_main.py").write_text("test content")
        (self.project_dir / ".git").mkdir()
        (self.project_dir / ".git" / "config").write_text("git stuff")
        (self.project_dir / "README.md").write_text("readme content")
        (self.root_dir / "another_file.txt").write_text("another content")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_collect_files_content_default(self):
        results = pack.collect_files_content(
            input_paths_str=[str(self.project_dir)],
            include_pattern="*",
            exclude_pattern="",
            max_file_size_bytes=10000,
            num_workers=1,
            paths_only=False,
            using_stdout=False
        )
        
        relative_paths = sorted([r[0] for r in results])
        
        self.assertEqual(len(relative_paths), 4)
        self.assertEqual(relative_paths, [
            "README.md",
            "src/main.py",
            "src/utils.py",
            "tests/test_main.py"
        ])
        
        # Check content
        readme_result = next(r for r in results if r[0] == "README.md")
        self.assertEqual(readme_result[1], "readme content")

    def test_collect_files_content_with_patterns(self):
        results = pack.collect_files_content(
            input_paths_str=[str(self.project_dir)],
            include_pattern="src/*.py",
            exclude_pattern="*utils*",
            max_file_size_bytes=10000,
            num_workers=1,
            paths_only=False,
            using_stdout=False
        )
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "src/main.py")
        self.assertEqual(results[0][1], "main content")

    def test_collect_files_content_mixed_input(self):
        another_txt_file = self.root_dir / "another_file.txt"
        another_txt_file.write_text("another content")
        another_md_file = self.root_dir / "another_file.md"
        another_md_file.write_text("another content")
        results = pack.collect_files_content(
            input_paths_str=[str(self.project_dir / "src"), str(another_txt_file), str(another_md_file)],
            include_pattern="*",
            exclude_pattern="*.md",
            max_file_size_bytes=10000,
            num_workers=1,
            paths_only=False,
            using_stdout=False
        )
        
        relative_paths = sorted([r[0] for r in results])
        filenames = sorted([Path(p).name for p in relative_paths])
        self.assertEqual(filenames, ["another_file.txt", "main.py", "utils.py"])


class TestE2EFunctional(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.tmpdir.name).resolve()
        
        # Create a test directory structure
        self.project_dir = self.root_dir / "project"
        self.project_dir.mkdir()
        (self.project_dir / "src").mkdir()
        (self.project_dir / "src" / "main.py").write_text("main content")
        (self.project_dir / "src" / "utils.py").write_text("utils content")
        (self.project_dir / "tests").mkdir()
        (self.project_dir / "tests" / "test_main.py").write_text("test content")
        (self.project_dir / ".git").mkdir()
        (self.project_dir / ".git" / "config").write_text("git stuff")
        (self.project_dir / "README.md").write_text("readme content")
        (self.project_dir / "large_file.log").write_text(
            "a" * 50 + "\n" + "b" * 20 + "\n" + "c" * 70)
        (self.project_dir / "image.png").touch()

        # Path to the script
        self.pack_script_path = Path(__file__).parent.parent / "pack"

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_pack(self, args, cwd):
        command = [str(self.pack_script_path)] + args
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)

    def test_piped_output_to_stdout(self):
        # subprocess.run with capture_output=True makes stdout not a tty.
        result = self.run_pack([], cwd=self.project_dir)
        self.assertEqual(result.returncode, 0)
        
        output_file = self.project_dir / "output.txt"
        self.assertFalse(output_file.exists())
        
        content = result.stdout
        self.maxDiff = None
        self.assertEqual(content, """>>>> README.md
readme content
>>>> large_file.log
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
bbbbbbbbbbbbbbbbbbbb
cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
>>>> src/main.py
main content
>>>> src/utils.py
utils content
>>>> tests/test_main.py
test content
""")

    def test_argument_handling_include(self):
        result = self.run_pack(["-i", "*.md"], cwd=self.project_dir)
        self.assertEqual(result.returncode, 0)
        content = result.stdout
        self.assertIn(">>>> README.md", content)
        self.assertNotIn("main.py", content)

    def test_argument_handling_exclude(self):
        result = self.run_pack(["-e", "tests/*"], cwd=self.project_dir)
        self.assertEqual(result.returncode, 0)
        content = result.stdout
        self.assertIn(">>>> README.md", content)
        self.assertIn("main.py", content)
        self.assertNotIn("test_main.py", content)

    def test_max_file_size(self):
        result = self.run_pack(["--max-file-size", "100"], cwd=self.project_dir)
        self.assertEqual(result.returncode, 0)
        content = result.stdout
        self.assertIn(">>>> README.md", content)
        self.assertNotIn("large_file.log", content)

    def test_paths_only(self):
        result = self.run_pack(["--paths-only"], cwd=self.project_dir)
        self.assertEqual(result.returncode, 0)
        content = result.stdout
        self.assertIn("README.md", content)
        self.assertIn("src/main.py", content)
        self.assertNotIn("main content", content)
        self.assertNotIn("readme content", content)

    def test_output_tokens_size_only(self):
        # This test assumes tiktoken might not be installed, which is fine.
        result = self.run_pack(["--output-tokens-size-only"], cwd=self.project_dir)
        self.assertEqual(result.returncode, 0)
        content = result.stdout
        self.maxDiff = None
        self.assertEqual(content, """>>>> README.md
7 tokens, 29 bytes

>>>> large_file.log
37 tokens, 162 bytes

>>>> src/main.py
7 tokens, 29 bytes

>>>> src/utils.py
7 tokens, 31 bytes

>>>> tests/test_main.py
8 tokens, 36 bytes

Total tokens of input files: 66
""")

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
