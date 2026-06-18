import os
import time
from typing import Tuple, Union
from .utils.file_utils import FileUtils
from .utils.config import ConfigManager
from .utils.logger import SmartSortLogger

class FileOrganizer:
    def __init__(self, config_manager: ConfigManager, logger: SmartSortLogger):
        self.config = config_manager
        self.logger = logger

    def get_category(self, file_path: str) -> str:
        filename = os.path.basename(file_path).lower()
        ext = os.path.splitext(filename)[1].lower()
        categories = self.config.get("categories", {})

        # Priority: Keywords (Cybersecurity, College)
        for cat, data in categories.items():
            if "keywords" in data:
                for keyword in data["keywords"]:
                    if keyword in filename:
                        return cat

        # Then: Extensions
        for cat, data in categories.items():
            if "extensions" in data:
                if ext in data["extensions"]:
                    return cat

        return "Others"

    def get_destination_path(self, file_path: str, category: str) -> str:
        base_dest = self.config.get("destination_base", os.path.expanduser("~"))
        filename = os.path.basename(file_path)
        
        # Special handling for Videos (Big/Small)
        if category == "Videos":
            size_gb = os.path.getsize(file_path) / (1024**3)
            threshold = self.config.get("large_file_threshold_gb", 2.5)
            video_config = self.config.get("categories", {}).get("Videos", {})
            subfolders = video_config.get("subfolders", {})
            
            if size_gb >= threshold:
                relative_path = subfolders.get("Big_Videos", "Videos/Big_Videos")
            else:
                relative_path = subfolders.get("Small_Videos", "Videos")
            
            return os.path.join(base_dest, relative_path, filename)

        # Default mapping for other categories
        category_relative_paths = {
            "Documents": "Documents",
            "Archives": "Archives",
            "Disk Images": "ISO",
            "Images": "Pictures",
            "Cybersecurity": "Cybersecurity",
            "College": "Documents/College",
            "Others": "Others"
        }
        
        relative_path = category_relative_paths.get(category, category)
        return os.path.join(base_dest, relative_path, filename)

    def process_file(self, file_path: str, user_approved: bool = False) -> Tuple[str, str]:
        """
        Process a single file: categorize, determine dest, safe copy, delete original.
        Returns (Status, Info)
        """
        if not os.path.exists(file_path):
            return "SKIPPED", "File already processed or removed"

        # Wait for file to be ready (not changing size)
        last_size = -1
        retries = 0
        max_retries = 60 # 1 minute max wait
        while retries < max_retries:
            if not os.path.exists(file_path):
                return "SKIPPED", "File disappeared during readiness check"
            try:
                current_size = os.path.getsize(file_path)
                # If size is 0, we should wait as it might be just started
                if current_size == last_size and current_size > 0:
                    break
                last_size = current_size
                time.sleep(1)
                retries += 1
            except OSError:
                return "ERROR", "File access error during readiness check"
        
        if retries == max_retries:
            return "ERROR", "File never became ready (size still changing or zero)"

        category = self.get_category(file_path)
        dest_path = self.get_destination_path(file_path, category)
        filename = os.path.basename(file_path)

        # Final existence check before critical operations
        if not os.path.exists(file_path):
            return "SKIPPED", "File disappeared before transfer"

        # Check for large video approval
        if category == "Videos":
            size_gb = os.path.getsize(file_path) / (1024**3)
            threshold = self.config.get("large_file_threshold_gb", 2.5)
            if size_gb >= threshold and not user_approved:
                # Trigger GUI/Notification for approval
                return "AWAIT_APPROVAL", dest_path

        # Duplicate detection
        if self.config.get("enable_duplicate_detection", True) and os.path.exists(dest_path):
            src_hash = FileUtils.calculate_sha256(file_path)
            dst_hash = FileUtils.calculate_sha256(dest_path)
            if src_hash == dst_hash:
                self.logger.log_action(filename, file_path, dest_path, "SKIP_DUPLICATE", "SKIP")
                return "DUPLICATE", dest_path

        # Safe Transfer
        success, info = FileUtils.safe_copy(file_path, dest_path)
        if success:
            try:
                os.remove(file_path)
                self.logger.log_action(filename, file_path, dest_path, "TRANSFER_SUCCESS")
                return "SUCCESS", dest_path
            except Exception as e:
                self.logger.log_action(filename, file_path, dest_path, "DELETE_ORIGINAL_FAILED", "ERROR", str(e))
                return "ERROR", f"Failed to delete source: {str(e)}"
        else:
            self.logger.log_action(filename, file_path, dest_path, "COPY_FAILED", "ERROR", info)
            return "ERROR", info
