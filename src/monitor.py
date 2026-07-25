import os
import threading
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger("SmartSort")

class DownloadHandler(FileSystemEventHandler):
    def __init__(self, organizer, on_new_file_callback):
        self.organizer = organizer
        self.on_new_file_callback = on_new_file_callback
        # Added .tmp, .opdownload for Chromium-based browsers
        self.ignored_extensions = [".crdownload", ".part", ".tmp", ".opdownload"]
        self.processed_files = {} # path -> timestamp
        self.pending_files = set() # paths currently being stability checked
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
        expired = [path for path, timestamp in self.processed_files.items() if now - timestamp > expiry_limit]
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

        # 3. Prevent duplicate processing of the same file path in a short window
        with self.lock:
            self._cleanup_expired()
            if file_path in self.processed_files or file_path in self.pending_files:
                return
            self.pending_files.add(file_path)

        # 4. Start a thread to check for stability and then process
        threading.Thread(target=self._wait_and_process, args=(file_path,), daemon=True).start()

    def _wait_and_process(self, file_path):
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
                
            with self.lock:
                self.processed_files[file_path] = time.time()
                
            # Notify the application/GUI about the new file
            self.on_new_file_callback(file_path)
        finally:
            with self.lock:
                self.pending_files.discard(file_path)

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
