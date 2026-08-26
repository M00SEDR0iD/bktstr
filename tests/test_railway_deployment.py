import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).parents[1]
UNEXPANDED_VARIABLE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*|\{[^}]+\})")


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_railway_start_command_reads_runtime_port_and_serves_health(tmp_path):
    config = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
    command = shlex.split(config["deploy"]["startCommand"])

    uses_shell = command[:2] in (["sh", "-c"], ["/bin/sh", "-c"])
    assert uses_shell or not any(UNEXPANDED_VARIABLE.search(token) for token in command), (
        "Railway runs Dockerfile start overrides in exec form, so environment "
        "references require a shell wrapper or must be read by the application"
    )

    # Exercise the configured module in this test environment while preserving
    # Railway's exec-form argument semantics.
    if command[0] == "python":
        command[0] = sys.executable
    elif command[0] == "uvicorn":
        command = [sys.executable, "-m", "uvicorn", *command[1:]]

    port = _available_port()
    environment = {
        **os.environ,
        "PORT": str(port),
        "BKTSTR_EXPERIMENT_DIR": str(tmp_path / "experiments"),
    }
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(
                    f"Railway start command exited before health was ready:\n{stdout}{stderr}"
                )
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.25) as response:
                    assert response.status == 200
                    assert json.load(response)["status"] == "ok"
                    break
            except URLError:
                time.sleep(0.05)
        else:
            raise AssertionError("Railway start command did not serve /health within 10 seconds")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
