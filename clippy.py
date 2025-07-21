#!/usr/bin/env python3

import argparse
import json
import os
import sys
import platform
import textwrap
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Callable

# --- Dependency Check ---
try:
    import requests
except ImportError:
    _CLIPPY_DIR = os.path.dirname(__file__)
    _REQUIREMENT_PATH = os.path.abspath(
        os.path.join(_CLIPPY_DIR, 'requirements.txt'))
    _VENV_PATH = os.path.abspath(
        os.path.join(_CLIPPY_DIR, 'venv'))
    command = sys.executable + " -m pip install -r " + _REQUIREMENT_PATH
    clean_command = "rm -rf " + _VENV_PATH
    print(
        "Error: The 'requests' library is required but not found.",
        "To address this issue, run: `" + clean_command +
        "` then run clippy command again", file=sys.stderr,
    )
    sys.exit(1)

# --- Constants ---
CONFIG_DIR = os.path.expanduser("~/.clippy")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOG_HISTORY_DIR = os.path.join(CONFIG_DIR, "history") # Added log directory
DEFAULT_TIMEOUT = 60  # Default request timeout in seconds
CLIPPY_REPO_URL = "https://github.com/nedn/clippy" # Added repo URL

# ANSI Color Codes
# Use functions for clarity and to ensure reset
def color_text(text: str, color_code: str) -> str:
    """Applies ANSI color code to text, ensuring reset."""
    if not sys.stdout.isatty():
        return text
    # Assume modern terminals support ANSI colors on Windows too
    # if platform.system() == "Windows":
    #     return text # Disable colors on Windows if needed
    return f"{color_code}{text}\033[0m"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m" # Added for warnings
CYAN = "\033[36m"
MAGENTA = "\033[35m" # Added for log session header
BOLD = "\033[1m"
RESET = "\033[0m" # Keep for internal use if needed

def error_print(*args, **kwargs):
    """Prints arguments to stderr in red."""
    print(color_text("Error:", RED + BOLD), *args, file=sys.stderr, **kwargs)

def warn_print(*args, **kwargs):
    """Prints arguments to stderr in yellow."""
    print(color_text("Warning:", YELLOW + BOLD), *args, file=sys.stderr, **kwargs)

def success_print(*args, **kwargs):
    """Prints arguments to stdout in green."""
    print(color_text("Success:", GREEN + BOLD), *args, **kwargs)

def info_print(*args, **kwargs):
    """Prints arguments to stdout (standard color)."""
    print(*args, **kwargs)


# --- Update Check ---

def run_git_command(command: List[str]) -> Tuple[Optional[str], Optional[str], int]:
    """Runs a git command and returns stdout, stderr, and return code."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Ensure the script directory exists (might not if run strangely)
    if not os.path.isdir(script_dir):
         return None, "Cannot determine script directory for git command.", -1
    try:
        process = subprocess.run(
            ["git"] + command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False, # Don't raise exception on non-zero exit
            cwd=script_dir # Run git in the script's directory
        )
        return process.stdout.strip(), process.stderr.strip(), process.returncode
    except FileNotFoundError:
        return None, "Git command not found. Please ensure git is installed and in your PATH.", -1
    except Exception as e:
        return None, f"Failed to run git command: {e}", -1

def check_for_updates():
    """Checks if the local clippy script is behind the remote main branch."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isdir(os.path.join(script_dir, '.git')):
         # info_print("Not a git repository. Skipping update check.")
         return # Silently skip if not in a git repo

    # 1. Check if inside a git repository
    stdout, stderr, retcode = run_git_command(["rev-parse", "--is-inside-work-tree"])
    if retcode != 0 or stdout != 'true':
        # warn_print("Not running inside a git repository. Skipping update check.")
        return # Silently skip if not in a git repo

    # 2. Check if remote 'origin' points to the correct repo
    stdout, stderr, retcode = run_git_command(["remote", "get-url", "origin"])
    if retcode != 0 or not stdout or CLIPPY_REPO_URL not in stdout:
        # warn_print(f"Git remote 'origin' does not point to {CLIPPY_REPO_URL}. Skipping update check.")
        return # Silently skip if remote is wrong

    # 3. Fetch latest changes from origin/main (quietly)
    # info_print("Checking for script updates...") # Made less verbose
    _, stderr, retcode = run_git_command(["fetch", "origin", "main", "--quiet"])
    if retcode != 0:
        # warn_print(f"Failed to fetch updates from remote: {stderr}. Skipping update check.")
        return

    # 4. Get local and remote commit hashes
    local_hash, stderr, retcode_local = run_git_command(["rev-parse", "HEAD"])
    remote_hash, stderr, retcode_remote = run_git_command(["rev-parse", "origin/main"])

    if retcode_local != 0 or retcode_remote != 0:
        # warn_print("Could not determine local or remote commit hash. Skipping update check.")
        return

    if local_hash == remote_hash:
        return

    # 5. Check if local commit is an ancestor of the remote commit
    _, _, retcode_ancestor = run_git_command(["merge-base", "--is-ancestor", local_hash, remote_hash])

    if retcode_ancestor == 0:
        warn_print(f"Your clippy script is behind the main branch ({CLIPPY_REPO_URL}).")
        warn_print(f"Consider updating by running: {color_text('git pull origin main', CYAN)} from the script directory.")


