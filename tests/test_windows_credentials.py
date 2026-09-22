from importlib import import_module
import subprocess
import sys
import uuid

import pytest


def test_mutex_identity_covers_all_sessions_but_separates_users_and_services():
    m = import_module("bktstr.windows_credentials")
    name = m.mutex_name("bktstr/service-a", b"user-sid-a")
    assert name.startswith("Global\\")
    assert name != m.mutex_name("bktstr/service-a", b"user-sid-b")
    assert name != m.mutex_name("bktstr/service-b", b"user-sid-a")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager integration")
def test_vault_roundtrip_across_processes_and_cleanup():
    try:
        m = import_module("bktstr.windows_credentials")
    except ModuleNotFoundError:
        pytest.fail("Windows credential store is not implemented")
    target = "bktstr/test/" + uuid.uuid4().hex
    store = m.WindowsCredentialStore(target)
    try:
        assert store.read() is None
        with store.locked():
            store.write('{"active":"disposable-test-key","pending":null}')
        script = "from bktstr.windows_credentials import WindowsCredentialStore; import sys; s=WindowsCredentialStore(sys.argv[1]); sys.exit(0 if s.read()=='{\"active\":\"disposable-test-key\",\"pending\":null}' else 1)"
        result = subprocess.run([sys.executable, "-c", script, target], capture_output=True)
        assert result.returncode == 0, result.stderr.decode()
        with store.locked():
            store.write("updated")
        assert store.read() == "updated"
    finally:
        store.delete()
    assert store.read() is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager integration")
def test_vault_lock_blocks_other_process_until_transaction_finishes():
    m = import_module("bktstr.windows_credentials")
    target = "bktstr/test/" + uuid.uuid4().hex
    store = m.WindowsCredentialStore(target)
    script = "from bktstr.windows_credentials import WindowsCredentialStore; import sys; s=WindowsCredentialStore(sys.argv[1]); print('ready',flush=True)\nwith s.locked():\n print('acquired',flush=True)\n"
    child = None
    try:
        with store.locked():
            child = subprocess.Popen([sys.executable, "-c", script, target], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            assert child.stdout.readline().strip() == "ready"
            with pytest.raises(subprocess.TimeoutExpired):
                child.communicate(timeout=0.2)
        output, errors = child.communicate(timeout=5)
        assert child.returncode == 0, errors
        assert "acquired" in output
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.communicate()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager integration")
def test_vault_rejected_write_preserves_previous_record():
    m = import_module("bktstr.windows_credentials")
    store = m.WindowsCredentialStore("bktstr/test/" + uuid.uuid4().hex)
    try:
        with store.locked():
            store.write("working")
            with pytest.raises(OSError):
                store.write("x" * 2561)
        assert store.read() == "working"
    finally:
        store.delete()
