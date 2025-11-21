import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests


def _read_env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name)
    return val if val else default


def _build_run_action(command: str, thought: str | None = None, blocking: bool | None = None) -> Dict[str, Any]:
    args: Dict[str, Any] = {"command": command}
    if thought:
        args["thought"] = thought
    if blocking is not None:
        args["blocking"] = blocking
    return {"action": {"action": "run", "args": args}}


def _print_error(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def _shell_single_quote(s: str) -> str:
    """Safely single-quote a string for POSIX shells.

    Replaces ' with '\'' pattern to avoid breaking out of quotes.
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _build_curl_command(api_url: str, api_key: Optional[str], payload: Dict[str, Any]) -> str:
    endpoint = api_url.rstrip("/") + "/execute_action"
    json_body = json.dumps({"action": payload["action"]}, ensure_ascii=False)
    parts = [
        "curl",
        "-s",
        "-X",
        "POST",
        _shell_single_quote(endpoint),
        "-H",
        _shell_single_quote("Content-Type: application/json"),
    ]
    if api_key:
        parts.extend(["-H", _shell_single_quote(f"X-Session-API-Key: {api_key}")])
    parts.extend(["-d", _shell_single_quote(json_body)])
    return " ".join(parts)


def _read_session_file(path: Path) -> Tuple[Optional[str], Optional[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("api_url"), data.get("api_key")
    except Exception:
        return None, None


def _find_session_file(start: Path) -> Optional[Path]:
    current = start
    root = current.anchor or "/"
    while True:
        candidate = current / ".oh-session"
        if candidate.exists() and candidate.is_file():
            return candidate
        if str(current) == root:
            return None
        current = current.parent


def cmd_context(api_url: str, api_key: Optional[str], raw: bool, timeout: float) -> int:
    url = api_url.rstrip("/") + "/server_info"
    headers = {}
    if api_key:
        headers["X-Session-API-Key"] = api_key
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if raw:
            print(resp.text)
            return 0
        resp.raise_for_status()
        data = resp.json()
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    except requests.RequestException as e:
        _print_error(f"oh-run: failed to get context: {e}")
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(prog="oh-run", description="Execute a bash command via Simple OpenHands runtime HTTP API")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute (single command; use shell operators to chain)")
    parser.add_argument("--url", dest="url", default=None, help="Runtime API base URL (e.g. http://127.0.0.1:8000)")
    parser.add_argument("--api-key", dest="api_key", default=None, help="Optional session API key (sent as X-Session-API-Key)")
    parser.add_argument("--timeout", dest="timeout", type=float, default=600.0, help="Client HTTP timeout in seconds (default: 600)")
    parser.add_argument("--thought", dest="thought", default=None, help="Optional rationale to attach to the action")
    parser.add_argument("--blocking", dest="blocking", action="store_true", help="Mark command as blocking (server may enforce timeouts)")
    parser.add_argument("--raw", dest="raw", action="store_true", help="Print raw JSON response instead of extracted content")
    parser.add_argument("--context", dest="context", action="store_true", help="Print runtime context (server_info) instead of executing a command")
    parser.add_argument("--emit-curl", dest="emit_curl", action="store_true", help="Print the equivalent curl command")
    parser.add_argument("--via-curl", dest="via_curl", action="store_true", help="Execute the request via curl subprocess instead of HTTP client")
    parser.add_argument("--session-file", dest="session_file", default=None, help="Path to a .oh-session JSON (overridden by --url/--api-key)")

    args = parser.parse_args()

    # Resolve routing (flags > env > session file)
    api_url = args.url or _read_env("OH_API_URL")
    api_key = args.api_key or _read_env("OH_API_KEY")

    if not api_url:
        # Try explicit session file
        session_path: Optional[Path] = None
        if args.session_file:
            session_path = Path(args.session_file)
        else:
            # Try env OH_SESSION_FILE, otherwise walk up for .oh-session
            env_sf = _read_env("OH_SESSION_FILE")
            if env_sf:
                session_path = Path(env_sf)
            else:
                session_path = _find_session_file(Path.cwd())
        if session_path and session_path.exists():
            sf_url, sf_key = _read_session_file(session_path)
            api_url = api_url or sf_url
            api_key = api_key or sf_key

    if not api_url:
        _print_error("oh-run: OH_API_URL is not set and --url was not provided. Set OH_API_URL or pass --url.")
        return 2

    if args.context:
        return cmd_context(api_url, api_key, raw=args.raw, timeout=args.timeout)

    if not args.command:
        _print_error("oh-run: no command provided. Example: oh-run \"ls -la\"")
        return 2

    command_str = " ".join(args.command).strip()
    payload = _build_run_action(command=command_str, thought=args.thought, blocking=args.blocking)

    # Optionally emit or execute via curl
    if args.emit_curl or args.via_curl:
        curl_cmd = _build_curl_command(api_url, api_key, payload)
        if args.emit_curl and not args.via_curl:
            print(curl_cmd)
            return 0
        # Execute via curl (POSIX shells only)
        if platform.system().lower().startswith("win"):
            _print_error("oh-run: --via-curl is not supported on Windows. Use default HTTP mode or WSL.")
            return 2
        try:
            proc = subprocess.run(["bash", "-lc", curl_cmd], capture_output=True, text=True, timeout=args.timeout)
            resp_text = proc.stdout
            if args.raw:
                print(resp_text)
                return 0 if proc.returncode == 0 else 1
            try:
                data = json.loads(resp_text)
            except ValueError:
                print(resp_text)
                return 1 if proc.returncode != 0 else 0
            content = data.get("content")
            if isinstance(content, str):
                # Format output to match CompileBench's format so it can be directly returned to LLM
                if len(content.strip()) == 0:
                    content = "[empty output]"
                print(f"Command ran and generated the following output:\n```\n{content}\n```")
                return 0 if proc.returncode == 0 else 1
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0 if proc.returncode == 0 else 1
        except subprocess.SubprocessError as e:
            _print_error(f"oh-run: curl execution failed: {e}")
            return 2

    # Default: direct HTTP request (robust, cross-platform)
    url = api_url.rstrip("/") + "/execute_action"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Session-API-Key"] = api_key

    try:
        resp = requests.post(url, headers=headers, json={"action": payload["action"]}, timeout=args.timeout)
    except requests.RequestException as e:
        _print_error(f"oh-run: request failed: {e}")
        return 2

    # Best-effort output handling
    text = resp.text
    if args.raw:
        print(text)
        return 0 if resp.ok else 1

    try:
        data = resp.json()
    except ValueError:
        # Not JSON (server error path) — print as-is
        print(text)
        return 1 if not resp.ok else 0

    # Simple OpenHands observation format: {"observation": "run", "content": "...", "extras": {...}}
    content = data.get("content")
    if isinstance(content, str):
        # Format output to match CompileBench's format so it can be directly returned to LLM
        if len(content.strip()) == 0:
            content = "[empty output]"
        print(f"Command ran and generated the following output:\n```\n{content}\n```")
        return 0 if resp.ok else 1

    # Fallback: pretty print
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if resp.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())


