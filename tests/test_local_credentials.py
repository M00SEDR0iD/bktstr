from contextlib import nullcontext
from importlib import import_module
import json
import os
import sys

import httpx
import pytest


ORIGIN = "https://bktstr.example"
OLD = "existing-test-secret"
NEW = "replacement-test-secret"


def module():
    try:
        return import_module("bktstr.local_credentials")
    except ModuleNotFoundError:
        pytest.fail("Local credential helper is not implemented")


class MemoryStore:
    def __init__(self):
        self.value = None

    def read(self):
        return self.value

    def write(self, value):
        self.value = value

    def locked(self):
        return nullcontext()


def helper(accepted=OLD, *, status=200):
    m = module()
    store = MemoryStore()

    def server(request):
        assert request.url == ORIGIN + "/api/v1/capabilities"
        if request.headers.get("Authorization") != f"Bearer {accepted}":
            return httpx.Response(401)
        return httpx.Response(status, json={"service": "bktstr", "version": "0.6.0"})

    return m.CredentialHelper(store, ORIGIN, transport=httpx.MockTransport(server)), store


def test_import_verifies_before_replacing_working_key():
    m = module()
    h, store = helper()
    h.save(OLD)
    original = store.value
    with pytest.raises(m.CredentialError):
        h.save(NEW)
    assert store.value == original
    assert h.status() == {"base_url": ORIGIN, "active": True, "pending": False}


def test_generation_preserves_active_and_requires_explicit_pending_replacement():
    m = module()
    h, store = helper()
    h.save(OLD)
    assert h.generate() is None
    record = json.loads(store.value)
    assert record["active"] == OLD
    assert len(record["pending"]) >= 43
    with pytest.raises(m.CredentialError):
        h.generate()
    assert json.loads(store.value) == record
    h.generate(replace_pending=True)
    assert json.loads(store.value)["pending"] != record["pending"]
    assert json.loads(store.value)["active"] == OLD


def test_activation_preserves_both_slots_on_failure_then_promotes_verified_key():
    m = module()
    h, store = helper(accepted=NEW)
    store.value = json.dumps({"active": OLD, "pending": "wrong-key"})
    before = store.value
    with pytest.raises(m.CredentialError):
        h.activate()
    assert store.value == before
    store.value = json.dumps({"active": OLD, "pending": NEW})
    h.activate()
    assert json.loads(store.value) == {"active": NEW, "pending": None}
    h.check()


@pytest.mark.parametrize("url", ["http://bktstr.example", "https://user:pass@bktstr.example", "https://bktstr.example/path", "https://bktstr.example?x=y", "https://bktstr.example/#x", "https://bktstr.example\\evil", "https://bktstr.example:wrong", "https://bkt str.example", "https://bktstr.example?", "https://bktstr.example#"])
def test_rejects_unsafe_origins(url):
    m = module()
    with pytest.raises(m.CredentialError):
        m.normalize_origin(url)


def test_origin_normalization_and_vault_binding():
    m = module()
    assert m.normalize_origin("https://BKTSTR.example:443/") == ORIGIN
    assert m.credential_target(ORIGIN) == m.credential_target(ORIGIN + "/")
    assert m.credential_target(ORIGIN) != m.credential_target("https://other.example")


@pytest.mark.parametrize("value", ["", "bad\nkey", "bad key", "é", "x" * 1025])
def test_rejects_invalid_keys_before_network_or_storage(value):
    m = module()
    h, store = helper()
    with pytest.raises(m.CredentialError):
        h.save(value)
    assert store.value is None


def test_verification_rejects_redirect_without_forwarding_secret():
    m = module()
    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://elsewhere.example"})

    with pytest.raises(m.CredentialError):
        m.verify_key(ORIGIN, OLD, transport=httpx.MockTransport(redirect))
    assert len(requests) == 1


@pytest.mark.parametrize("response", [httpx.Response(200, json={"service": "other"}), httpx.Response(200, text="not-json"), httpx.Response(403), httpx.Response(500), httpx.Response(200, json=[])])
def test_verification_rejects_wrong_services_and_errors(response):
    m = module()
    with pytest.raises(m.CredentialError):
        m.verify_key(ORIGIN, OLD, transport=httpx.MockTransport(lambda r: response))


def test_run_supplies_key_only_to_child_and_propagates_exit(monkeypatch):
    m = module()
    h, store = helper()
    h.save(OLD)
    monkeypatch.setenv("BKTSTR_API_KEY", "unrelated-parent-value")
    # Real child checks the injected environment and arguments without printing secrets.
    script = "import os,sys; sys.exit(7 if os.environ['BKTSTR_API_KEY']=='existing-test-secret' and os.environ['BKTSTR_BASE_URL']=='https://bktstr.example' and sys.argv[1]=='two words' else 8)"
    assert h.run([sys.executable, "-c", script, "two words"]) == 7
    assert os.environ["BKTSTR_API_KEY"] == "unrelated-parent-value"