# --- Provider Configuration ---

HeaderFactory = Callable[[str], Dict[str, str]]
PayloadFactory = Callable[[str, List[Dict[str, str]], Optional[int], float], Dict[str, Any]]
ResponseParser = Callable[[Dict[str, Any]], Optional[str]]

class ProviderConfig:
    """Holds configuration and logic for a specific API provider type."""
    def __init__(self, base_url: str, header_factory: HeaderFactory, payload_factory: PayloadFactory, response_parser: ResponseParser):
        self.base_url = base_url
        self.header_factory = header_factory
        self.payload_factory = payload_factory
        self.response_parser = response_parser

# --- Provider Specific Implementations ---

def _openai_headers(api_key: str) -> Dict[str, str]:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

def _openai_payload(model: str, messages: List[Dict[str, str]], max_tokens: Optional[int], temperature: float) -> Dict[str, Any]:
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens is not None: payload["max_tokens"] = max_tokens
    return payload

def _openai_parser(response: Dict[str, Any]) -> Optional[str]:
    try:
        if "error" in response and isinstance(response["error"], dict):
            raise ValueError(f"API Error: {response['error'].get('message', 'Unknown OpenAI API Error')}")
        elif "error" in response:
            raise ValueError(f"API Error: {response['error']}")
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content")
        if content is None: content = choice.get("text") # Added for compatibility with older/other OpenAI-like APIs
        return content
    except (IndexError, KeyError, AttributeError, TypeError) as e:
        raise ValueError(f"Could not parse API response structure: {e}. Response: {response}") from e

def _anthropic_headers(api_key: str) -> Dict[str, str]:
    return {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}

def _anthropic_payload(model: str, messages: List[Dict[str, str]], max_tokens: Optional[int], temperature: float) -> Dict[str, Any]:
    system_prompt = next((msg["content"] for msg in messages if msg["role"] == "system"), None)
    # Filter messages: start with user, alternate user/assistant
    user_messages = [msg for msg in messages if msg["role"] in ("user", "assistant")]
    while user_messages and user_messages[0]["role"] == "assistant": user_messages.pop(0) # Ensure starts with user
    valid_messages = []
    last_role = None
    for msg in user_messages:
        if msg["role"] != last_role:
            valid_messages.append(msg)
            last_role = msg["role"]
    # Handle edge case: only system prompt provided
    if not valid_messages and system_prompt:
        warn_print("Only system prompt provided; adding empty user message for Anthropic.")
        valid_messages.append({"role": "user", "content": "..."})
    elif not valid_messages:
        raise ValueError("No valid user messages found for Anthropic payload")
    payload = {"model": model, "max_tokens": max_tokens or 1024, "messages": valid_messages, "temperature": temperature}
    if system_prompt: payload["system"] = system_prompt
    return payload

def _anthropic_parser(response: Dict[str, Any]) -> Optional[str]:
    try:
        if response.get("type") == "error":
            raise ValueError(f"Anthropic API Error: {response.get('error', {}).get('message', 'Unknown Anthropic Error')}")
        content_blocks = response.get("content", [])
        if not content_blocks: return None
        full_text = "".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")
        return full_text if full_text else None
    except (IndexError, KeyError, AttributeError, TypeError) as e:
        raise ValueError(f"Could not parse Anthropic response structure: {e}. Response: {response}") from e

