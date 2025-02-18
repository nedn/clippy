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
*   **OpenAI Python Library:** Install the `openai` library using pip:
    ```bash
    pip install openai
    ```

### Installation

1.  **Download the `clippy` script:** Save the provided Python script as `clippy` (or any name you prefer).
2.  **Move to your PATH (Optional):** For easier access from anywhere in your terminal, you can move the `clippy` script to a directory in your system's PATH, such as `/usr/local/bin/` or `~/bin/`.
    ```bash
    # Example for /usr/local/bin (may require sudo)
    sudo mv clippy /usr/local/bin/
    ```
    or
    ```bash
    # Example for ~/bin (ensure ~/bin is in your PATH)
    mv clippy ~/bin/
    ```

### Configuration

Before you can start asking questions, you need to configure Clippy with your desired AI model and API key. Use the `set_model` command:

```bash
clippy set_model <model_name>:<your_api_key>
```


### Examples

````bash
$ clippy set_model gpt-4o:<openai-api-key>
Model 'gpt-4o' set successfully.
Model 'gpt-4o' set as default.
$ clippy set_model gemini-2.0-flash:<gemini-api-key> --default
Model 'gemini-2.0-flash' set successfully.
Model 'gemini-2.0-flash' set as default.
$ clippy list_models

Configured Models:
  gpt-4o
* gemini-2.0-flash

* indicates default model

$ clippy ask "what is the capital of France?"
Sending prompt to model 'gemini-2.0-flash'...

AI Response:

The capital of France is **Paris**.

$ clippy ask "Give me the commandline to list all the files in folder projects/ recursively. The command should show list the file names only and noth
ing else"
Sending prompt to model 'gemini-2.0-flash'...

AI Response:

```bash
find projects/ -type f -print
```

$ man ffmpeg | clippy ask "give me the ffmpeg commandline to shorten a video in half"
Sending prompt to model 'gemini-2.0-flash'...

AI Response:

```bash
ffmpeg -i input.mp4 -ss 0 -to $(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 input.mp4 | awk '{printf "%.3f\n", $1/2}') -c copy output.mp4
```
````

If you install the [yek utility](https://github.com/bodo-run/yek), then you can
do the following:

```bash
$ git clone https://github.com/karpathy/cryptos
$ yek cryptos/ | clippy ask "Give me a high level overview of this project"
Sending prompt to model 'gemini-2.0-flash'...

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
