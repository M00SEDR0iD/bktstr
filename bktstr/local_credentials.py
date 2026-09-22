"""Local agent access: python -m bktstr.local_credentials --help."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import urlsplit
import warnings

import httpx

from .windows_credentials import WindowsCredentialStore


DEFAULT_ORIGIN = "https://bktstr-production.up.railway.app"


class CredentialError(Exception):
    """Safe, user-facing error that never includes credential material."""


def normalize_origin(value: str) -> str:
    try:
        parts = urlsplit(value)
        port = parts.port
        if (
            parts.scheme != "https" or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.path not in ("", "/") or "?" in value or "#" in value
            or "\\" in value or any(ord(c) <= 32 or ord(c) >= 127 for c in value)
            or port == 0
        ):
            raise ValueError
        host = parts.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        origin = f"https://{host}" + (f":{port}" if port not in (None, 443) else "")
        # Let the HTTP library validate the same hostname it will actually contact.
        if httpx.URL(origin).host != parts.hostname.lower():
            raise ValueError
        return origin
    except (ValueError, httpx.InvalidURL):
        raise CredentialError("Use an HTTPS service origin without credentials, paths, queries, or fragments.") from None


def credential_target(base_url: str) -> str:
    digest = hashlib.sha256(normalize_origin(base_url).encode()).hexdigest()
    return "bktstr/api/" + digest


def validate_key(key: str) -> None:
    if not isinstance(key, str) or not 1 <= len(key) <= 1024 or any(not 33 <= ord(c) <= 126 for c in key):
        raise CredentialError("The key must contain 1 to 1024 printable ASCII characters without spaces.")


def verify_key(base_url: str, key: str, *, transport=None) -> None:
    origin = normalize_origin(base_url)
    validate_key(key)
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False, transport=transport) as client:
            response = client.get(origin + "/api/v1/capabilities", headers={"Authorization": "Bearer " + key})
        if response.status_code in (401, 403):
            raise CredentialError("The service rejected the key. Check BKTSTR_API_KEY in Railway and wait for deployment.")
        if response.status_code != 200:
            raise CredentialError("Authentication check failed. The service must respond directly with HTTP 200.")
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("service") != "bktstr":
            raise CredentialError("The address did not return BKTSTR capabilities.")
    except (httpx.HTTPError, ValueError):
        raise CredentialError("Could not verify the key. Check the service address, connectivity, and TLS certificate.") from None


def read_key() -> str:
    if not sys.stdin.isatty():
        raise CredentialError("Run save yourself in an interactive terminal; key input is hidden.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass("Paste the existing BKTSTR key (hidden): ")
    except (getpass.GetPassWarning, EOFError):
        raise CredentialError("Hidden key input is unavailable. Use an interactive Windows terminal.") from None


def copy_to_clipboard(key: str) -> None:
    if sys.platform != "win32":
        raise CredentialError("Clipboard transfer requires Windows.")
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run(
        [str(executable), "-NoProfile", "-NonInteractive", "-Command", "$ErrorActionPreference='Stop'; Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
        input=key, text=True, capture_output=True, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise CredentialError("Could not copy the key to the Windows clipboard.")


class CredentialHelper:
    def __init__(self, store, base_url: str, *, transport=None):
        self.store = store
        self.base_url = normalize_origin(base_url)
        self.transport = transport

    def _read(self) -> dict:
        raw = self.store.read()
        if raw is None:
            return {"active": None, "pending": None}
        try:
            record = json.loads(raw)
            if not isinstance(record, dict) or set(record) != {"active", "pending"}:
                raise ValueError
            for value in record.values():
                if value is not None:
                    validate_key(value)
            return record
        except (ValueError, CredentialError):
            raise CredentialError("The saved credential record is invalid. Restore it through Windows Credential Manager.") from None

    def _key(self, record: dict, slot: str = "active") -> str:
        key = record[slot]
        if key is None:
            raise CredentialError(f"No {slot} key is saved for this service. Use save or generate first.")
        return key

    def _verify(self, key: str) -> None:
        verify_key(self.base_url, key, transport=self.transport)

    def save(self, key: str) -> None:
        validate_key(key)
        with self.store.locked():
            record = self._read()
            self._verify(key)
            record["active"] = key
            if record["pending"] == key:
                record["pending"] = None
            self.store.write(json.dumps(record))

    def generate(self, *, replace_pending: bool = False) -> None:
        with self.store.locked():
            record = self._read()
            if record["pending"] is not None and not replace_pending:
                raise CredentialError("A pending key already exists. Use --replace-pending to intentionally replace it.")
            record["pending"] = secrets.token_urlsafe(32)
            self.store.write(json.dumps(record))

    def activate(self) -> None:
        with self.store.locked():
            record = self._read()
            key = self._key(record, "pending")
            self._verify(key)
            self.store.write(json.dumps({"active": key, "pending": None}))

    def status(self) -> dict:
        with self.store.locked():
            record = self._read()
            return {"base_url": self.base_url, **{slot: value is not None for slot, value in record.items()}}

    def check(self) -> None:
        with self.store.locked():
            self._verify(self._key(self._read()))

    def copy(self, *, pending: bool = False) -> None:
        with self.store.locked():
            copy_to_clipboard(self._key(self._read(), "pending" if pending else "active"))

    def run(self, command: list[str]) -> int:
        if not command:
            raise CredentialError("Supply a trusted program after run --.")
        with self.store.locked():
            key = self._key(self._read())
        environment = os.environ.copy()
        environment.update(BKTSTR_API_KEY=key, BKTSTR_BASE_URL=self.base_url)
        return subprocess.run(command, env=environment, shell=False).returncode


def make_helper(base_url: str) -> CredentialHelper:
    if sys.platform != "win32":
        raise CredentialError("This helper requires Windows. Other environments must supply BKTSTR_API_KEY through their own secret store.")
    origin = normalize_origin(base_url)
    return CredentialHelper(WindowsCredentialStore(credential_target(origin)), origin)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Do not echo unrecognized arguments: an accidental pasted key is still secret.
        self.exit(2, "Invalid command arguments. Use --help. Never pass a key as an argument.\n")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Use BKTSTR keys from Windows Credential Manager without printing them.")
    parser.add_argument("--base-url", default=DEFAULT_ORIGIN, help="HTTPS service origin; defaults to BKTSTR production")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("save", help="Import and verify an existing key through hidden input")
    generate = commands.add_parser("generate", help="Store a new pending key; active key is preserved")
    generate.add_argument("--replace-pending", action="store_true")
    commands.add_parser("activate", help="Verify pending key against the server, then make it active")
    commands.add_parser("check", help="Verify the active key against the server")
    commands.add_parser("status", help="Show which key slots are populated; makes no network requests")
    copy = commands.add_parser("copy", help="Explicitly copy the active key to the Windows clipboard")
    copy.add_argument("--pending", action="store_true", help="Copy pending key instead")
    run = commands.add_parser("run", help="Run a trusted program with BKTSTR_API_KEY and BKTSTR_BASE_URL")
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        helper = make_helper(args.base_url)
        if args.action == "save":
            helper.save(read_key())
            print("Key verified and saved as active.")
        elif args.action == "generate":
            helper.generate(replace_pending=args.replace_pending)
            print("Pending key saved. Copy it to Railway and GitHub, then activate after Railway deploys.")
        elif args.action == "activate":
            helper.activate()
            print("Pending key verified and activated.")
        elif args.action == "check":
            helper.check()
            print("Authentication succeeded.")
        elif args.action == "status":
            print(json.dumps(helper.status(), indent=2))
        elif args.action == "copy":
            helper.copy(pending=args.pending)
            print("Key copied. Paste only into the intended secret settings, then clear clipboard and history.")
        elif args.action == "run":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            return helper.run(command)
        return 0
    except CredentialError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError, UnicodeError):
        print("Credential storage or process operation failed. Check Windows access and the program path; saved keys were not printed.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