# --- Provider Registry ---
PROVIDER_TYPES = {
    "openai": ProviderConfig("https://api.openai.com/v1/chat/completions", _openai_headers, _openai_payload, _openai_parser),
    "google": ProviderConfig("https://generativelanguage.googleapis.com/v1beta/models", _openai_headers, _openai_payload, _openai_parser), # Corrected base URL and assuming OpenAI-compatible for now
    "anthropic": ProviderConfig("https://api.anthropic.com/v1/messages", _anthropic_headers, _anthropic_payload, _anthropic_parser),
}
MODEL_PREFIX_TO_PROVIDER = {"gpt-": "openai", "gemini-": "google", "claude-": "anthropic"}
DEFAULT_PROVIDER = "openai"

def get_provider_type_for_model(model_name: str) -> str:
    for prefix, provider_key in MODEL_PREFIX_TO_PROVIDER.items():
        if model_name.startswith(prefix): return provider_key
    warn_print(f"Unknown model prefix for '{model_name}'. Falling back to provider type: '{DEFAULT_PROVIDER}'.")
    return DEFAULT_PROVIDER

# --- Configuration ---
def load_config() -> Dict[str, Any]:
    """Loads configuration, ensuring defaults for models, default_model, and log_enabled."""
    default_config = {"models": {}, "default_model": None, "log_enabled": True} # Log enabled by default
    if not os.path.exists(CONFIG_FILE):
        return default_config
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Ensure essential keys exist with defaults
            config.setdefault("models", {})
            config.setdefault("default_model", None)
            config.setdefault("log_enabled", True) # Ensure log setting exists
            return config
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        warn_print(f"Could not load config file ({CONFIG_FILE}): {e}. Using default configuration.")
        return default_config

