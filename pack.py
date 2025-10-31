#!/usr/bin/env python3
"""
This script, `pack`, is a command-line utility designed to recursively find and
concatenate the contents of text files from specified directories or files into
a single output. It's optimized for speed by reading files in parallel using a
thread pool.

The main purpose of this tool is to "pack" a project's source code into a
single text file, which can then be easily used as context for Large Language
Models (LLMs). By default, it intelligently filters out binary files, hidden
files (like .git), and overly large files to keep the output clean and relevant.

How to Run:

The script is executed from the command line. You can specify one or more paths
to files or directories. If no path is provided, it defaults to the current
directory.

Basic Usage:
- Pack the current directory:
  $ pack

- Pack a specific directory:
  $ pack ./my_project

- Pack multiple directories and files:
  $ pack ./src ./docs/README.md

- Pipe the output to another command (e.g., clipboard):
  $ pack | pbcopy

Filtering and Options:
The script provides several flags to customize its behavior:

- `-i` or `--include`:
  Specifies a glob pattern to include only certain files.
  Example: To pack only Python files:
  $ pack -i "*.py"

- `-e` or `--exclude`:
  Specifies a glob pattern to exclude certain files or directories.
  Example: To exclude all test files:
  $ pack -e "*_test.py"

- `--max-file-size`:
  Sets a limit on the size of files to include. This is useful for excluding
  large data files or logs. Sizes can be specified in human-readable formats.
  Example: To include files up to 1MB:
  $ pack --max-file-size 1M

- `--paths-only`:
  This flag will output only the list of file paths that would be included,
  without their content. This is useful for previewing what will be packed.
  Example:
  $ pack --paths-only

- `--output-tokens-size-only`:
  This flag will output the token count and byte size for each file instead of
  its content. This is useful for estimating the size of the final packed
  content to ensure it fits within a model's context window. Requires the
  `tiktoken` library to be installed (`pip install tiktoken`).
  Example:
  $ pack --output-tokens-size-only

Output Behavior:
- If the output is a terminal (TTY), the script will write to a file named
  `output.txt` in the current directory.
- If the output is piped or redirected, the script will write directly to
  `stdout`. This allows for seamless integration with other command-line tools.
"""

import argparse
import sys
import os
import logging
from pathlib import Path
import concurrent.futures
import fnmatch
import re
import shlex
from typing import TextIO

try:
    import tiktoken
except ImportError:
    print(
        "Warning: tiktoken is not installed, total token count will be disabled."
        "Install it with 'pip install tiktoken'",
        file=sys.stderr)
    tiktoken = None

# --- Configuration ---
DEFAULT_OUTPUT_FILENAME = "output.txt"
MAX_WORKERS = os.cpu_count() or 4  # Use CPU count or default to 4 workers
READ_CHUNK_SIZE = 1024 * 1024  # Read in 1MB chunks for binary check
DEFAULT_max_file_size_bytes = 5 * 1024 * 1024  # Default 5 MB

# --- Helper Functions ---

# Define a reasonable chunk size for reading
READ_CHUNK_SIZE = 1024  # Read 1KB chunk


