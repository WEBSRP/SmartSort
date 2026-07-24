import os
import time
import threading
from src.monitor import FileMonitor
from src.organizer import FileOrganizer
from src.utils.config import ConfigManager
from src.utils.logger import SmartSortLogger

class DummyOrganizer(FileOrganizer):
    def __init__(self):
        self.logger = SmartSortLogger(log_dir="logs")
    def process_file(self, *args, **kwargs):
        print(f"process_file called with {args}")
        return "SUCCESS", "fake_path"

def on_new_file(path):
    print(f"CALLBACK TRIGGERED: {path}")

os.makedirs("test_downloads", exist_ok=True)
organizer = DummyOrganizer()
monitor = FileMonitor("test_downloads", organizer, on_new_file)
monitor.start()

print("1. Creating a file...")
with open("test_downloads/test1.txt", "w") as f:
    f.write("hello")
time.sleep(2)

print("2. Simulating rapid rename...")
with open("test_downloads/test2.txt", "w") as f:
    f.write("temp")
os.rename("test_downloads/test2.txt", "test_downloads/test3.txt")
time.sleep(2)

print("3. Simulating deleted file (stale event)...")
with open("test_downloads/test4.txt", "w") as f:
    f.write("delete_me")
# Delete it immediately before monitor can stabilize
os.remove("test_downloads/test4.txt")
time.sleep(2)

monitor.stop()
print("Test completed.")