def save_config(config: Dict[str, Any]) -> bool:
    """Saves configuration to the config file. Returns True on success."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except OSError as e:
        error_print(f"Could not save config file ({CONFIG_FILE}): {e}")
        return False

# --- API Client ---
class ApiClient:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()

    def make_request(self, url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            if not response.content: raise ValueError("API returned an empty response.")
            try: return response.json()
            except json.JSONDecodeError as json_err:
                raise ValueError(f"API returned non-JSON response (Status: {response.status_code}): {response.text[:1000]}") from json_err
        except requests.exceptions.Timeout as e: raise TimeoutError(f"Request timed out after {timeout} seconds.") from e
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error: {e.response.status_code} {e.response.reason}"
            try:
                error_data = e.response.json()
                details = error_data.get('error', {}).get('message') or error_data.get('detail') or str(error_data)
                error_msg += f" - {details}"
            except json.JSONDecodeError: error_msg += f" - {e.response.text[:500]}"
            raise ConnectionError(error_msg) from e
        except requests.exceptions.RequestException as e: raise ConnectionError(f"Network or request setup error: {e}") from e
        except Exception as e: raise RuntimeError(f"An unexpected error occurred during the API request: {e}") from e

# --- Core Logic ---
def get_default_system_prompt() -> str:
    try: os_info = f"OS: {platform.system()} {platform.release()} ({platform.machine()})"
    except Exception: os_info = "OS: (Could not determine)"
    return textwrap.dedent(f"""
        You are a helpful command-line assistant called Clippy.
        Provide concise, accurate, and well-formatted responses suitable for a terminal.

        Guidelines:
        - **Brevity:** Be brief and to the point. Avoid unnecessary conversation.
        - **Formatting:** Use simple Markdown (bold `**`, lists `-`/`*`/`1.`, code blocks ```).
        - **Readability:** Keep lines reasonably short for terminal display.
        - **Clarity:** Focus on answering the request directly.
        - **Environment:** You are running in a terminal environment. {os_info}.

        Aim for efficiency and clarity in your output.
    """).strip()

# --- Logging --- New Section ---

def save_log_entry(prompt: str, model_name: str, provider_type: str, response: str):
    """Saves a single interaction log entry."""
    try:
        os.makedirs(LOG_HISTORY_DIR, exist_ok=True)
        timestamp = int(time.time())
        log_filename = os.path.join(LOG_HISTORY_DIR, f"{timestamp}.log")
        log_data = {
            "timestamp": timestamp,
            "prompt": prompt,
            "model_name": model_name,
            "provider_type": provider_type,
            "response": response,
        }
        with open(log_filename, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        error_print(f"Failed to save log entry: {e}")
    except Exception as e:
        error_print(f"An unexpected error occurred while saving log: {e}")

def _get_sorted_log_files() -> List[str]:
    """Returns a list of log file paths, sorted oldest to newest by filename (timestamp)."""
    try:
        if not os.path.isdir(LOG_HISTORY_DIR):
            return []
        log_files = [f for f in os.listdir(LOG_HISTORY_DIR) if f.endswith('.log')]
        # Sort numerically based on the timestamp in the filename
        log_files.sort(key=lambda x: int(x.split('.')[0]))
        return [os.path.join(LOG_HISTORY_DIR, f) for f in log_files]
    except OSError as e:
        error_print(f"Could not list log files in {LOG_HISTORY_DIR}: {e}")
        return []
    except ValueError:
        error_print(f"Found non-numeric log filename in {LOG_HISTORY_DIR}. Please clean up.")
        return []

# --- Ask AI Function (Modified for Logging) ---

def ask_gemini(prompt: str, model_name: str, api_key: str, system_prompt: str, config: Dict[str, Any]) -> Optional[str]:
    try:
        from google import genai
    except ImportError:
        error_print("Google genai client not found. Please install the google-genai package with 'pip install google-genai'.")
        return None

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={
            'system_instruction': system_prompt,
        }
    )
    return response.text

def ask_ai(prompt: str, model_name: str, api_key: str, provider_type: str, system_prompt: str, config: Dict[str, Any], raw: bool = False) -> Optional[str]:
    """Sends the prompt, returns the response, and logs if enabled."""
    if not raw: # Conditionally print info
        info_print(f"Querying model '{color_text(model_name, CYAN)}' ({provider_type})...")

    provider = PROVIDER_TYPES.get(provider_type)
    if not provider:
        error_print(f"Provider type '{provider_type}' is not configured.")
        return None

    if provider_type == "google":
        return ask_gemini(prompt, model_name, api_key, system_prompt, config)

    client = ApiClient()
    messages: List[Dict[str, str]] = []
    effective_system_prompt = system_prompt or get_default_system_prompt()
    if effective_system_prompt: messages.append({"role": "system", "content": effective_system_prompt.strip()})
    messages.append({"role": "user", "content": prompt.strip()})

    try:
        headers = provider.header_factory(api_key)
        payload = provider.payload_factory(model_name, messages, None, 0.7)
        response_data = client.make_request(provider.base_url, headers, payload)
        parsed_response = provider.response_parser(response_data)
        return parsed_response

    except (ValueError, ConnectionError, TimeoutError, RuntimeError) as e:
        error_print(f"API interaction failed: {e}")
        return None
    except Exception as e:
        error_print(f"An unexpected error occurred during AI request: {e}")
        return None

# --- Output Formatting ---

def format_terminal_output(text: str) -> str:
    if not sys.stdout.isatty(): return text
    lines = text.splitlines()
    formatted_lines = []
    in_code_block = False
    import re # Keep import local to function
    for line in lines:
        stripped_line = line.strip()
        # Handle code block fences
        if stripped_line.startswith("```"):
            in_code_block = not in_code_block
            formatted_lines.append(line) # Keep backticks
        elif in_code_block:
            formatted_lines.append(color_text(line, CYAN)) # Color code block content
        else:
            # Apply bold formatting using **...**
            formatted_line = re.sub(r'\*\*(.*?)\*\*', lambda m: color_text(m.group(1), BOLD), line)
            formatted_lines.append(formatted_line)
    return "\n".join(formatted_lines)


# --- Command Functions ---

def set_model_cmd(args: argparse.Namespace, config: Dict[str, Any]) -> bool:
    try: model_name, api_key = args.model_api.split(":", 1)
    except ValueError:
        error_print("Invalid format. Use <model_name>:<api_key>")
        return False
    model_name, api_key = model_name.strip(), api_key.strip()
    if not model_name or not api_key:
        error_print("Both model name and API key are required.")
        return False

    provider_type = get_provider_type_for_model(model_name)
    config['models'][model_name] = {'api_key': api_key, 'provider_type': provider_type}
    info_print(f"Model '{color_text(model_name, CYAN)}' (type: {provider_type}) configured.")
    if args.default or len(config['models']) == 1:
        config['default_model'] = model_name
        info_print(f"Model '{color_text(model_name, CYAN)}' set as default.")
    return save_config(config)

def _assemble_prompt(prompt_args: List[str]) -> str:
    stdin_content = ""
    if not sys.stdin.isatty(): stdin_content = sys.stdin.read().strip()
    full_prompt = " ".join(prompt_args).strip()
    if stdin_content: full_prompt = (full_prompt + "\n\n" + stdin_content) if full_prompt else stdin_content
    return full_prompt.strip()

def ask_cmd(args: argparse.Namespace, config: Dict[str, Any]) -> bool:
    if not config['models']:
        error_print(
            "No models configured. Run `clippy set_model"
            "<model_name>:<api_key>` first, e.g: "
            "clippy set_model gemini-2.5-pro:<api_key>")
        return False
    model_name = args.model or config.get('default_model')
    if not model_name:
        error_print("No model specified and no default model set.")
        info_print("Specify a model with --model or run 'clippy set_default <model_name>'.")
        list_models_cmd(args, config)
        return False
    model_config = config['models'].get(model_name)
    if not model_config:
        error_print(f"Model '{model_name}' not found. Available: {', '.join(sorted(config['models'].keys()))}")
        return False

    api_key = model_config.get('api_key')
    provider_type = model_config.get('provider_type')
    if not api_key:
        error_print(f"API key for model '{model_name}' is missing.")
        return False
    if not provider_type:
        warn_print(f"Provider type for model '{model_name}' missing. Determining from prefix.")
        provider_type = get_provider_type_for_model(model_name)

    prompt = _assemble_prompt(args.prompt)
    if not prompt:
        # Allow empty prompt if stdin might be coming (though _assemble handles this)
        # Let the AI handle an empty prompt if it gets that far
        pass
        # error_print("Prompt cannot be empty. Provide text as arguments or pipe via stdin.")
        # return False

    system_prompt = get_default_system_prompt()
    # Pass config to ask_ai so it can check and raw flag
    ai_response = ask_ai(prompt, model_name, api_key, provider_type, system_prompt=system_prompt, config=config, raw=args.raw)

    if config["log_enabled"] == True:
        save_log_entry(prompt, model_name, provider_type, ai_response)

    if ai_response is not None:
        if args.raw:
            print(ai_response.strip())
        else:
            formatted_response = format_terminal_output(ai_response.strip())
            print("\n" + color_text("AI Response:", BOLD) + "\n")
            print(formatted_response)
        return True
    else:
        # Error already printed by ask_ai or sub-functions
        return False # Indicate failure

def list_models_cmd(args: argparse.Namespace, config: Dict[str, Any]) -> bool:
    models = config.get('models', {})
    default_model = config.get('default_model')
    if not models:
        info_print("No models configured. Use 'clippy set_model <model_name>:<api_key>' to add one.")
        return True
    info_print("\n" + color_text("Configured Models:", BOLD))
    for name in sorted(models.keys()):
        provider_type = config['models'][name].get('provider_type', get_provider_type_for_model(name))
        prefix = color_text("* ", GREEN) if name == default_model else "  "
        info_print(f"{prefix}{color_text(name, CYAN)} ({provider_type})")
    if default_model: info_print(f"\n({color_text('*', GREEN)} indicates the default model)")
    else: info_print("\nNo default model set. Use 'clippy set_default <model_name>'.")
    return True

def set_default_cmd(args: argparse.Namespace, config: Dict[str, Any]) -> bool:
    model_name = args.model.strip()
    if not config.get('models'):
        error_print("No models configured yet.")
        return False
    if model_name not in config['models']:
        error_print(f"Model '{model_name}' not found. Available: {', '.join(sorted(config['models'].keys()))}")
        return False
    config['default_model'] = model_name
    if save_config(config):
        success_print(f"Default model set to '{color_text(model_name, CYAN)}'.")
        return True
    else: return False

def remove_model_cmd(args: argparse.Namespace, config: Dict[str, Any]) -> bool:
    model_name = args.model.strip()
    if not config.get('models'):
        error_print("No models configured yet.")
        return True # Nothing to remove
    if model_name not in config['models']:
        error_print(f"Model '{color_text(model_name, CYAN)}' not found.")
        list_models_cmd(args, config)
        return False
    del config['models'][model_name]
    info_print(f"Removed model '{color_text(model_name, CYAN)}'.")
    if config.get('default_model') == model_name:
        config['default_model'] = None
        warn_print(f"Removed model was the default. No default model is set now.")
        if config['models']: info_print("Set a new default using 'clippy set_default <model_name>'.")
    if save_config(config):
        success_print(f"Configuration updated.")
        return True
    else: return False

# --- Log Command Functions --- New Section ---

def show_log_status_cmd(args: argparse.Namespace, config: Dict[str, Any]) -> bool:
    """Shows the log status, basic help, and latest entry details."""
    info_print(f"\n{color_text('Log Command Status & Help:', BOLD)}")
    info_print("Manages interaction logs stored in:", LOG_HISTORY_DIR)
    info_print("\nSub-commands:")
    info_print(f"  {color_text('on', CYAN)}      Enable logging (currently default)")
    info_print(f"  {color_text('off', CYAN)}     Disable logging")
    info_print(f"  {color_text('show [N]', CYAN)} Show the latest N log sessions (default N=1)")
    info_print(f"  {color_text('clear [N]', CYAN)} Clear the oldest N logs, or keep latest N if N is negative")

    log_enabled = config.get("log_enabled", True) # Assume enabled if not set
    status_text = color_text("enabled", GREEN) if log_enabled else color_text("disabled", RED)
    info_print(f"\nCurrent status: Logging is {status_text}.")

    log_files = _get_sorted_log_files()
    total_logs = len(log_files)

    if total_logs == 0:
        info_print("History: No log sessions found.")
    else:
        info_print(f"History: Contains {color_text(str(total_logs), CYAN)} log session(s).")
        num_to_show = 3
        latest_files = log_files[-num_to_show:]
        latest_files.reverse() # Show newest first

        if latest_files:
            info_print(f"\nLatest {min(num_to_show, total_logs)} log session timestamp(s):")
            for filepath in latest_files:
                try:
                    filename = os.path.basename(filepath)
                    timestamp_str = filename.split('.')[0]
                    ts = int(timestamp_str)
                    dt_object = datetime.fromtimestamp(ts)
                    formatted_time = dt_object.strftime('%a %b %d - %H:%M:%S %Y') # e.g., Wed Apr 09 - 18:00:58 2024
                    info_print(f"  - {formatted_time}")
                except (ValueError, IndexError):
                    error_print(f"  - Could not parse timestamp from filename: {filename}")
                except Exception as e:
                     error_print(f"  - Error processing log file {filename}: {e}")

    return True # This command always 'succeeds' in showing info

def log_on_cmd(args: argparse.Namespace, config: Dict[str, Any]) -> bool:
    """Enables logging."""
    config["log_enabled"] = True
    if save_config(config):
        success_print("Logging is enabled.")
        return True
    else:
        error_print("Failed to update config to enable logging.")
        return False

def log_off_cmd(args: argparse.Namespace, config: Dict[str, Any]) -> bool:
    """Disables logging."""
    config["log_enabled"] = False
    if save_config(config):
        success_print("Logging is disabled.")
        return True
    else:
        error_print("Failed to update config to disable logging.")
        return False

def log_show_cmd(args: argparse.Namespace, config: Dict[str, Any]) -> bool:
    """Shows the N latest log entries."""
    count = args.count
    if count <= 0:
        error_print("Number of logs to show must be positive.")
        return False

    log_files = _get_sorted_log_files()
    if not log_files:
        info_print("No log history found.")
        return True

    # Get the latest N files (list is sorted oldest to newest)
    files_to_show = log_files[-count:]
    files_to_show.reverse() # Show latest first

    info_print(f"Showing the latest {min(count, len(files_to_show))} log session(s):")

    display_count = 0
    for i, filepath in enumerate(files_to_show):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                log_data = json.load(f)

            ts = log_data.get("timestamp", 0)
            dt_object = datetime.fromtimestamp(ts)
            formatted_time = dt_object.strftime('%a %b %d - %H:%M:%S %Y') # e.g., Wed Apr 09 - 18:00:58 2024
            model = log_data.get('model_name', 'N/A')
            provider = log_data.get('provider_type', 'N/A')
            prompt = log_data.get('prompt', '<empty>')
            response = log_data.get('response', '<empty>')

            print(f"\n{color_text(f'==== Session {i+1} of {len(files_to_show)} ({formatted_time}) ====', MAGENTA + BOLD)}")
            print(f"{color_text('Model:', BOLD)} '{color_text(model, CYAN)}' ({provider})")
            print(f"{color_text('Prompt:', BOLD)}\n{textwrap.indent(prompt, '  ')}")
            print(f"{color_text('Response:', BOLD)}\n{textwrap.indent(response.strip(), '  ')}")
            display_count += 1

        except FileNotFoundError:
            error_print(f"Log file not found (might have been deleted): {os.path.basename(filepath)}")
        except json.JSONDecodeError:
            error_print(f"Could not parse log file (invalid JSON): {os.path.basename(filepath)}")
        except Exception as e:
            error_print(f"Error reading log file {os.path.basename(filepath)}: {e}")

    return display_count > 0 # Return True if at least one log was shown successfully

def log_clear_cmd(args: argparse.Namespace, config: Dict[str, Any]) -> bool:
    """Clears log entries."""
    count = args.count
    log_files = _get_sorted_log_files()
    total_logs = len(log_files)

    if total_logs == 0:
        info_print("No log history found to clear.")
        return True

    files_to_delete = []
    keep_count = 0

    if count > 0: # Clear N oldest
        num_to_delete = min(count, total_logs)
        files_to_delete = log_files[:num_to_delete]
        action_desc = f"{num_to_delete} oldest log(s)"
    elif count < 0: # Keep N latest (-N means keep N)
        keep_count = -count
        if keep_count >= total_logs:
             info_print(f"Keeping all {total_logs} log(s). Nothing to clear.")
             return True
        num_to_delete = total_logs - keep_count
        files_to_delete = log_files[:num_to_delete]
        action_desc = f"{num_to_delete} log(s) (keeping {keep_count} latest)"
    else: # count == 0
         error_print("Clear count cannot be zero. Use positive N to clear oldest, negative N to keep latest.")
         return False

    if not files_to_delete:
        info_print("No logs selected for deletion based on the criteria.")
        return True

    info_print(f"Preparing to delete {action_desc}...")
    deleted_count = 0
    failed_count = 0
    for filepath in files_to_delete:
        try:
            os.remove(filepath)
            deleted_count += 1
        except OSError as e:
            error_print(f"Failed to delete log file {os.path.basename(filepath)}: {e}")
            failed_count += 1

    if failed_count == 0:
        success_print(f"Successfully cleared {deleted_count} log file(s).")
    else:
        warn_print(f"Cleared {deleted_count} log file(s), but failed to delete {failed_count}.")
    remaining = total_logs - deleted_count
    info_print(f"{remaining} log file(s) remain.")
    return failed_count == 0

# --- Main Execution ---

def main() -> None:
    """Parses arguments and executes the corresponding command."""
    parser = argparse.ArgumentParser(
        description="Clippy: Your AI Command-Line Assistant (Supports OpenAI, Google, Anthropic compatible APIs)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=f"Config: {CONFIG_FILE}\nLogs:   {LOG_HISTORY_DIR}"
    )
    subparsers = parser.add_subparsers(
        title='Commands', dest='command', required=False, # Make top-level command optional for default 'ask'
        help="Available actions"
    )

    # --- set_model command ---
    set_model_parser = subparsers.add_parser('set_model', help='Configure an AI model (<model_name>:<api_key>)', description='Adds/updates model: API key. Provider type inferred from name.')
    set_model_parser.add_argument(
        'model_api',
        help='Model name and API key string, e.g.:"gpt-4o:sk-...", "gemini-2.5-pro-preview-06-05:A92f..."')
    set_model_parser.add_argument('--default', '-d', action='store_true', help='Set this model as default.')
    set_model_parser.set_defaults(func=set_model_cmd)

    # --- ask command ---
    ask_parser = subparsers.add_parser('ask', help='Ask the AI (default command)', description='Sends prompt (args + stdin) to the AI.')
    ask_parser.add_argument('prompt', nargs='*', help='Prompt text. Reads from stdin if piped.')
    ask_parser.add_argument('--model', '-m', help='Model name to use (overrides default).')
    ask_parser.add_argument('--raw', action='store_true', help='Output raw response without formatting.', default=False)
    ask_parser.set_defaults(func=ask_cmd)

    # --- list command ---
    list_parser = subparsers.add_parser('list', help='List configured models', aliases=['ls'])
    list_parser.set_defaults(func=list_models_cmd)

    # --- set_default command ---
    set_default_parser = subparsers.add_parser('set_default', help='Set the default model')
    set_default_parser.add_argument('model', help='Name of the configured model to set as default.')
    set_default_parser.set_defaults(func=set_default_cmd)

    # --- remove_model command ---
    remove_parser = subparsers.add_parser('remove_model', help='Remove a configured model', aliases=['rm'])
    remove_parser.add_argument('model', help='Name of the model to remove.')
    remove_parser.set_defaults(func=remove_model_cmd)

    # --- log command --- New Subparser Group ---
    log_parser = subparsers.add_parser('log', help='Manage interaction logs')
    # Make log_action optional: running 'clippy log' will show status/help
    log_subparsers = log_parser.add_subparsers(title='Log Actions', dest='log_action', required=False)

    # Add placeholder default function for 'log' command itself
    log_parser.set_defaults(func=show_log_status_cmd) # Execute status cmd if no sub-command given

    log_on_parser = log_subparsers.add_parser('on', help='Enable logging (default)')
    log_on_parser.set_defaults(func=log_on_cmd) # Overwrite func for this specific sub-command

    log_off_parser = log_subparsers.add_parser('off', help='Disable logging')
    log_off_parser.set_defaults(func=log_off_cmd) # Overwrite func

    log_show_parser = log_subparsers.add_parser('show', help='Show latest N log sessions')
    log_show_parser.add_argument('count', type=int, nargs='?', default=1, help='Number of latest sessions to show (default: 1)')
    log_show_parser.set_defaults(func=log_show_cmd) # Overwrite func

    log_clear_parser = log_subparsers.add_parser('clear', help='Clear log sessions')
    log_clear_parser.add_argument(
        'count', type=int, nargs='?', default=-10,
        help='Number of OLDEST logs to clear. Negative N means KEEP N LATEST (e.g., -10 keeps 10 latest). Default: -10'
    )
    log_clear_parser.set_defaults(func=log_clear_cmd) # Overwrite func


    # --- Check for updates ---
    try: check_for_updates()
    except Exception as e: warn_print(f"Update check failed: {e}")

    # --- Pre-process args: Default to 'ask' command ---
    argv = sys.argv[1:] # Get args excluding script name
    known_commands = {'set_model', 'ask', 'list', 'ls', 'set_default', 'remove_model', 'rm', 'log'}
    # Default to 'ask' if no args, or first arg isn't a known command or option
    if not argv or (argv[0] not in known_commands and not argv[0].startswith('-')):
         sys.argv.insert(1, 'ask')

    # --- Parse arguments ---
    args = parser.parse_args()

    # --- Load config ---
    config = load_config()
    if not config.get('models'):
        error_print("No models with API KEY configured. Note: Google P&D engineers can check out go/pd-ai-key")
    # --- Execute command ---
    success = False # Default to failure
    if hasattr(args, 'func'):
        # Handle the case where 'clippy log' is called with no subcommand
        # args.func will be show_log_status_cmd if log_action is None
        # Otherwise, it will be the specific log action function (on, off, show, clear)
        success = args.func(args, config)
    elif not args.command: # Handles case where only 'clippy' is run (after inserting 'ask')
        # Re-parse ensures args.func is set correctly for the default 'ask' command
        args = parser.parse_args(['ask'] + args.prompt) # Include any prompt args captured initially
        if hasattr(args, 'func'):
             success = args.func(args, config)
        else:
             parser.print_help() # Should not happen if 'ask' is default
             success = False
    else:
        # This case might occur if a command is recognized but no function is set
        # (e.g., if 'log' was defined without subparsers or a default func)
        # Or if an unknown command was somehow passed through pre-processing
        parser.print_help()
        success = False

    # --- Exit status ---
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
