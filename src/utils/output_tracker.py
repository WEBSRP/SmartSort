"""Briefly suppress unchanged files just written by this process's organizers."""
import os
import stat
import threading
import time

_lock = threading.Lock()
_outputs = {}
_MAX_OUTPUTS = 2048
_TTL = 300


def _snapshot(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        return None
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def remember_output(path):
    try:
        path = os.path.abspath(path)
        identity = _snapshot(path)
        if identity is None:
            return
    except OSError:
        return
    now = time.monotonic()
    with _lock:
        for key, (_, saved) in list(_outputs.items()):
            if now - saved > _TTL:
                _outputs.pop(key, None)
        _outputs.pop(path, None)
        while len(_outputs) >= _MAX_OUTPUTS:
            _outputs.pop(next(iter(_outputs)))
        _outputs[path] = (identity, now)


def is_recent_output(path):
    path = os.path.abspath(path)
    with _lock:
        record = _outputs.get(path)
    if record is None:
        return False
    try:
        current = _snapshot(path)
    except OSError:
        current = None
    unchanged = time.monotonic() - record[1] <= _TTL and current == record[0]
    if not unchanged:
        with _lock:
            if _outputs.get(path) == record:
                _outputs.pop(path, None)
    return unchanged
