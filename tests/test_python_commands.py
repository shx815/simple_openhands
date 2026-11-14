"""Smoke tests against a running runtime.

Set OH_TEST_API_URL to use a runtime outside the default Linux container.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import requests

from simple_openhands.cli import main


API_URL = os.environ.get("OH_TEST_API_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("OH_API_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def execute(action: str, **args) -> dict:
    response = requests.post(
        f"{API_URL}/execute_action",
        json={"action": {"action": action, "args": args}},
        headers=HEADERS,
        timeout=70,
    )
    response.raise_for_status()
    return response.json()


def test_basic_commands():
    info = requests.get(f"{API_URL}/server_info", headers=HEADERS, timeout=5)
    info.raise_for_status()
    server = info.json()
    for command, key in (("pwd", "cwd"), ("whoami", "username")):
        result = execute("run", command=command)
        assert result["observation"] == "run"
        assert result["extras"]["metadata"]["exit_code"] == 0
        output = result["content"].strip()
        expected = server[key]
        if command == "pwd":
            assert os.path.realpath(output) == os.path.realpath(expected)
        else:
            assert output == expected


def test_python_code():
    result = execute("run_ipython", code="print(123)")
    assert result["observation"] == "run_ipython"
    assert result["content"].strip() == "123"


def test_parallel_python_commands():
    def run_cell(value):
        return execute("run_ipython", code=f"import time; time.sleep(0.2); print({value})")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run_cell, [12345, 54321]))
    assert [result["content"].strip() for result in results] == ["12345", "54321"]


def test_python_timeout():
    result = execute("run_ipython", code="import time; time.sleep(30)", timeout=1)
    assert "Execution timed out" in result["content"]
    assert execute("run_ipython", code="print(456)")["content"].strip() == "456"


def test_health_check():
    response = requests.get(f"{API_URL}/alive", timeout=5)
    response.raise_for_status()
    assert response.json() == {"status": "alive", "bash_session_active": True}


@pytest.mark.skipif(not TOKEN, reason="Runtime is not configured for bearer authentication")
def test_authentication():
    for authorization in ({}, {"Authorization": "Bearer invalid"}):
        response = requests.get(f"{API_URL}/server_info", headers=authorization, timeout=5)
        assert response.status_code == 401
    response = requests.get(f"{API_URL}/server_info", headers=HEADERS, timeout=5)
    assert response.status_code == 200


def test_health_check_while_shell_is_busy():
    marker = f"/tmp/simple-openhands-smoke-{uuid4().hex}"
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(execute, "run", command=f"touch {marker} && sleep 4 && rm {marker}")
        try:
            # These smoke tests normally run in the same container as the API.
            if API_URL == "http://127.0.0.1:8000":
                deadline = time.monotonic() + 3
                while not Path(marker).exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                assert Path(marker).exists()
            response = requests.get(f"{API_URL}/alive", timeout=1)
            response.raise_for_status()
            assert not running.done()
        finally:
            assert running.result()["extras"]["metadata"]["exit_code"] == 0


def test_line_operations_and_edit():
    path = f"/tmp/simple-openhands-smoke-{uuid4().hex}"
    try:
        assert execute("write", path=path, content="a\nb\nc\n")["observation"] == "write"
        assert execute("read", path=path, start=1, end=2)["content"] == "b\n"
        assert execute("write", path=path, start=1, end=2, content="B\n")["observation"] == "write"
        assert execute("read", path=path)["content"] == "a\nB\nc\n"
        assert execute("edit", path=path, command="str_replace", old_str="B\n", new_str="")["observation"] == "edit"
        assert execute("edit", path=path, command="str_replace", old_str="B", new_str="d")["observation"] == "error"
        assert execute("read", path=path)["content"] == "a\nc\n"
    finally:
        assert execute("run", command=f"rm -f {path}")["extras"]["metadata"]["exit_code"] == 0


@pytest.mark.parametrize("raw", [False, True])
def test_cli_returns_remote_exit_code(raw, monkeypatch, capsys):
    options = ["--raw"] if raw else []
    command = "bash -c 'exit 17'"
    monkeypatch.setattr(sys, "argv", ["oh-run", "--url", API_URL, *options, command])
    assert main() == 17
    assert capsys.readouterr().out
