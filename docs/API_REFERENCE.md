# Simple OpenHands API Reference

This document describes every public module exposed by the `simple_openhands` package, how they interact, and how to use them from either Python code, the bundled CLI, or the HTTP runtime. The reference is organized by layer so you can jump to the component you need to extend or integrate.

> All import paths in this guide assume `simple_openhands` is on your `PYTHONPATH`.

---

## 1. Package Metadata (`simple_openhands.__init__`)

Exports basic metadata and important paths:

| Symbol | Description |
| --- | --- |
| `__version__` | Package version (falls back to `0.1.0` when running from source). |
| `PACKAGE_DIR` | Absolute `Path` pointing to `simple_openhands/`. |
| `REPO_ROOT` | Repository root, useful for resolving fixtures and assets. |

These names are part of `__all__` and safe to import directly:

```python
from simple_openhands import __version__, REPO_ROOT
print(__version__, REPO_ROOT)
```

---

## 2. Command-Line Interface (`simple_openhands.cli`)

`oh-run` is the user-facing CLI for sending actions to a running runtime.

### Key helpers

| Function | Purpose |
| --- | --- |
| `_build_run_action(command, thought=None, blocking=None)` | Packages a bash command into the OpenHands action envelope. |
| `_build_ipython_action(code, thought=None)` | Same as above for Python/Notebook execution. |
| `_find_session_file(start: Path)` | Walks up from `start` to locate `.oh-session`. |
| `_read_session_file(path)` | Extracts `api_url` from a `.oh-session` JSON file. |
| `cmd_context(api_url, raw, timeout)` | Calls `GET /server_info` and prints either prettified JSON or raw text. |
| `main()` | Parses CLI flags, resolves the API URL (flag > `OH_API_URL` > session file), builds the action payload, calls `/execute_action`, and prints the response. |

### Usage examples

```bash
# Run a single bash command
oh-run --url http://127.0.0.1:8000 "ls -al /workspace"

# Execute Python code instead of bash
oh-run --url http://127.0.0.1:8000 --python "print('hello from runtime')"

# Inspect runtime metadata
oh-run --context --timeout 5 --url http://localhost:8000
```

Flags of note:

- `--blocking` marks the command as potentially long-running (so the server waits longer before a no-change timeout).
- `--session-file` overrides the automatic `.oh-session` walk.
- `--raw` prints the entire HTTP response (useful for debugging image URLs).

---

## 3. FastAPI Runtime (`simple_openhands.main`)

`simple_openhands.main` exposes a fully featured FastAPI app that manages command execution, filesystem actions, and runtime plugins.

### Lifespan & session management

- `lifespan(app)` initializes a `BashSession` (or `WindowsPowershellSession` on Windows) with a configurable working directory, ensures Git is usable, and kicks off asynchronous Jupyter initialization.
- `/reset` tears down the current session and starts a fresh one using the same logic as `lifespan`.

### Built-in endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Returns a simple greeting and version. |
| `GET` | `/alive` | Health check that also reports whether the shell session is ready. |
| `GET` | `/server_info` | Returns `ServerInfo` (status, version, cwd, username, resource stats). |
| `GET` | `/system/stats` | Raw system metrics from `utils.system_stats.get_system_stats()`. |
| `POST` | `/reset` | Re-initializes the shell session (Linux bash or Windows PowerShell). |
| `GET` | `/view-file?path=/abs/file` | Renders supported files (PDF/images) as HTML using `generate_file_viewer_html`. |
| `GET` | `/plugins` | Lists available plugins and whether they are initialized. |
| `POST` | `/plugins/{plugin}/initialize` | Lazily initialize VSCode or other manual plugins. |
| `GET` | `/vscode/connection_token` | Returns the OpenVSCode connection token after `VSCodePlugin` starts. |
| `GET` | `/vscode-url` | Convenience URL builder that encodes the workspace path. |
| `POST` | `/execute_action` | Primary RPC endpoint that accepts any Action envelope and returns the resulting Observation. |

### Executing actions over HTTP

`/execute_action` expects the canonical OpenHands payload:

```json
{
  "action": {
    "action": "run",
    "args": {
      "command": "python -V",
      "timeout": 120,
      "thought": "Confirm interpreter version"
    }
  }
}
```

Example request/response:

```bash
# curl example
curl -X POST http://127.0.0.1:8000/execute_action \
     -H "Content-Type: application/json" \
     -d '{"action":{"action":"run","args":{"command":"ls","blocking":false}}}'
```

Response (truncated):

```json
{
  "observation": "run",
  "content": "README.md\nsimple_openhands",
  "extras": {
    "command": "ls",
    "metadata": {
      "exit_code": 0,
      "working_dir": "/workspace"
    }
  }
}
```

Supported action types are detected by `events.serialization.event_from_dict` and dispatched to:

- `bash_session.execute` for `CmdRunAction`
- `JupyterPlugin.run` for `IPythonRunCellAction`
- Async file helpers (`read_file_action`, `write_file_action`, `edit_file_action`)

---

## 4. Event & Serialization Layer (`simple_openhands.events`)

### Action model (`events.action`)

| Class | Description |
| --- | --- |
| `Action` | Base dataclass that extends `Event`. |
| `CmdRunAction` | Executes a shell command. Key fields: `command`, `is_input`, `thought`, `blocking`, `timeout`, `hidden`. `runnable=True`. |
| `IPythonRunCellAction` | Executes Python code through the Jupyter kernel gateway. Fields: `code`, `thought`, `include_extra`, `kernel_init_code`. |
| `FileReadAction` | Reads a file (optionally range-limited) and records the implementation source. |
| `FileWriteAction` | Writes text to a file; supports partial writes via `start`/`end`. |
| `FileEditAction` | Hybrid action that can call the OpenHands ACI editor or act as an LLM-based edit (fields cover both modes). |

`ActionConfirmationStatus` tracks manual review, while `ActionSecurityRisk` is available for risk-aware runtimes.

### Observation model (`events.observation`)

| Class | Description |
| --- | --- |
| `CmdOutputObservation` | Wraps shell output plus `CmdOutputMetadata` (exit code, cwd, interpreter, prefix/suffix). |
| `IPythonRunCellObservation` | Textual + rich-media output (image URLs) for Python cells. |
| `FileReadObservation`, `FileWriteObservation`, `FileEditObservation` | Represent file operations, provide diff visualizations when possible. |
| `ErrorObservation` | Used for recoverable errors (e.g., lint failure, invalid action). |

`CmdOutputMetadata.to_ps1_prompt()` builds the special PS1 prompt injected into `BashSession` so metadata can be parsed from tmux output.

### Serialization helpers (`events.serialization.event`)

- `event_to_dict(event: Event) -> dict` converts Actions or Observations to the REST payload form.
- `event_from_dict(data: dict) -> Event` instantiates the right dataclass from JSON.

Usage:

```python
from simple_openhands.events.serialization import event_to_dict, event_from_dict
from simple_openhands.events.action import CmdRunAction

action = CmdRunAction(command="pytest", blocking=True, thought="Run unit tests")
payload = {"action": event_to_dict(action)}

# ...send payload...

observation = event_from_dict({"observation": "run", "content": "...", "extras": {...}})
```

---

## 5. Shell Execution Layers

### 5.1 Bash utilities (`simple_openhands.bash`)

| Function/Class | Description |
| --- | --- |
| `split_bash_commands(cmd: str) -> list[str]` | Uses `bashlex` to ensure only a single command is executed at once. |
| `escape_bash_special_chars(cmd: str) -> str` | Escapes characters interpreted differently by Python vs. bash. |
| `BashCommandStatus` | Enum for tracking the previous command state (`COMPLETED`, `NO_CHANGE_TIMEOUT`, etc.). |
| `BashSession` | Manages a tmux-backed bash shell with persistent history, advanced timeout handling, and PS1 metadata parsing. |

`BashSession` workflow:

```python
from simple_openhands.bash import BashSession
from simple_openhands.events.action import CmdRunAction

session = BashSession(work_dir="/workspace", username="simple_openhands")
session.initialize()
observation = session.execute(CmdRunAction(command="ls -la"))
print(observation.content)
session.close()
```

Important behaviors:

- `initialize()` creates a dedicated tmux session, configures `PS1`, and clears the pane.
- `execute()` enforces “one command at a time” by parsing the input and by tracking prompt reappearance.
- Timeout paths (`NO_CHANGE_TIMEOUT`, `HARD_TIMEOUT`) append human-readable suffixes referencing `bash_constants.TIMEOUT_MESSAGE_TEMPLATE`.
- `CmdOutputMetadata` is continuously extracted to capture final `exit_code`, `cwd`, `python interpreter`, etc.

### 5.2 Windows PowerShell (`simple_openhands.windows_bash`)

`WindowsPowershellSession` mirrors the Linux behavior using pythonnet and the .NET PowerShell SDK.

Highlights:

- Maintains a persistent runspace that keeps variables and working directory between commands.
- Supports asynchronous `Start-Job` execution with background job polling, `C-c` approximations, and metadata extraction.
- Provides detailed error messaging when the PowerShell SDK or runtime prerequisites are missing.

Usage:

```python
from simple_openhands.windows_bash import WindowsPowershellSession
from simple_openhands.events.action import CmdRunAction

session = WindowsPowershellSession(work_dir="C:\\workspace", username="Administrator")
observation = session.execute(CmdRunAction(command="Get-ChildItem"))
print(observation.content)
session.close()
```

---

## 6. Core Utilities (`simple_openhands.core`)

