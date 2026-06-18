import logging
import os
from datetime import datetime

class SmartSortLogger:
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        self.logger = logging.getLogger("SmartSort")
        self.logger.setLevel(logging.INFO)
        
        log_file = os.path.join(log_dir, f"smartsort_{datetime.now().strftime('%Y%m%d')}.log")
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # Also log to console for development
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def log_action(self, filename, source, destination, action, result="SUCCESS", error=""):
        msg = f"File: {filename} | Source: {source} | Dest: {destination} | Action: {action} | Result: {result}"
        if error:
            msg += f" | Error: {error}"
        self.logger.info(msg)

    def error(self, msg):
        self.logger.error(msg)

    def info(self, msg):
        self.logger.info(msg)
