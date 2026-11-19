"""Short-lived undo journal for interactive folder organization."""
import os
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

from src.utils.file_utils import FileUtils
from src.utils.folder_guard import protected_folder_for
from src.utils.output_tracker import remember_output


def identity(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Expected a regular file")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


@dataclass
class Entry:
    source: str
    target: str
    fingerprint: tuple
    digest: str
    source_stat: os.stat_result
    duplicate: bool
    backup: Optional[tuple]


class FolderUndo:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self.entries = []
        self.storage = None
        self.deadline = 0

    def backup(self, target):
        """Only overwrite operations need to retain any file contents."""
        before = identity(target)
        if self.storage is None:
            self.storage = tempfile.TemporaryDirectory(prefix="smartsort-undo-")
        fd, path = tempfile.mkstemp(dir=self.storage.name)
        os.close(fd)
        shutil.copy2(target, path)
        digest = FileUtils.calculate_sha256(path)
        if not digest or FileUtils.calculate_sha256(target) != digest or identity(target) != before:
            raise ValueError("Could not verify the existing file before overwrite")
        return path, digest, before

    def complete(self):
        self.deadline = time.monotonic() + 600

    def close(self):
        self.entries.clear()
        if self.storage:
            self.storage.cleanup()
            self.storage = None

    def _check_path(self, path):
        if (os.path.realpath(path) != path or os.path.commonpath([self.root, path]) != self.root
                or protected_folder_for(path, self.root)):
            raise ValueError("Folder changed or is protected")

    def _publish(self, original, destination, digest, info, replace_identity=None):
        """Publish a verified copy exclusively, even across filesystems."""
        self._check_path(destination)
        if replace_identity is None and os.path.lexists(destination):
            raise FileExistsError("Original location is occupied")
        fd, staged = tempfile.mkstemp(dir=os.path.dirname(destination), prefix=".smartsort-undo-")
        os.close(fd)
        try:
            shutil.copy2(original, staged)
            if FileUtils.calculate_sha256(staged) != digest:
                raise ValueError("Content changed")
            os.chmod(staged, stat.S_IMODE(info.st_mode) & 0o777)
            os.utime(staged, ns=(info.st_atime_ns, info.st_mtime_ns))
            self._check_path(destination)
            if replace_identity is None:
                os.link(staged, destination)
            else:
                if identity(destination) != replace_identity:
                    raise ValueError("Sorted file changed during reversal")
                os.replace(staged, destination)
        finally:
            if os.path.lexists(staged):
                os.unlink(staged)
        remember_output(destination)
        return identity(destination)

    def restore_backup(self, backup, target, expected):
        path, digest, _ = backup
        return self._publish(path, target, digest, os.stat(path), expected)

    def reverse(self):
        restored, errors = 0, []
        replaced = {}
        try:
            for entry in reversed(self.entries):
                try:
                    self._check_path(entry.target)
                    self._check_path(entry.source)
                    expected = replaced.get((entry.target, entry.digest), entry.fingerprint)
                    if identity(entry.target) != expected:
                        raise ValueError("Sorted file changed or was replaced")
                    recovered = self._publish(entry.target, entry.source, entry.digest, entry.source_stat)
                    if not entry.duplicate:
                        self._check_path(entry.target)
                        self._check_path(entry.source)
                        if identity(entry.source) != recovered or identity(entry.target) != expected:
                            raise ValueError("Sorted file changed during reversal")
                        if entry.backup:
                            previous = self.restore_backup(entry.backup, entry.target, expected)
                            replaced[entry.target, entry.backup[1]] = previous
                        else:
                            os.unlink(entry.target)
                    restored += 1
                except (OSError, ValueError) as error:
                    errors.append(f"{entry.source} — {error}")
        finally:
            self.close()
        return restored, errors