### Logging (`core.logger`)

- Automatically configures a package-level logger (`simple_openhands.core.logger.logger`) honoring environment variables:
  - `LOG_LEVEL`, `DEBUG`, `LOG_JSON`, `LOG_TO_FILE`, `LOG_ALL_EVENTS`.
- `SimpleOpenHandsLoggerAdapter` merges extra metadata per log call.
- `SensitiveDataFilter` redacts secrets gleaned from environment variables or common key names.
- `json_log_handler()` provides structured JSON logging without external dependencies.

Example:

```python
from simple_openhands.core.logger import logger

logger.info("Runtime ready", extra={"msg_type": "DETAIL"})
```

### Platform helpers (`core.platform`)

| Function | Description |
| --- | --- |
| `get_platform()` | Returns `"windows"`, `"linux"`, or `"unknown"`. |
| `is_windows()`, `is_linux()` | Convenience checks. |
| `get_bash_session_class()` | Returns `BashSession` or `WindowsPowershellSession` based on platform. |
| `get_platform_specific_config()` | Shell-specific defaults (paths, environment variable prefixes, etc.). |
| `check_platform_compatibility()` | Verifies required libraries (`pythonnet` on Windows, `libtmux` on Linux). |
| `get_platform_paths()` | Alias for `get_platform_specific_config()`. |

### Schemas (`core.schema`)

Two enums describe the action/observation types recognized by the runtime:

```python
from simple_openhands.core.schema import ActionType, ObservationType

ActionType.RUN          # 'run'
ObservationType.ERROR   # 'error'
```

Use these enums for type-safe comparisons or when constructing custom actions.

---

## 7. Models (`simple_openhands.models`)

`ServerInfo` is the response model for `/server_info`. Fields:

```python
class ServerInfo(BaseModel):
    status: str
    version: str
    cwd: str
    username: str | None = None
    resources: dict[str, Any] | None = None
```

---

## 8. File & System Utilities (`simple_openhands.utils`)

### `utils.system_stats.get_system_stats()`

Returns a dict containing CPU%, memory (rss/vms/percent), disk usage, and process I/O counters. Useful for embedding telemetry in API responses.

```python
from simple_openhands.utils.system_stats import get_system_stats

print(get_system_stats())
```

### `utils.system`

| Function | Description |
| --- | --- |
| `check_port_available(port)` | Tries to bind to `0.0.0.0:port` and returns `True` if possible. Logs helpful diagnostics for common `errno` cases. |
| `find_available_tcp_port(min_port=30000, max_port=39999, max_attempts=10)` | Picks a random open port in the range. |
| `display_number_matrix(number)` | Renders a blocky ASCII-art representation of a three-digit number. Handy for logging tokens or codes. |

### `utils.file.file_viewer.generate_file_viewer_html(path)`

Generates a standalone HTML document that can render PDFs and common image formats directly in the browser (powered by PDF.js). Used by `/view-file`.

### `utils.file.files`

- `resolve_path(file_path, working_directory, workspace_base, workspace_mount_path_in_sandbox)` ensures a path stays within the workspace mount.
- `read_file(...)` and `write_file(...)` implement sandbox-aware I/O with rich error observations.
- `insert_lines()` and `read_lines()` provide helpers for granular edits.

Example for sandboxed read:

```python
from simple_openhands.utils.file import files

obs = await files.read_file(
    path="src/app.py",
    workdir="/workspace",
    workspace_base="/workspace",
    workspace_mount_path_in_sandbox="/workspace",
    start=0,
    end=50,
)
print(obs.content)
```

---

## 9. Plugins (`simple_openhands.plugins`)

`simple_openhands.plugins.__all__` exports `Plugin`, `PluginRequirement`, and concrete plugin classes. `ALL_PLUGINS` maps plugin names (`jupyter`, `agent_skills`, `vscode`) to their classes for registration.

### 9.1 Agent Skills (`plugins.agent_skills`)

`AgentSkillsPlugin` itself is a lightweight container (no runtime `run` implementation). The real functionality lives in the re-exported helper modules:

- **File navigation (`file_ops`)**
  - `open_file(path, line_number=1, context_lines=100)`
  - `goto_line(line_number)`
  - `scroll_down()`, `scroll_up()`
  - `search_dir(term, dir_path='./')`
  - `search_file(term, file_path=None)`
  - `find_file(file_name, dir_path='./')`
  - Helpers `_lint_file`, `_print_window`, etc. enforce consistent output for the agent.

- **File readers (`file_reader`)**
  - `parse_pdf`, `parse_docx`, `parse_latex`, `parse_pptx`
  - Conditional exports `parse_audio`, `parse_video`, `parse_image` when OpenAI credentials are available.

- **Repository operations (`repo_ops`)**
  - `explore_tree_structure`, `get_entity_contents`, `search_code_snippets` (sourced from the lightweight ACI implementation).

