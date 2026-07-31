import os
import time
from pathlib import Path
from typing import Tuple, Union
from .utils.file_utils import FileUtils
from .utils.config import ConfigManager
from .utils.logger import SmartSortLogger
from src.rules.manager import RuleManager
from src.rules.engine import RuleEngine
from src.core.filename_cleanup import FilenameCleanup
from src.core.notifications import NotificationManager

class FileOrganizer:
    def __init__(self, config_manager: ConfigManager, logger: SmartSortLogger):
        self.config = config_manager
        self.logger = logger
        self.rule_manager = RuleManager(config_manager)
        self.notification_manager = NotificationManager(config_manager, logger)
        self.filename_cleanup = FilenameCleanup(
            enabled=config_manager.get("smart_filename_cleanup", False),
            min_length=config_manager.get("filename_min_length", 4),
            max_length=config_manager.get("filename_max_length", 80),
        )

    def get_category(self, file_path: str) -> str:
        engine = RuleEngine(self.rule_manager.rules)
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            file_size = None
        rule, _ = engine.evaluate_file(file_path, file_size)
        if rule:
            return rule.name
        return "Others"

    def get_destination_path(self, file_path: str, category: str = None, override_filename: str = None) -> str:
        engine = RuleEngine(self.rule_manager.rules)
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            file_size = None
        rule, relative_dest = engine.evaluate_file(file_path, file_size)
        
        original_filename = os.path.basename(file_path)
        filename = override_filename or original_filename
        if rule and "{filename}" in rule.destination:
            # If an override filename is provided, replace the already-expanded
            # original filename in the destination path with the clean name.
            if override_filename and original_filename in relative_dest:
                relative_dest = relative_dest.replace(original_filename, filename, 1)
        else:
            relative_dest = os.path.join(relative_dest, filename)
            
        base_dest = Path(self.config.get("destination_base", os.path.expanduser("~"))).expanduser().resolve()
        dest_path = (base_dest / relative_dest).resolve(strict=False)
        if os.path.commonpath([str(base_dest), str(dest_path)]) != str(base_dest):
            raise ValueError(f"Destination escapes configured base directory: {relative_dest}")
        return str(dest_path)

    def process_file(self, file_path: str, user_approved: bool = False) -> Tuple[str, str]:
        """
        Process a single file: categorize, determine dest, safe copy, delete original.
        Returns (Status, Info)
        """
        if not os.path.exists(file_path):
            return "SKIPPED", "File already processed or removed"

        # Smart Filename Cleanup (evaluated before categorization)
        override_filename = None
        original_basename = os.path.basename(file_path)
        if self.filename_cleanup.needs_cleanup(original_basename):
            clean_name = self.filename_cleanup.generate_clean_name(file_path)
            override_filename = clean_name
            self.logger.info(
                f"Smart Cleanup: '{original_basename}' → '{clean_name}'"
            )

        category = self.get_category(file_path)
        try:
            dest_path = self.get_destination_path(file_path, category, override_filename=override_filename)
        except ValueError as e:
            return "ERROR", str(e)
        filename = os.path.basename(file_path)

        # Check for large video approval
        if "Videos" in category or category.startswith("Videos"):
            try:
                file_size = os.path.getsize(file_path)
                threshold_bytes = self.config.get("large_file_threshold_gb")
                
                # Fallback to GB if threshold is legacy float/int < 10000
                if isinstance(threshold_bytes, (int, float)) and threshold_bytes < 10000:
                    threshold_bytes = int(threshold_bytes * (1024**3))
                elif threshold_bytes is None:
                    threshold_bytes = int(2.5 * (1024**3))
                    
                if file_size >= threshold_bytes and not user_approved:
                    # Trigger GUI/Notification for approval
                    return "AWAIT_APPROVAL", dest_path
            except OSError as e:
                self.logger.error(f"Failed to check size of {file_path}: {e}")
                return "ERROR", f"Failed to access file: {str(e)}"

        # Duplicate and Collision Detection
        if os.path.exists(dest_path):
            if self.config.get("enable_duplicate_detection", True):
                src_hash = FileUtils.calculate_sha256(file_path)
                dst_hash = FileUtils.calculate_sha256(dest_path)
                if src_hash is not None and src_hash == dst_hash:
                    self.logger.log_action(filename, file_path, dest_path, "SKIP_DUPLICATE", "SKIP")
                    return "DUPLICATE", dest_path
            
            # Destination file exists but either hashes differ or duplicate detection is disabled
            conflict_policy = self.config.get("conflict_resolution", "rename")
            if conflict_policy == "rename":
                dest_path = FileUtils.get_unique_path(dest_path)
            elif conflict_policy == "overwrite":
                pass # let it overwrite in safe_copy
            else: # "skip" or other unrecognized conflict policy
                self.logger.log_action(filename, file_path, dest_path, "SKIP_COLLISION", "SKIP")
                return "SKIPPED", f"Destination file already exists: {dest_path}"

        # Safe Transfer
        success, info = FileUtils.safe_copy(file_path, dest_path)
        if success:
            try:
                os.remove(file_path)
                self.logger.log_action(filename, file_path, dest_path, "TRANSFER_SUCCESS")
                try:
                    self.notification_manager.send_success_notification(dest_path)
                except Exception as notif_err:
                    self.logger.error(f"Notification error ignored during sorting: {notif_err}")
                return "SUCCESS", dest_path
            except Exception as e:
                self.logger.log_action(filename, file_path, dest_path, "DELETE_ORIGINAL_FAILED", "ERROR", str(e))
                return "ERROR", f"Failed to delete source: {str(e)}"
        else:
            self.logger.log_action(filename, file_path, dest_path, "COPY_FAILED", "ERROR", info)
            return "ERROR", info

