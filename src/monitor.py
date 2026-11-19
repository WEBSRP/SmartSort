import os
import threading
import time
import logging
from pathlib import Path
import stat
from src.utils.output_tracker import is_recent_output
from src.utils.folder_guard import protected_folder_for
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger("SmartSort")


def _get_file_identity(file_path):
    """Return (inode, device) tuple that uniquely identifies a file on disk.

    After a MOVE operation the original path no longer exists and may be
    reused by a completely new file.  Comparing inode+device lets us
    distinguish "same physical file, duplicate watchdog event" from
    "new file that happens to reuse the same path".

    Returns ``None`` if the file cannot be stat'd (e.g. already removed).
    """
    try:
        st = os.stat(file_path)
        return (st.st_ino, st.st_dev)
    except OSError:
        return None


def _get_file_version(file_path):
    """Distinguish changed contents and rapid inode reuse without hashing."""
    try:
        info = os.stat(file_path)
        return (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    except OSError:
        return None


class DownloadHandler(FileSystemEventHandler):
    def __init__(self, organizer, on_new_file_callback, *, watch_path=None, recursive=False):
        self.organizer = organizer
        self.on_new_file_callback = on_new_file_callback
        self.watch_path = os.path.realpath(watch_path) if watch_path else None
        self.recursive = recursive
        # Added .tmp, .opdownload for Chromium-based browsers
        self.ignored_extensions = [".crdownload", ".part", ".tmp", ".opdownload"]
        # path -> (timestamp, inode, device)
        # The inode+device pair identifies the *physical* file so that a new
        # file appearing at the same path after a MOVE is not mistakenly
        # considered already processed.
        self.processed_files = {}
        self._processed_versions = {}
        # (path, inode, device) tuples currently being stability-checked
        self.pending_files = {}  # path -> (inode, device)
        self.lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            self._handle_directory(event.src_path)
        else:
            self._handle_event(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            self._handle_directory(event.dest_path)
        else:
            self._handle_event(event.dest_path)
            
    def on_modified(self, event):
        if not event.is_directory:
            self._handle_event(event.src_path)

    def _ignored_path(self, path):
        absolute = os.path.abspath(path)
        if self.watch_path:
            try:
                if os.path.commonpath([self.watch_path, absolute]) != self.watch_path:
                    return True
                parts = Path(os.path.relpath(absolute, self.watch_path)).parts
            except ValueError:
                return True
            if any(part.startswith('.') or os.path.splitext(part)[1].lower() in self.ignored_extensions for part in parts):
                return True
            if protected_folder_for(absolute, self.watch_path):
                return True
            # Reject symlinked ancestors as well as direct symlink files.
            if os.path.realpath(absolute) != absolute:
                return True
        return (os.path.islink(absolute) or os.path.basename(absolute) == 'SmartSort_Arrangement.md'
                or is_recent_output(absolute))

    def _handle_directory(self, path):
        if not self.recursive or self._ignored_path(path):
            return
        for directory, names, files in os.walk(path, followlinks=False):
            names[:] = [name for name in names if not self._ignored_path(os.path.join(directory, name))]
            for name in files:
                self._handle_event(os.path.join(directory, name))

    def _cleanup_expired(self):
        """Prune files processed more than 300 seconds (5 minutes) ago."""
        now = time.time()
        expiry_limit = 300
        expired = [path for path, (timestamp, _ino, _dev) in self.processed_files.items()
                    if now - timestamp > expiry_limit]
        for path in expired:
            self.processed_files.pop(path, None)
            self._processed_versions.pop(path, None)

    def _handle_event(self, file_path):
        # 1. Ignore if file doesn't exist (e.g. deleted or moved by us)
        if not os.path.exists(file_path):
            return
        if self._ignored_path(file_path):
            return
        try:
            if not stat.S_ISREG(os.lstat(file_path).st_mode):
                return
        except OSError:
            return

        # 2. Ignore temporary download files
        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()
        if ext in self.ignored_extensions or filename.startswith("."):
            return

        # 3. Get the physical file identity (inode + device)
        identity = _get_file_identity(file_path)
        version = _get_file_version(file_path)
        if identity is None or version is None:
            return

        # 4. Prevent duplicate processing of the same *physical* file
        with self.lock:
            self._cleanup_expired()

            # Check processed_files: same path AND same inode/device → duplicate event
            prev = self.processed_files.get(file_path)
            if prev is not None:
                _, prev_ino, prev_dev = prev
                if ((prev_ino, prev_dev) == identity and
                        self._processed_versions.get(file_path, version) == version):
                    # Same physical file and version: duplicate watchdog event.
                    return
                # Changed contents or a replacement at the same path. Linux
                # can reuse an inode immediately; inode/device alone is insufficient.
                del self.processed_files[file_path]
                self._processed_versions.pop(file_path, None)

            # Check pending_files: same path AND same inode/device → already stabilizing
            pending_identity = self.pending_files.get(file_path)
            if pending_identity is not None and pending_identity == identity:
                return

            self.pending_files[file_path] = identity

        # 5. Start a thread to check for stability and then process
        threading.Thread(target=self._wait_and_process, args=(file_path, identity), daemon=True).start()

    def _wait_and_process(self, file_path, original_identity):
        try:
            # Wait for file to be stable
            stable = False
            last_version = None
            stable_count = 0
            
            # Check up to 10 seconds for stability
            for _ in range(20):
                if not os.path.exists(file_path):
                    self.organizer.logger.debug(f"Stale event skipped. File no longer exists: {file_path}")
                    return
                    
                current_version = _get_file_version(file_path)
                if current_version is None:
                    self.organizer.logger.debug(f"Stale event skipped. Could not stat: {file_path}")
                    return
                    
                if current_version == last_version:
                    stable_count += 1
                    if stable_count >= 2: # 1 second stable
                        stable = True
                        break
                else:
                    stable_count = 0
                    last_version = current_version
                    
                time.sleep(0.5)
                
            if not stable:
                self.organizer.logger.debug(f"File did not stabilize in time: {file_path}")
                return
                
            # One final check before processing
            if not os.path.exists(file_path):
                self.organizer.logger.debug(f"Stale event skipped before callback. File missing: {file_path}")
                return

            # Verify the file identity hasn't changed during stabilization
            current_identity = _get_file_identity(file_path)
            if current_identity is None or current_identity != original_identity or self._ignored_path(file_path):
                self.organizer.logger.debug(f"Stale event skipped. Cannot stat file: {file_path}")
                return

            with self.lock:
                self.processed_files[file_path] = (time.time(), current_identity[0], current_identity[1])
                self._processed_versions[file_path] = current_version
                
            # Notify the application/GUI about the new file
            self.on_new_file_callback(file_path)
        finally:
            with self.lock:
                if self.pending_files.get(file_path) == original_identity:
                    self.pending_files.pop(file_path, None)

    def mark_as_unprocessed(self, file_path):
        """Allow re-processing if needed (e.g. on error)"""
        with self.lock:
            self.processed_files.pop(file_path, None)
            self._processed_versions.pop(file_path, None)


class FileMonitor:
    def __init__(self, watch_path, organizer, on_new_file_callback):
        self.watch_path = os.path.realpath(os.path.expanduser(watch_path))
        self.organizer = organizer
        self.on_new_file_callback = on_new_file_callback
        self.observer = Observer()
        config = getattr(organizer, 'config', None)
        self.recursive = bool(config and config.get('sorting_mode', 'rules_first') == 'intelligence'
                              and config.get('downloads_recursive', True))
        self.event_handler = DownloadHandler(self.organizer, self.on_new_file_callback,
                                            watch_path=self.watch_path, recursive=self.recursive)

    def start(self):
        self.observer.schedule(self.event_handler, self.watch_path, recursive=self.recursive)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        if self.observer.is_alive():
            self.observer.join()