- **Editing utilities**
  - `file_editor(file_path, start, end, content)` replaces 1-based line ranges and performs syntax linting via `DefaultLinter`.
  - `DefaultLinter.lint(file_path)` compiles Python files to report syntax errors (line, column, message).

All public functions are collected in `AgentSkillsRequirement.documentation`, so runtime UIs can display human-readable tooltips.

Example of a skill call:

```python
from simple_openhands.plugins.agent_skills import open_file, search_dir

open_file("/workspace/simple_openhands/main.py", line_number=200)
search_dir("TODO", dir_path="/workspace")
```

### 9.2 Jupyter Plugin (`plugins.jupyter`)

`JupyterPlugin` provides notebook-style execution via Jupyter Kernel Gateway.

- `initialize(username, kernel_id='simple_openhands-default')` starts the gateway on `JUPYTER_PORT` (default `8001`), waits for “server ready” output, and validates the kernel by running `import sys; print(sys.executable)`.
- `run(action: IPythonRunCellAction)` (via `_run`) sends code to the kernel and returns an `IPythonRunCellObservation` containing both text and inline image URLs (data URIs).
- Async helper `_init_jupyter_async` in `main.py` starts the plugin without blocking the FastAPI startup sequence.

Usage (outside FastAPI):

```python
import asyncio
from simple_openhands.plugins.jupyter import JupyterPlugin
from simple_openhands.events.action import IPythonRunCellAction

async def demo():
    plugin = JupyterPlugin()
    await plugin.initialize(username="simple_openhands")
    obs = await plugin.run(IPythonRunCellAction(code="print(2 + 2)"))
    print(obs.content)  # => 4

asyncio.run(demo())
```

`plugins/jupyter/execute_server.py` contains the low-level `JupyterKernel` client used internally. It manages WebSocket channels, heartbeats, timeouts, and structured output parsing.

### 9.3 VSCode Plugin (`plugins.vscode`)

`VSCodePlugin` launches OpenVSCode Server inside the workspace, making it accessible via a secure token.

- `initialize(username, runtime_id=None)` validates platform support, copies default settings into `<workspace>/.vscode/settings.json`, chooses an available port (`VSCODE_PORT` env var), and spawns OpenVSCode Server.
- Exposes:
  - `vscode_port`
  - `vscode_connection_token`
- Endpoints in `main.py` (`/vscode/connection_token`, `/vscode-url`) read these fields and provide client-friendly responses.

Example initialization from Python:

```python
import asyncio
from simple_openhands.plugins.vscode import VSCodePlugin

async def boot_vscode():
    plugin = VSCodePlugin()
    await plugin.initialize(username="simple_openhands")
    print(plugin.vscode_connection_token, plugin.vscode_port)

asyncio.run(boot_vscode())
```

---

## 10. Putting It All Together

Below is a minimal end-to-end interaction that exercises most of the APIs:

```python
import asyncio
import httpx
from simple_openhands.events.action import CmdRunAction
from simple_openhands.events.serialization import event_to_dict

# 1. Launch the FastAPI runtime (python -m simple_openhands.main) in another process.

# 2. Use the CLI or direct HTTP to run a command
action = CmdRunAction(command="python -V", blocking=True, thought="Check interpreter")
payload = {"action": event_to_dict(action)}

resp = httpx.post("http://127.0.0.1:8000/execute_action", json=payload, timeout=30)
resp.raise_for_status()
print(resp.json()["content"])

# 3. Trigger a Python cell using the Jupyter plugin
async def run_python():
    action = {"action": "run_ipython", "args": {"code": "print('hi from ipy')" }}
    resp = httpx.post("http://127.0.0.1:8000/execute_action", json={"action": action}, timeout=30)
    print(resp.json()["content"])

asyncio.run(run_python())
```

For filesystem manipulation, construct `FileReadAction` or `FileEditAction` objects and send them through the same endpoint. The runtime will respond with the corresponding observation types and detailed metadata highlighted in this reference.

---

## 11. Reference Checklist

Use this section to ensure you didn’t miss any publicly supported element:

- [x] Package metadata (`__version__`, `PACKAGE_DIR`, `REPO_ROOT`)
- [x] CLI entrypoint and helper functions
- [x] FastAPI runtime endpoints and plugin lifecycle
- [x] Action/Observation dataclasses and serialization helpers
- [x] Bash and PowerShell session implementations
- [x] Core utilities: logging, platform detection, schema enums
- [x] Models (`ServerInfo`)
- [x] Utilities: system stats, port selection, file sandbox, HTML viewers
- [x] Plugins: AgentSkills (file ops, readers, repo ops, editor), Jupyter, VSCode

With this document, you can safely build clients, extend runtime behaviors, or add new plugins without diving through the source first.
