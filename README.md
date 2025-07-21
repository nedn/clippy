# Clippy: Your Command-Line AI Assistant

**Clippy** is a simple yet powerful command-line interface (CLI) tool that lets you interact with various AI models like OpenAI's GPT series, Google's Gemini, and Anthropic's Claude directly from your terminal. Ask questions, get explanations, summarize text, and more – all without leaving your command line!

## Features

*   **Multi-Model Support:**  Works with OpenAI (gpt-4o, gpt-3.5-turbo, etc.), Google Gemini (gemini-pro), and Anthropic Claude models (and potentially others compatible with the OpenAI API endpoint).
*   **Easy Setup:**  Simple configuration to set your preferred AI model and API key.
*   **Ask Questions:**  Pose questions to the AI model and receive insightful responses directly in your terminal.
*   **Piping Input:**  Seamlessly feed file content to Clippy using pipes, allowing you to analyze and process files with AI.
*   **Configuration File:** Stores your model and API key securely in a configuration file in your home directory (`~/.clippy/config.json`).

## Getting Started

### Prerequisites

*   **Python 3.6 or higher:** Make sure you have Python installed on your system.

### Installation

1.  **Download the `clippy` script:**
   -   Just clone this git repo:

       ```bash
       git clone https://github.com/nedn/clippy
       ```

2.  **Add to PATH:**

    **Linux/macOS:**

    -   Add the following line to your shell's configuration file (e.g., `~/.bashrc`, `~/.zshrc`):

        ```bash
        export PATH="$PATH:/path/to/directory/containing/clippy"
        ```
         Replace `/path/to/directory/containing/` with the *actual* path to the directory where you saved `clippy`.

    -   Reload your shell configuration:

        ```bash
        source ~/.bashrc  # Or source ~/.zshrc, etc.
        ```
    **Windows:**

    1.  Search for "environment variables" in the Start Menu and select "**Edit the system environment variables**".
    2.  Click the "**Environment Variables...**" button.
    3.  Under "**System variables**", select the `Path` variable and click "**Edit...**".
    4.  Click "**New**" and add the full path to the directory containing the `clippy` script.
    5.  Click "**OK**" on all open windows.
    6.  **Restart your terminal** for the changes to take effect.

> **Note:** The `run_script.sh` wrapper automatically handles Python dependency installation. When you first run the script, it will create a virtual environment and install all required packages from `requirements.txt`. You don't need to manually install any dependencies.

### Configuration

Before you can start asking questions, you need to configure Clippy with your desired AI model and API key. Use the `set_model` command, e.g:

```bash
clippy set_model gemini-2.5-pro:<your_gemini_api_key>
clippy set_model gemini-2.5-flash:<your_gemini_api_key>
```


### Examples

````bash
$ clippy set_model gemini-2.5-pro:<gemini-api-key> --default
Model 'gemini-2.5-pro' set successfully.
Model 'gemini-2.5-pro' set as default.

$ clippy set_model gpt-4o:<openai-api-key>
Model 'gpt-4o' set successfully.
Model 'gpt-4o' set as default.

$ clippy ls

Configured Models:
* gemini-2.5-pro
  gpt-4o


* indicates default model

$ clippy ask "what is the capital of France?"
Sending prompt to model 'gemini-2.5-pro'...

AI Response:

The capital of France is **Paris**.

# ask is the default of clippy command so it's ok to just skip ask
$ clippy "Give me the commandline to list all the files in folder projects/ recursively. The command should show list the file names only and nothing else"
Sending prompt to model 'gemini-2.5-pro'...

AI Response:

```bash
find projects/ -type f -print
```

$ man ffmpeg | clippy "give me the ffmpeg commandline to shorten a video in half"
Sending prompt to model 'gemini-2.5-pro'...

AI Response:

```bash
ffmpeg -i input.mp4 -ss 0 -to $(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 input.mp4 | awk '{printf "%.3f\n", $1/2}') -c copy output.mp4
```

