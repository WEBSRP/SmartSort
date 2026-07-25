import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from src.utils.paths import AppPaths

class SmartSortLogger:
    def __init__(self, log_dir="logs", retention_days=7):
        is_testing = "PYTEST_CURRENT_TEST" in os.environ
        
        if log_dir and Path(log_dir).is_absolute():
            self.log_dir = Path(log_dir)
        elif is_testing:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = AppPaths.logs_dir()
            
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger("SmartSort")
        self.logger.setLevel(logging.INFO)
        
        # Clear existing handlers to prevent duplicate message logs across instances or test executions
        self.logger.handlers.clear()
        
        log_file = self.log_dir / f"smartsort_{datetime.now().strftime('%Y%m%d')}.log"
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # Also log to console for development
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # Apply log retention policy
        self.cleanup_old_logs(retention_days)

    def cleanup_old_logs(self, retention_days):
        """Delete log files older than the specified retention period."""
        try:
            now = datetime.now()
            cutoff = now - timedelta(days=retention_days)
            for log_file in self.log_dir.glob("smartsort_*.log"):
                if log_file.is_file():
                    base = log_file.name
                    # Parse date from smartsort_YYYYMMDD.log
                    date_str = base.replace("smartsort_", "").replace(".log", "")
                    try:
                        file_date = datetime.strptime(date_str, "%Y%m%d")
                        if file_date < cutoff:
                            log_file.unlink(missing_ok=True)
                    except ValueError:
                        # Ignore malformed filenames
                        pass
        except Exception as e:
            # Silently catch exceptions to ensure log issues don't crash initialization
            print(f"Log retention cleanup encountered an error: {e}")

    def log_action(self, filename, source, destination, action, result="SUCCESS", error=""):
        msg = f"File: {filename} | Source: {source} | Dest: {destination} | Action: {action} | Result: {result}"
        if error:
            msg += f" | Error: {error}"
        self.logger.info(msg)

    def error(self, msg):
        self.logger.error(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def warn(self, msg):
        self.logger.warning(msg)

    def debug(self, msg):
        self.logger.debug(msg)