def parse_size(size_str: str) -> int:
    """Parse human-readable size string (e.g., '5M', '10K', '2G') into bytes."""
    size_str = size_str.upper()
    match = re.match(r'^(\d+(\.\d+)?)\s*([KMGTPEZY]?B?)?$', size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")

    size = float(match.group(1))
    unit = match.group(3) if match.group(3) else ''

    if unit in ('', 'B'):
        factor = 1
    elif unit in ('K', 'KB'):
        factor = 1024
    elif unit in ('M', 'MB'):
        factor = 1024**2
    elif unit in ('G', 'GB'):
        factor = 1024**3
    elif unit in ('T', 'TB'):
        factor = 1024**4
    elif unit in ('P', 'PB'):
        factor = 1024**5
    elif unit in ('E', 'EB'):
        factor = 1024**6
    elif unit in ('Z', 'ZB'):
        factor = 1024**7
    elif unit in ('Y', 'YB'):
        factor = 1024**8
    else:
        raise ValueError(f"Unknown size unit: {unit}")

    return int(size * factor)


# Common non-text file extensions (lowercase)
# This list is not exhaustive but covers many common binary formats.
NON_TEXT_EXTENSIONS = [
    # Images
    '.jpg',
    '.jpeg',
    '.png',
    '.gif',
    '.bmp',
    '.tiff',
    '.webp',
    '.ico',
    '.heic',
    '.heif',

    # Audio
    '.mp3',
    '.wav',
    '.aac',
    '.ogg',
    '.flac',
    '.m4a',
    '.wma',
    '.aiff',

    # Video
    '.mp4',
    '.avi',
    '.mov',
    '.mkv',
    '.wmv',
    '.flv',
    '.webm',
    '.mpeg',
    '.mpg',

    # Compressed Archives
    '.zip',
    '.rar',
    '.tar',
    '.gz',
    '.bz2',
    '.7z',
    '.xz',
    '.iso',
    '.dmg',

    # Executables & Libraries
    '.exe',
    '.dll',
    '.so',
    '.dylib',
    '.app',
    '.msi',

    # Compiled Code / Object Files
    '.o',
    '.obj',
    '.class',
    '.pyc',
    '.pyo',
    '.wasm',

    # Documents (often binary or complex structure)
    '.pdf',
    '.doc',
    '.docx',
    '.xls',
    '.xlsx',
    '.ppt',
    '.pptx',
    '.odt',
    '.ods',
    '.odp',  # OpenDocument formats

    # Databases
    # .dat is ambiguous but often binary
    '.sqlite',
    '.db',
    '.mdb',
    '.accdb',
    '.dat',

    # Fonts
    '.ttf',
    '.otf',
    '.woff',
    '.woff2',
    '.eot',

    # Other common binary/non-text data
    '.bin',
    '.dat',  # Reiterate .dat as it's common
    '.pickle',
    '.pkl',  # Python serialized objects
    '.joblib',  # Scikit-learn models
    '.h5',
    '.hdf5',  # Hierarchical Data Format
    '.parquet',  # Columnar storage format
    '.avro',  # Data serialization system
    '.feather',  # Fast, lightweight file format
    '.arrow',  # Apache Arrow format
    '.model',  # Generic model files
    '.pt',
    '.pth',  # PyTorch models
    '.pb',  # Protocol Buffers (often used for ML models)
    '.onnx',  # Open Neural Network Exchange
    '.sav',  # SPSS data file
    '.dta',  # Stata data file
    '.idx',  # Often index files (binary)
    '.pack',  # Git pack files
    '.deb',
    '.rpm',  # Package manager files
    '.jar',  # Java archives
    '.war',
    '.ear',  # Java web/enterprise archives
    '.swf',  # Adobe Flash (obsolete but might be encountered)
    '.psd',  # Adobe Photoshop
    # Adobe Illustrator (often PDF compatible but proprietary)
    '.ai',
    '.indd',  # Adobe InDesign
    '.blend',  # Blender 3D files
    '.dwg',
    '.dxf',  # CAD files (DXF can be text, but often complex)
    '.skp',  # SketchUp files
    '.stl',  # Stereolithography (3D printing)
    # Wavefront OBJ (can be text, but often large/complex geometry data)
    '.obj',
    '.fbx',  # Autodesk FBX (3D models)
    '.gltf',
    '.glb',  # GL Transmission Format (glb is binary)
    '.swp',  # Vim swap file (binary)
    '.lock',  # Often empty or contain minimal binary data
]

# Convert to a set for slightly faster lookups, though for this size, a list is fine too.
NON_TEXT_EXTENSIONS_SET = set(NON_TEXT_EXTENSIONS)


def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string."""
    if tiktoken is None:
        return -1  # Return -1 if tiktoken is not installed
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def is_likely_non_text(file_path: Path) -> bool:
    """
    Check if a file is likely non-text (binary).

    First checks the file extension against a list of known non-text types.
    If the extension doesn't match, it reads a small chunk of the file
    and checks for the presence of null bytes (a common indicator of binary data).

    Returns True if the file is likely non-text, False otherwise.
    Handles potential read errors gracefully.
    """
    # Check extension of file (case-insensitive)
    if file_path.suffix.lower() in NON_TEXT_EXTENSIONS_SET:
        return True

    # If extension isn't conclusive, check content for null bytes
    try:
        with file_path.open('rb') as f:
            chunk = f.read(READ_CHUNK_SIZE)
            # Check if a null byte exists in the chunk read
            # Empty files are considered not binary by this check
            return b'\0' in chunk
    except FileNotFoundError:
        print(f"Warning: File not found {file_path}", file=sys.stderr)
        return True  # Treat as non-text if it disappeared or never existed
    except IsADirectoryError:
        print(f"Warning: Path is a directory, not a file {file_path}",
              file=sys.stderr)
        return True  # Directories are not text files
    except PermissionError:
        print(f"Warning: Permission denied reading {file_path}",
              file=sys.stderr)
        return True  # Treat as non-text if we can't read it
    except OSError as e:
        # Catch other potential OS-level errors during open/read
        print(
            f"Warning: Could not read {file_path} to check for binary content: {e}",
            file=sys.stderr)
        return True  # Treat as non-text if we can't read it properly
    except Exception as e:
        # Catch any other unexpected errors
        print(
            f"Warning: Unexpected error checking binary status of {file_path}: {e}",
            file=sys.stderr)
        return True  # Default to treating as non-text on unexpected errors


def should_ignore(file_path: Path, root_dir: Path, include_pattern: str,
                  exclude_pattern: str, max_file_size_bytes: int) -> bool:
    """
    Check if a file should be ignored based on defined rules:
    - Not a file or inaccessible
    - Too large
    - Hidden file (starts with '.')
    - Inside a hidden directory (any parent part starts with '.')
    - Does not match the include pattern
    - Matches the exclude pattern
    - Is likely binary.
    """
    # 1. Check if it's actually a file (resolve symlinks first)
    try:
        if not file_path.is_file():
            # This might happen with broken symlinks during the walk
            return True
        # Check file size
        file_size = file_path.stat().st_size
        if file_size > max_file_size_bytes:
            logging.info(
                f"Skipping large file {file_path.name} ({file_size} bytes > {max_file_size_bytes} bytes)",
                file=sys.stderr)
            return True
    except OSError as e:
        # Could be a permission error or other issue accessing the file type/stat
        print(f"Warning: Could not check status of {file_path}: {e}",
              file=sys.stderr)
        return True  # Ignore if we can't verify it's a file or get its size

    # Use relative path for hidden checks and pattern matching
    try:
        relative_path = file_path.relative_to(root_dir)
        relative_path_str = str(relative_path)
    except ValueError:
        # Should not happen if file_path is within root_dir, but handle defensively
        print(
            f"Warning: Could not get relative path for {file_path} based on {root_dir}",
            file=sys.stderr)
        return True

    # 2. Check glob patterns
    # First check exclude pattern (if specified)
    if exclude_pattern and (fnmatch.fnmatch(relative_path_str, exclude_pattern)
                            or fnmatch.fnmatch(file_path.name,
                                               exclude_pattern)):
        return True

    # Then check include pattern
    if include_pattern != '*' and not fnmatch.fnmatch(
            relative_path_str, include_pattern) and not fnmatch.fnmatch(
                file_path.name, include_pattern):
        return True

    # 3. Check for hidden file/directory
    # Check filename itself
    if file_path.name.startswith('.'):
        return True
    # Check any parent directory component
    # Use relative_path.parts to avoid checking parts outside the root_dir
    # Check parent parts
    if any(part.startswith('.') for part in relative_path.parts[:-1]):
        return True

    # 4. Check for binary content (can be slow, do last)
    if is_likely_non_text(file_path):
        logging.info(f"Skipping likely non text file: {relative_path_str}",
                     file=sys.stderr)
        return True

    return False  # If none of the ignore conditions match


def read_file_content(file_path: Path,
                      root_dir: Path) -> tuple[str, str] | None:
    """
    Reads the content of a text file.
    Returns a tuple (relative_path_str, content) or None if reading fails.
    """
    try:
        relative_path = file_path.relative_to(root_dir)
        relative_path_str = str(relative_path)
        with file_path.open('r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return (relative_path_str, content)
    except OSError as e:
        print(f"Warning: Could not read file {file_path}: {e}",
              file=sys.stderr)
        return None
    except UnicodeDecodeError as e:
        # Should ideally be caught by is_likely_binary, but as a fallback
        print(f"Warning: Skipping file with encoding issues {file_path}: {e}",
              file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Unexpected error reading file {file_path}: {e}",
              file=sys.stderr)
        return None


def read_files_parallel(files_to_process: list[tuple[Path,
                                                     Path]], num_workers: int,
                        paths_only: bool) -> list[tuple[str, str]]:
    """
    Read files in parallel using a thread pool.
    Returns a list of tuples (relative_path_str, content).
    If paths_only is True, content will be empty string.
    """
    if paths_only:
        # In paths-only mode, we don't need to read file contents
        results = []
        for abs_path, root_dir in files_to_process:
            try:
                relative_path = abs_path.relative_to(root_dir)
                relative_path_str = str(relative_path)
                results.append((relative_path_str, ""))
            except Exception as e:
                print(
                    f"Warning: Could not get relative path for {abs_path}: {e}",
                    file=sys.stderr)
        return results

    # Normal mode - read file contents in parallel
    results = []
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_workers) as executor:
        # Submit tasks
        future_to_path = {
            executor.submit(read_file_content, abs_path, root_dir):
            (abs_path, root_dir)
            for abs_path, root_dir in files_to_process
        }

        # Collect results as they complete
        processed_count = 0
        for future in concurrent.futures.as_completed(future_to_path):
            abs_path, root_dir = future_to_path[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
                processed_count += 1
                # Optional: Progress indicator
                print(
                    f"\rProcessed: {processed_count}/{len(files_to_process)}",
                    end="",
                    file=sys.stderr)
            except Exception as e:
                print(f"\nError processing file {abs_path}: {e}",
                      file=sys.stderr)

    return results


def collect_results(input_paths_str: list[str], include_pattern: str,
                    exclude_pattern: str, max_file_size_bytes: int,
                    num_workers: int, paths_only: bool,
                    using_stdout: bool) -> list[tuple[str, str]]:

    cwd = Path('.').resolve()

    print(f"Processing paths: {', '.join(input_paths_str)}", file=sys.stderr)
    print(f"Using include pattern: {include_pattern}", file=sys.stderr)
    print(f"Using exclude pattern: {exclude_pattern}", file=sys.stderr)
    print(
        f"Ignoring hidden files/directories (within scanned dirs) and binary files.",
        file=sys.stderr)
    print(f"Maximum file size: {max_file_size_bytes:,} bytes", file=sys.stderr)
    print(f"Using {num_workers} workers", file=sys.stderr)
    print(f"Current working directory: {cwd}", file=sys.stderr)

    # (absolute_path, root_for_relative_path)
    files_to_process_tuples: list[tuple[Path, Path]] = []
    processed_files: set[Path] = set()  # Keep track of files added

    for path_str in input_paths_str:
        p = Path(path_str).resolve()

        if not p.exists():
            print(f"Warning: Input path not found: {path_str}",
                  file=sys.stderr)
            continue

        if p in processed_files:
            # Avoid processing the same resolved path twice if listed multiple times
            continue

        if p.is_file():
            # Check if file should be ignored (using simpler rules for explicit files)
            # Need to check size, binary, and if already processed
            try:
                file_size = p.stat().st_size
                is_too_large = file_size > max_file_size_bytes
                is_binary = is_likely_non_text(p)
                is_processed = p in processed_files

                if not is_too_large and not is_binary and not is_processed:
                    # Use cwd as root for relative path
                    files_to_process_tuples.append((p, cwd))
                    processed_files.add(p)
                else:
                    reason = []
                    if is_too_large:
                        reason.append(
                            f"too large ({file_size} > {max_file_size_bytes})")
                    if is_binary:
                        reason.append("likely binary")
                    if is_processed:
                        reason.append("already processed")
                    print(
                        f"Info: Ignoring explicitly provided file: {path_str} ({', '.join(reason)})",
                        file=sys.stderr)
            except OSError as e:
                print(
                    f"Warning: Could not stat explicitly provided file {path_str}: {e}",
                    file=sys.stderr)

        elif p.is_dir():
            print(f"Scanning directory: {p}", file=sys.stderr)
            try:
                # Use rglob for recursion
                for item in p.rglob('*'):
                    # Combine checks for file, not processed, and not ignored
                    if item not in processed_files and not should_ignore(
                            item, p, include_pattern, exclude_pattern,
                            max_file_size_bytes):
                        files_to_process_tuples.append(
                            (item, p))  # Use dir 'p' as root
                        processed_files.add(item)
            except PermissionError as e:
                print(f"Warning: Permission denied during scan of {p}: {e}",
                      file=sys.stderr)
            except Exception as e:
                print(f"Error during scan of {p}: {e}", file=sys.stderr)
                # Decide if we should exit or just continue
                # continue # Continue with next path for now
        else:
            print(
                f"Warning: Input path is neither a file nor a directory: {path_str}",
                file=sys.stderr)

    # --- Filtering & Sorting (Preparation) ---
    print(
        f"Found {len(files_to_process_tuples)} potential files. Preparing list...",
        file=sys.stderr)

    # Calculate relative paths and prepare for sorting
    files_to_sort = []
    for abs_path, root_for_rel in files_to_process_tuples:
        try:
            rel_path_str = str(abs_path.relative_to(root_for_rel))
            files_to_sort.append((rel_path_str, abs_path, root_for_rel))
        except ValueError:
            print(
                f"Warning: Could not compute relative path for {abs_path} based on {root_for_rel}. Using absolute path.",
                file=sys.stderr)
            # Fallback: Use absolute path string or just filename for sorting
            files_to_sort.append((abs_path.name, abs_path, root_for_rel))

    # Sort files based on the calculated relative path string
    files_to_sort.sort(key=lambda item: item[0])

    # Reconstruct the list of tuples in the sorted order for reading
    sorted_files_info = [
        (abs_path, root_for_rel)
        for rel_path_str, abs_path, root_for_rel in files_to_sort
    ]

    print(f"Processing {len(sorted_files_info)} files...", file=sys.stderr)

    # --- Parallel Reading (Needs updated function call) ---
    results = read_files_parallel(sorted_files_info, num_workers, paths_only)
    # Newline after progress indicator
    print("\nReading complete.", file=sys.stderr)

    # --- Sort results by relative path (already done conceptually, but results format might change) ---
    # The results from read_files_parallel should already contain the correct relative paths
    # Let's ensure the sorting of the final results list remains
    # Sort by relative_path_str returned by read_file_content
    results.sort(key=lambda item: item[0])

    return results


def write_output(output_target: TextIO, results: list[tuple[str, str]],
                 using_stdout: bool, output_tokens_size_only: bool) -> int:
    """
    Write the results to the output target.
    Returns the total number of tokens of the output.
    """
    # --- Writing Output ---
    total_tokens_of_files = 0
    total_tokens_of_output = 0
    try:
        file_count = 0
        total_files = len(results)
        for relative_path, content in results:
            file_info = f">>>> {relative_path}\n"
            file_content = file_info + content
            file_content_tokens = count_tokens(file_content)
            total_tokens_of_files += file_content_tokens
            if output_tokens_size_only:
                to_write = file_info + \
                    f"\n{file_content_tokens} tokens, {len(file_content)} bytes\n"
            else:
                to_write = file_content
            output_target.write(to_write)
            output_target.write('\n')
            total_tokens_of_output += count_tokens(to_write)
            output_target.flush()  # Flush periodically for long outputs
            file_count += 1
            # Show progress as percentage
            percentage = (file_count / total_files) * 100
            print(f"\rWriting: {percentage:.1f}%", end="", file=sys.stderr)
    except Exception as e:
        print(f"\nError writing output for {file_info}: {e}", file=sys.stderr)
        # Avoid traceback flood if stdout pipe is broken
        if isinstance(e, BrokenPipeError):
            sys.exit(0)  # Exit cleanly if pipe is broken
        else:
            sys.exit(1)
    finally:
        if output_tokens_size_only:
            output_target.write(
                f"Total tokens of input files: {total_tokens_of_files:,}\n")
        if output_target and not using_stdout:
            output_target.close()
        # Newline after progress indicator
        print("\n", end="", file=sys.stderr)

    print(f"\nSuccessfully combined content of {file_count} files.",
          file=sys.stderr)
    print(f"Total tokens (approximate): {total_tokens_of_output:,}",
          file=sys.stderr)
    return total_tokens_of_output


def print_warning_about_large_output(total_tokens_of_output: int,
                                     argv: list[str]):
    """
    Prints a warning to stderr if the output token count is very large,
    and suggests a command to help the user selectively pack files.
    """
    # Reconstruct the original command, adding the --output-tokens-size-only flag
    args_for_token_size_cmd = argv[1:]
    if '--output-tokens-size-only' not in args_for_token_size_cmd and '-t' not in args_for_token_size_cmd:
        args_for_token_size_cmd.append('--output-tokens-size-only')

    # Use shlex.join for robust command line string construction
    script_name = argv[0]
    token_size_cmd = shlex.join([script_name] + args_for_token_size_cmd)
    original_cmd = shlex.join(argv)
    help_cmd = shlex.join([script_name, '--help'])

    # The combined command that the user can copy-paste
    suggested_command = (
        f'(echo "Original directory where the command was run fromm: {os.getcwd()};" '
        f'echo "Original run command that resulted in large token output: {original_cmd}"; '
        f'echo "--- Help output ---"; {help_cmd}; '
        f'echo "--- File token/size analysis ---"; {token_size_cmd})'
        )

    warning_message = f"""
================================================================================
===== WARNING: LARGE OUTPUT DETECTED =====
================================================================================

The generated output is approximately {total_tokens_of_output:,} tokens.
This is very large and will likely exceed the context window of most LLMs.

To help you refine your selection, here is a command that will:
1. Show you the help message for `pack`.
2. List all the files from your original command with their token/byte counts.
3. Save this combined information to a file & use it as context for the LLM.
4. Use the LLM to help you create a new, more selective `pack` command.

An example get started:
--------------------------------------------------------------------------------
Run: `{suggested_command} > llm_context.txt`

Then add the content of `llm_context.txt` to your prompt and ask the LLM to help 
you create a new, more selective `pack` command to pack only the files that 
are most relevant to the task.

Example prompt: "I am working on writting feature X. Please help me create a 
new, more selective `pack` command to pack only the files that are most relevant 
to the task. Context is in attached file `llm_context.txt`".
--------------------------------------------------------------------------------
"""
    print(warning_message, file=sys.stderr)


def main(argv: list[str]):
    parser = argparse.ArgumentParser(
        description=
        "Recursively combine content of text files from specified files and directories.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        "paths",
        nargs="*",  # Accept zero or more arguments
        default=["."],  # Default to current directory if no paths are given
        help=
        "List of files and/or directories to process. If directories are provided, "
        "they will be scanned recursively. Defaults to the current directory if none specified."
    )
    parser.add_argument(
        "-i",
        "--include",
        default="*",
        help="Optional file glob pattern (e.g., '*.py', 'src/**/test_*.py'). "
        "Filters files based on their relative path within the target directory."
    )
    parser.add_argument(
        "-e",
        "--exclude",
        default="",
        help="Optional file glob pattern (e.g., '*.py', 'src/**/test_*.py'). "
        "Filters files based on their relative path within the target directory."
    )
    parser.add_argument("-w",
                        "--workers",
                        type=int,
                        default=MAX_WORKERS,
                        help="Number of parallel workers for reading files.")
    parser.add_argument("--paths-only",
                        action="store_true",
                        help="Only output file paths, without their content.")
    parser.add_argument(
        "--max-file-size",
        type=str,  # Accept string input for parsing
        default=f"{DEFAULT_max_file_size_bytes}",  # Use the constant
        help=
        "Maximum size for individual files (e.g., '5M', '100K', '1G'). Files larger than this will be skipped."
    )
    parser.add_argument(
        "-t",
        "--output-tokens-size-only",
        action="store_true",
        help=
        "Only output the total number of tokens per file and the total size of the output."
        "This is useful for gauging the size of the output and come up with a strategy for "
        "selective packing, such as using a smaller model or a smaller context window."
    )

    args = parser.parse_args()

    # Resolve input paths immediately
    input_paths_str = args.paths
    include_pattern = args.include
    exclude_pattern = args.exclude
    num_workers = args.workers
    paths_only = args.paths_only  # Get paths_only flag

    try:
        max_file_size_bytes = parse_size(args.max_file_size)
    except ValueError as e:
        print(f"Error: Invalid --max-file-size value: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Determine Output Destination ---
    output_target = None
    using_stdout = False
    if sys.stdout.isatty():
        # Output is to a terminal, write to default file
        output_filename = DEFAULT_OUTPUT_FILENAME
        print(f"Outputting to file: {os.path.abspath(output_filename)}",
              file=sys.stderr)
        try:
            output_target = open(output_filename, 'w', encoding='utf-8')
        except OSError as e:
            print(f"Error: Could not open output file {output_filename}: {e}",
                  file=sys.stderr)
            sys.exit(1)
    else:
        # Output is piped or redirected, write to stdout
        print(f"Outputting to stdout", file=sys.stderr)
        output_target = sys.stdout
        using_stdout = True

    results = collect_results(input_paths_str=input_paths_str,
                              include_pattern=include_pattern,
                              exclude_pattern=exclude_pattern,
                              max_file_size_bytes=max_file_size_bytes,
                              num_workers=num_workers,
                              paths_only=paths_only,
                              using_stdout=using_stdout)

    total_tokens_of_output = write_output(
        output_target=output_target,
        results=results,
        using_stdout=using_stdout,
        output_tokens_size_only=args.output_tokens_size_only)
    if total_tokens_of_output > 800000 and args.output_tokens_size_only is False:
        print_warning_about_large_output(
            total_tokens_of_output=total_tokens_of_output, argv=argv)


if __name__ == "__main__":
    main(argv=sys.argv)
