"""Local GUI ownership survives rapid launch, crash and startup activation races."""

import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtNetwork import QLocalSocket

from src.gui.single_instance import InstanceGuardError, SingleInstanceGuard


@pytest.fixture
def runtime():
    # Keep Unix socket pathnames short even when the suite's basetemp is deep.
    with tempfile.TemporaryDirectory(prefix='ss-instance-') as directory:
        yield Path(directory)


def pump(qapp, milliseconds=100):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()
    qapp.processEvents()


def secondary(runtime, activate=True):
    code = '''
import sys
from PyQt6.QtCore import QCoreApplication
from src.gui.single_instance import SingleInstanceGuard
app=QCoreApplication([])
guard=SingleInstanceGuard(runtime_dir=sys.argv[1],startup_timeout_ms=1000)
print('primary' if guard.acquire_or_notify(activate=sys.argv[2]=='yes') else 'secondary',flush=True)
guard.close()
'''
    return subprocess.run([sys.executable, '-B', '-c', code, str(runtime), 'yes' if activate else 'no'],
                          capture_output=True, text=True, timeout=5)


def test_secondary_launch_activates_existing_owner(qapp, runtime):
    owner = SingleInstanceGuard(runtime_dir=runtime)
    try:
        assert owner.acquire_or_notify()
        activations = []
        owner.set_activation_handler(lambda: activations.append('dashboard'))
        other = secondary(runtime)
        assert other.returncode == 0, other.stderr
        assert other.stdout.strip() == 'secondary'
        pump(qapp)
        assert activations == ['dashboard']
        assert owner.is_primary
        assert stat.S_IMODE(runtime.stat().st_mode) == 0o700
        assert stat.S_IMODE(owner.lock_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(Path(owner.server_name).stat().st_mode) & 0o077 == 0
    finally:
        owner.close()


def test_activation_during_startup_waits_for_window_handler(qapp, runtime):
    owner = SingleInstanceGuard(runtime_dir=runtime)
    try:
        assert owner.acquire_or_notify()
        assert secondary(runtime).returncode == 0
        pump(qapp)
        assert owner.pending_activation
        calls = []
        owner.set_activation_handler(lambda: calls.append(1))
        assert calls == [1] and not owner.pending_activation
        owner.set_activation_handler(lambda: calls.append(2))
        assert calls == [1]
    finally:
        owner.close()


def test_service_duplicate_can_exit_without_foreground_activation(qapp, runtime):
    owner = SingleInstanceGuard(runtime_dir=runtime)
    try:
        assert owner.acquire_or_notify()
        calls = []
        owner.set_activation_handler(lambda: calls.append(1))
        other = secondary(runtime, activate=False)
        assert other.returncode == 0 and other.stdout.strip() == 'secondary'
        pump(qapp, 30)
        assert not calls
    finally:
        owner.close()


def test_close_is_idempotent_and_cannot_remove_replacement_endpoint(qapp, runtime):
    first = SingleInstanceGuard(runtime_dir=runtime)
    assert first.acquire_or_notify()
    first.close()
    replacement = SingleInstanceGuard(runtime_dir=runtime)
    try:
        assert replacement.acquire_or_notify()
        first.close()
        assert Path(replacement.server_name).exists()
        assert secondary(runtime).stdout.strip() == 'secondary'
        pump(qapp)
        assert replacement.pending_activation
        assert first.lock_path.exists()  # Never unlink a lock another process may hold.
    finally:
        replacement.close()


@pytest.mark.parametrize('payload', [b'invalid\n', b'activate\ntrailing', b'x' * 200])
def test_only_bounded_fixed_activation_protocol_is_accepted(qapp, runtime, payload):
    owner = SingleInstanceGuard(runtime_dir=runtime)
    client = QLocalSocket()
    try:
        assert owner.acquire_or_notify()
        calls = []
        owner.set_activation_handler(lambda: calls.append(1))
        client.connectToServer(owner.server_name)
        assert client.waitForConnected(1000)
        client.write(payload)
        if client.bytesToWrite():
            assert client.waitForBytesWritten(1000)
        pump(qapp)
        assert calls == []
    finally:
        client.abort()
        owner.close()


def test_crashed_owner_releases_lock_and_stale_socket_is_recovered(qapp, runtime):
    code = '''
import os,sys
from PyQt6.QtCore import QCoreApplication
from src.gui.single_instance import SingleInstanceGuard
app=QCoreApplication([])
guard=SingleInstanceGuard(runtime_dir=sys.argv[1]);assert guard.acquire_or_notify()
print('ready',flush=True);os._exit(0)
'''
    process = subprocess.run([sys.executable, '-B', '-c', code, str(runtime)],
                             capture_output=True, text=True, timeout=5)
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == 'ready'
    recovered = SingleInstanceGuard(runtime_dir=runtime)
    try:
        assert recovered.acquire_or_notify()
        assert Path(recovered.server_name).exists()
    finally:
        recovered.close()


def test_racing_launches_choose_one_primary(qapp, runtime):
    code = '''
import sys
from PyQt6.QtCore import QCoreApplication,QTimer
from src.gui.single_instance import SingleInstanceGuard
app=QCoreApplication([]);guard=SingleInstanceGuard(runtime_dir=sys.argv[1])
primary=guard.acquire_or_notify();print('primary' if primary else 'secondary',flush=True)
if primary:
 QTimer.singleShot(1500,app.quit);app.exec()
guard.close()
'''
    processes = [subprocess.Popen([sys.executable, '-B', '-c', code, str(runtime)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for _ in range(6)]
    try:
        results = [process.communicate(timeout=8) for process in processes]
        assert all(process.returncode == 0 for process in processes), results
        assert [stdout.strip() for stdout, _ in results].count('primary') == 1
        assert [stdout.strip() for stdout, _ in results].count('secondary') == 5
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait()


def test_busy_owner_without_server_fails_closed_with_bounded_wait(qapp, runtime):
    descriptor = os.open(runtime / 'gui.lock', os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    guard = SingleInstanceGuard(runtime_dir=runtime, startup_timeout_ms=100)
    start = time.monotonic()
    try:
        with pytest.raises(InstanceGuardError, match='already starting'):
            guard.acquire_or_notify()
        assert time.monotonic() - start < 1
    finally:
        guard.close()
        os.close(descriptor)


@pytest.mark.parametrize('kind', ['directory-link', 'public-directory', 'lock-link', 'socket-file'])
def test_unsafe_runtime_entries_fail_without_touching_existing_data(qapp, runtime, kind):
    victim = runtime / 'victim'
    victim.write_text('preserve')
    target = runtime
    if kind == 'directory-link':
        target = runtime / 'link'
        target.symlink_to(runtime, target_is_directory=True)
    elif kind == 'public-directory':
        runtime.chmod(0o755)
    elif kind == 'lock-link':
        (runtime / 'gui.lock').symlink_to(victim)
    else:
        (runtime / 'gui.sock').write_text('preserve socket-file')
    guard = None
    try:
        with pytest.raises(InstanceGuardError):
            guard = SingleInstanceGuard(runtime_dir=target)
            guard.acquire_or_notify()
    finally:
        if guard is not None:
            guard.close()
    assert victim.read_text() == 'preserve'
    if kind == 'socket-file':
        assert (runtime / 'gui.sock').read_text() == 'preserve socket-file'


def test_default_namespace_is_shared_by_source_and_installed_launches(qapp, runtime, monkeypatch):
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(runtime))
    owner = SingleInstanceGuard()
    try:
        assert owner.runtime_dir == runtime / 'smartsort'
        assert owner.acquire_or_notify()
        another = SingleInstanceGuard()
        try:
            assert another.server_name == owner.server_name
            assert not another.acquire_or_notify(activate=False)
        finally:
            another.close()
    finally:
        owner.close()


def test_absent_xdg_runtime_uses_private_uid_fallback(qapp, runtime, monkeypatch):
    monkeypatch.delenv('XDG_RUNTIME_DIR', raising=False)
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(runtime))
    guard = SingleInstanceGuard()
    try:
        assert guard.runtime_dir == runtime / f'smartsort-{os.geteuid()}'
        assert guard.acquire_or_notify()
    finally:
        guard.close()
