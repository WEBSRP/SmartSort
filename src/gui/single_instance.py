"""One GUI per user runtime, with bounded local-only window activation.

A kernel flock owns the GUI lifetime; it releases on a crash without stale PID
heuristics. The lock file is deliberately never unlinked. Only its owner may
remove a stale socket, and normal shutdown closes the server before unlocking.
"""

import errno
import fcntl
import os
from pathlib import Path
import stat
import tempfile
import threading
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket


class InstanceGuardError(RuntimeError):
    """The GUI cannot safely establish or contact its single-instance owner."""


class SingleInstanceGuard(QObject):
    activation_requested = pyqtSignal()
    _REQUEST = b"activate\n"
    _MAX_REQUEST = 32
    _MAX_CLIENTS = 8

    def __init__(self, parent=None, *, runtime_dir=None, startup_timeout_ms=2500):
        super().__init__(parent)
        if (isinstance(startup_timeout_ms, bool) or not isinstance(startup_timeout_ms, int)
                or startup_timeout_ms <= 0):
            raise ValueError("startup_timeout_ms must be a positive integer")
        self.startup_timeout_ms = startup_timeout_ms
        self.runtime_dir = self._runtime_directory(runtime_dir)
        self.server_name = str(self.runtime_dir / 'gui.sock')
        self.lock_path = self.runtime_dir / 'gui.lock'
        self._lock_fd = None
        self._server = None
        self._clients = {}
        self._handler = None
        self._pending_activation = False
        self._primary = False
        self._notified = False
        self._closed = False

    @staticmethod
    def _private_directory(path):
        try:
            info = path.lstat()
        except OSError as error:
            raise InstanceGuardError("Cannot access SmartSort's private runtime directory") from error
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077):
            raise InstanceGuardError("SmartSort's runtime directory must be private and owned by this user")

    @classmethod
    def _runtime_directory(cls, explicit):
        if explicit is not None:
            directory = Path(explicit)
            if not directory.is_absolute():
                raise InstanceGuardError("SmartSort's runtime directory must be absolute")
        else:
            configured = os.environ.get('XDG_RUNTIME_DIR')
            if configured:
                base = Path(configured)
                if not base.is_absolute():
                    raise InstanceGuardError("XDG_RUNTIME_DIR must be an absolute private directory")
                cls._private_directory(base)
                directory = base / 'smartsort'
            else:
                directory = Path(tempfile.gettempdir()) / f'smartsort-{os.geteuid()}'
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
        except OSError as error:
            raise InstanceGuardError("Cannot create SmartSort's private runtime directory") from error
        cls._private_directory(directory)
        # Linux pathname Unix sockets have a small fixed sockaddr_un buffer.
        if len(os.fsencode(directory / 'gui.sock')) > 103:
            raise InstanceGuardError("SmartSort's runtime directory path is too long for a local socket")
        return directory

    @property
    def is_primary(self):
        return self._primary

    @property
    def pending_activation(self):
        return self._pending_activation

    def set_activation_handler(self, callback):
        """Connect the ready window and coalesce any requests received at startup."""
        if not callable(callback):
            raise TypeError("activation handler must be callable")
        if self._closed:
            return
        self._handler = callback
        if self._pending_activation:
            self._pending_activation = False
            callback()

    def _open_lock(self):
        descriptor = None
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC
                                 | getattr(os, 'O_NOFOLLOW', 0) | os.O_NONBLOCK, 0o600)
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1):
                raise InstanceGuardError("SmartSort's instance lock is not a private regular file")
            os.fchmod(descriptor, 0o600)
            self._lock_fd = descriptor
            descriptor = None
        except OSError as error:
            raise InstanceGuardError("Cannot open SmartSort's instance lock") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _try_primary(self):
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EAGAIN, errno.EACCES):
                return False
            raise InstanceGuardError("Cannot lock the SmartSort GUI instance") from error
        self._primary = True
        try:
            # A crashed owner may leave a socket name. No other contender can
            # be listening here legitimately while this process holds the lock.
            try:
                info = os.lstat(self.server_name)
            except FileNotFoundError:
                info = None
            if info is not None:
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
                    raise InstanceGuardError("SmartSort's local socket path is occupied by an unexpected file")
                if not QLocalServer.removeServer(self.server_name):
                    raise InstanceGuardError("Cannot remove SmartSort's stale local socket")
            self._server = QLocalServer(self)
            self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
            self._server.setMaxPendingConnections(self._MAX_CLIENTS)
            self._server.newConnection.connect(self._accept_connections)
            if not self._server.listen(self.server_name):
                raise InstanceGuardError("Cannot listen on SmartSort's local activation socket: "
                                         + self._server.errorString())
            return True
        except Exception:
            self.close()
            raise

    def _notify_primary(self, remaining_ms):
        socket = QLocalSocket()
        try:
            socket.connectToServer(self.server_name)
            if not socket.waitForConnected(min(100, remaining_ms)):
                return False
            if socket.write(self._REQUEST) != len(self._REQUEST):
                return False
            if socket.bytesToWrite() and not socket.waitForBytesWritten(min(100, remaining_ms)):
                return False
            # No acknowledgement is required: the owner can still be building
            # its dashboard. The fixed request is queued in the local socket.
            socket.disconnectFromServer()
            if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                socket.waitForDisconnected(min(50, remaining_ms))
            return True
        finally:
            socket.abort()

    def acquire_or_notify(self, *, activate=True):
        """True claims the GUI; False means an existing owner was notified.

        A failed/unsafe IPC setup raises instead of starting an unguarded GUI.
        ``activate=False`` permits quiet autostart/service duplicates to exit.
        """
        if self._closed:
            raise InstanceGuardError("The instance guard has already been closed")
        if self._primary:
            return True
        if self._notified:
            return False
        self._open_lock()
        deadline = time.monotonic() + self.startup_timeout_ms / 1000
        try:
            while True:
                if self._try_primary():
                    return True
                remaining = deadline - time.monotonic()
                if not activate or self._notify_primary(max(1, int(remaining * 1000))):
                    self._notified = True
                    self._release_lock()
                    return False
                if remaining <= 0:
                    raise InstanceGuardError("SmartSort is already starting but cannot yet be contacted. Try again.")
                threading.Event().wait(min(.025, remaining))
        except Exception:
            self.close()
            raise

    def _accept_connections(self):
        if self._closed or self._server is None:
            return
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if len(self._clients) >= self._MAX_CLIENTS:
                socket.abort()
                socket.deleteLater()
                continue
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.setInterval(1000)
            timer.timeout.connect(socket.abort)
            self._clients[socket] = (bytearray(), timer)
            socket.readyRead.connect(lambda current=socket: self._read_request(current))
            socket.disconnected.connect(lambda current=socket: self._drop_client(current))
            timer.start()
            self._read_request(socket)

    def _read_request(self, socket):
        if self._closed or socket not in self._clients:
            return
        buffer, timer = self._clients[socket]
        if socket.bytesAvailable() + len(buffer) > self._MAX_REQUEST:
            socket.abort()
            self._drop_client(socket)
            return
        buffer.extend(bytes(socket.readAll()))
        if bytes(buffer) == self._REQUEST:
            timer.stop()
            self._pending_activation = self._handler is None
            self.activation_requested.emit()
            if self._handler is not None:
                self._handler()
            socket.disconnectFromServer()
            self._drop_client(socket)
        elif not self._REQUEST.startswith(bytes(buffer)):
            socket.abort()
            self._drop_client(socket)

    def _drop_client(self, socket):
        state = self._clients.pop(socket, None)
        if state is not None:
            state[1].stop()
            socket.deleteLater()

    def _release_lock(self):
        if self._lock_fd is not None:
            if self._primary:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None
        self._primary = False

    def close(self):
        """Close our endpoint before unlocking, never unlinking the shared lock."""
        if self._closed:
            return
        self._closed = True
        for socket in list(self._clients):
            socket.abort()
            self._drop_client(socket)
        if self._server is not None:
            self._server.close()
            self._server.deleteLater()
            self._server = None
        self._handler = None
        self._pending_activation = False
        self._release_lock()