def test_run_refuses_missing_key_and_command():
    m = module()
    h, _ = helper()
    with pytest.raises(m.CredentialError):
        h.run([sys.executable])
    h.save(OLD)
    with pytest.raises(m.CredentialError):
        h.run([])


def test_clipboard_is_explicit_and_selects_requested_slot(monkeypatch):
    m = module()
    h, store = helper()
    store.value = json.dumps({"active": OLD, "pending": NEW})
    clipboard = []
    monkeypatch.setattr(m, "copy_to_clipboard", clipboard.append)
    h.copy(pending=True)
    h.copy(pending=False)
    assert clipboard == [NEW, OLD]


def test_corrupt_record_fails_closed():
    m = module()
    h, store = helper()
    for value in ["not json", "[]", '{"active": 1}', '{"pending": "secret"}', '{"active": "", "pending": null}']:
        store.value = value
        with pytest.raises(m.CredentialError):
            h.status()
        assert store.value == value


def test_cli_never_prints_keys_and_rejects_noninteractive_save(monkeypatch, capsys):
    m = module()
    h, store = helper()
    store.value = json.dumps({"active": OLD, "pending": NEW})
    monkeypatch.setattr(m, "make_helper", lambda url: h)
    assert m.main(["status"]) == 0
    assert m.main(["check"]) == 0
    assert m.main(["activate"]) == 1
    monkeypatch.setattr(m.sys.stdin, "isatty", lambda: False)
    assert m.main(["save"]) == 1
    output = capsys.readouterr()
    assert OLD not in output.out + output.err
    assert NEW not in output.out + output.err
    assert "terminal" in output.err.lower()


def test_cli_hidden_import_and_child_exit(monkeypatch, capsys):
    m = module()
    h, _ = helper()
    monkeypatch.setattr(m, "make_helper", lambda url: h)
    monkeypatch.setattr(m.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(m.getpass, "getpass", lambda prompt: OLD)
    assert m.main(["save"]) == 0
    assert m.main(["run", "--", sys.executable, "-c", "raise SystemExit(9)"]) == 9
    assert OLD not in str(capsys.readouterr())


def test_cli_redacts_external_exception_details(monkeypatch, capsys):
    m = module()
    h, _ = helper()
    monkeypatch.setattr(m, "make_helper", lambda url: h)

    def fail(value):
        raise OSError(OLD)

    monkeypatch.setattr(h.store, "write", fail)
    assert m.main(["generate"]) == 1
    assert OLD not in str(capsys.readouterr())


def test_hidden_prompt_refuses_getpass_echo_fallback(monkeypatch):
    m = module()
    import warnings

    monkeypatch.setattr(m.sys.stdin, "isatty", lambda: True)

    def echo_fallback(prompt):
        warnings.warn("echo unavailable", m.getpass.GetPassWarning)
        pytest.fail("must stop before echoed input")

    monkeypatch.setattr(m.getpass, "getpass", echo_fallback)
    with pytest.raises(m.CredentialError):
        m.read_key()


def test_failed_vault_write_keeps_working_record(monkeypatch):
    h, store = helper()
    h.save(OLD)
    before = store.value

    def deny(value):
        raise OSError("vault unavailable")

    monkeypatch.setattr(store, "write", deny)
    with pytest.raises(OSError):
        h.generate()
    assert store.value == before


def test_cli_argument_errors_do_not_echo_accidentally_pasted_key(capsys):
    m = module()
    with pytest.raises(SystemExit) as error:
        m.main(["save", OLD])
    assert error.value.code == 2
    assert OLD not in str(capsys.readouterr())


def test_network_failure_does_not_reveal_exception_or_replace_active(capsys, monkeypatch):
    m = module()
    h, store = helper()
    h.save(OLD)
    before = store.value

    def unavailable(request):
        raise httpx.ConnectError(OLD, request=request)

    h.transport = httpx.MockTransport(unavailable)
    monkeypatch.setattr(m, "make_helper", lambda url: h)
    assert m.main(["activate"]) == 1
    assert m.main(["check"]) == 1
    assert store.value == before
    assert OLD not in str(capsys.readouterr())


def test_clipboard_uses_stdin_and_suppresses_external_error_details(monkeypatch, capsys):
    m = module()
    h, _ = helper()
    h.save(OLD)
    monkeypatch.setattr(m, "make_helper", lambda url: h)
    monkeypatch.setattr(m.sys, "platform", "win32")
    monkeypatch.setattr(m.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    from types import SimpleNamespace

    def clipboard(command, **kwargs):
        assert OLD not in str(command)
        assert kwargs["input"] == OLD
        assert kwargs["capture_output"] is True
        assert kwargs["creationflags"] == 0x08000000
        return SimpleNamespace(returncode=1, stderr=OLD)

    monkeypatch.setattr(m.subprocess, "run", clipboard)
    assert m.main(["copy"]) == 1
    assert OLD not in str(capsys.readouterr())