$ git diff | clippy  generate git commit message command
Checking for script updates...
Querying model 'gemini-2.5-pro-preview-03-25' (google)...

AI Response:

```bash
git commit -m "feat: Make 'ask' the default command" -m "If the first argument isn't a recognized command or option, default to the 'ask' command. Updated README examples."
```

````

## Using the `pack` Script

You can use the included [`pack`](pack) script to easily gather the content of multiple text files from a directory structure and pipe it directly into `clippy`. This is useful for providing broader context to the AI, such as asking questions about an entire codebase.

The `pack` script:
*   Recursively scans specified directories (or uses the current directory by default).
*   Reads text files in parallel for faster processing.
*   Skips hidden files/directories by default (like `.git`).
*   Attempts to automatically skip binary files (images, executables, etc.) based on file extensions and content checking.
*   Allows filtering files using include (`-i`) and exclude (`-e`) glob patterns.
*   Skips files larger than a configurable size (`--max-file-size`, default 5MB).
*   Outputs the combined content, prepending each file's content with `>>>> path/to/file.ext`.
*   Can optionally output just the file paths (`--paths-only`).
*   If `tiktoken` is installed, it will estimate the total token count.

**Example:**

```bash
# Clone a repository
$ git clone https://github.com/karpathy/cryptos

# Use 'pack' to combine its text files and ask clippy about it
$ pack cryptos/ | clippy "Give me a high level overview of this project"
Sending prompt to model 'gemini-2.5-pro'...

AI Response:

Okay, here's a high-level overview of the project:

**Overall Goal:**

- To build a pure Python, zero-dependency implementation of Bitcoin for educational purposes.

**Key Components & Functionality:**

- **`blog.ipynb`:**
    - A Jupyter Notebook that guides the user through creating, digitally signing, and broadcasting a Bitcoin transaction from scratch.
    - Covers cryptographic identity generation (private/public keypairs using Elliptic Curve Cryptography).
    - Implements SHA256 and RIPEMD160 hash functions from scratch.
    - Derives Bitcoin wallet addresses.
    - Explains transaction structure, inputs, outputs, and fees.
    - Details digital signature creation using ECDSA.
    - Shows how to broadcast a transaction to the Bitcoin network (using a third-party service).
- **`cryptos` directory:** Contains Python modules with the core implementations.
    - **`__init__.py`:**  Empty file, likely used to make the directory a Python package.
    - **`block.py`:** Defines the `Block` object, related functions, and constants for working with Bitcoin blocks.
        - Includes decoding and encoding blocks from bytes
        - Calculating the Block ID, the target and the difficulty
        - Functionality to validate a block.
    - **`ecdsa.py`:** Implements the Elliptic Curve Digital Signature Algorithm (ECDSA) for signing and verifying transactions.
    - **`bitcoin.py`:** Contains Bitcoin-specific constants and parameters, such as the `BITCOIN` object holding curve and generator information.
    - **`network.py`:** Implements classes and utilities for connecting to Bitcoin nodes and communicating using the Bitcoin protocol. Includes functions for encoding/decoding version, verack, ping, pong, getheaders and headers messages
    - **`ripemd160.py`:** Provides a pure Python implementation of the RIPEMD-160 hash function.
    - **`sha256.py`:** Implements the SHA-256 hash function from scratch.
    - **`transaction.py`:** Defines the `Tx`, `TxIn`, `TxOut`, and `Script` objects for working with Bitcoin transactions. Implements decoding and encoding transactions from bytes. Includes functions for calculating transaction IDs, and fees.
    - **`keys.py`:** Utilities for generating secret/public key pairs and deriving Bitcoin addresses. Implements base58 encoding/decoding.
- **`tests` directory:** Contains unit tests for the modules in the `cryptos` directory.
- **`README.md`:** Provides a high-level overview of the project, including instructions on how to use the code and run the tests.
- **`getnewaddress.py`:** A command-line tool to generate a new Bitcoin secret/public key pair and address.

```
