import os
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class DownloadHandler(FileSystemEventHandler):
    def __init__(self, organizer, on_new_file_callback):
        self.organizer = organizer
        self.on_new_file_callback = on_new_file_callback
        # Added .tmp, .opdownload for Chromium-based browsers
        self.ignored_extensions = [".crdownload", ".part", ".tmp", ".opdownload"]
        self.processed_files = set()
        self.lock = threading.Lock()

    def on_created(self, event):
        if not event.is_directory:
            self._handle_event(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle_event(event.dest_path)

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
            if file_path in self.processed_files:
                return
            self.processed_files.add(file_path)
            # Remove from set after a delay or after success? 
            # For now, just keep it to prevent re-triggering during the same session
            # if the file is moved out, the path is no longer relevant anyway.

        # Notify the application/GUI about the new file
        self.on_new_file_callback(file_path)

    def mark_as_unprocessed(self, file_path):
        """Allow re-processing if needed (e.g. on error)"""
        with self.lock:
            if file_path in self.processed_files:
                self.processed_files.remove(file_path)

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
        self.observer.join()
