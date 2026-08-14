import os
import threading
import time
import logging
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


class DownloadHandler(FileSystemEventHandler):
    def __init__(self, organizer, on_new_file_callback):
        self.organizer = organizer
        self.on_new_file_callback = on_new_file_callback
        # Added .tmp, .opdownload for Chromium-based browsers
        self.ignored_extensions = [".crdownload", ".part", ".tmp", ".opdownload"]
        # path -> (timestamp, inode, device)
        # The inode+device pair identifies the *physical* file so that a new
        # file appearing at the same path after a MOVE is not mistakenly
        # considered already processed.
        self.processed_files = {}
        # (path, inode, device) tuples currently being stability-checked
        self.pending_files = {}  # path -> (inode, device)
        self.lock = threading.Lock()

    def on_created(self, event):
        if not event.is_directory:
            self._handle_event(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle_event(event.dest_path)
            
    def on_modified(self, event):
        if not event.is_directory:
            self._handle_event(event.src_path)

    def _cleanup_expired(self):
        """Prune files processed more than 300 seconds (5 minutes) ago."""
        now = time.time()
        expiry_limit = 300
        expired = [path for path, (timestamp, _ino, _dev) in self.processed_files.items()
                    if now - timestamp > expiry_limit]
        for path in expired:
            self.processed_files.pop(path, None)

    def _handle_event(self, file_path):
        # 1. Ignore if file doesn't exist (e.g. deleted or moved by us)
        if not os.path.exists(file_path):
            return

        # 2. Ignore temporary download files
        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()
        if ext in self.ignored_extensions or filename.startswith("."):
            return

        # 3. Get the physical file identity (inode + device)
        identity = _get_file_identity(file_path)
        if identity is None:
            return

        # 4. Prevent duplicate processing of the same *physical* file
        with self.lock:
            self._cleanup_expired()

            # Check processed_files: same path AND same inode/device → duplicate event
            prev = self.processed_files.get(file_path)
            if prev is not None:
                _, prev_ino, prev_dev = prev
                if (prev_ino, prev_dev) == identity:
                    # Same physical file at same path – duplicate watchdog event
                    return
                # Different inode at same path – this is a new file (path reused
                # after a MOVE).  Remove stale entry and process the new file.
                del self.processed_files[file_path]

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
            last_size = -1
            stable_count = 0
            
            # Check up to 10 seconds for stability
            for _ in range(20):
                if not os.path.exists(file_path):
                    self.organizer.logger.debug(f"Stale event skipped. File no longer exists: {file_path}")
                    return
                    
                try:
                    current_size = os.path.getsize(file_path)
                except OSError:
                    self.organizer.logger.debug(f"Stale event skipped. Could not get size for: {file_path}")
                    return
                    
                if current_size == last_size:
                    stable_count += 1
                    if stable_count >= 2: # 1 second stable
                        stable = True
                        break
                else:
                    stable_count = 0
                    last_size = current_size
                    
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
            if current_identity is None:
                self.organizer.logger.debug(f"Stale event skipped. Cannot stat file: {file_path}")
                return

            with self.lock:
                self.processed_files[file_path] = (time.time(), current_identity[0], current_identity[1])
                
            # Notify the application/GUI about the new file
            self.on_new_file_callback(file_path)
        finally:
            with self.lock:
                self.pending_files.pop(file_path, None)

    def mark_as_unprocessed(self, file_path):
        """Allow re-processing if needed (e.g. on error)"""
        with self.lock:
            self.processed_files.pop(file_path, None)


class FileMonitor:
    def __init__(self, watch_path, organizer, on_new_file_callback):
        self.watch_path = watch_path
        self.organizer = organizer
        self.on_new_file_callback = on_new_file_callback
        self.observer = Observer()
        self.event_handler = DownloadHandler(self.organizer, self.on_new_file_callback)

    def start(self):
        self.observer.schedule(self.event_handler, self.watch_path, recursive=False)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        if self.observer.is_alive():
            self.observer.join()
