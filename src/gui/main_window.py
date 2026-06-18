import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, 
                             QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QTextEdit, QTableWidget, QTableWidgetItem, 
                             QFileDialog, QSpinBox, QCheckBox, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRunnable, QThreadPool, QObject
from PyQt6.QtGui import QIcon

from src.utils.config import ConfigManager
from src.utils.logger import SmartSortLogger
from src.organizer import FileOrganizer
from src.monitor import FileMonitor

class WorkerSignals(QObject):
    finished = pyqtSignal(str, str, str) # file_path, result, info
    error = pyqtSignal(str, str) # file_path, error_msg

class FileWorker(QRunnable):
    def __init__(self, organizer, file_path, user_approved=False):
        super().__init__()
        self.organizer = organizer
        self.file_path = file_path
        self.user_approved = user_approved
        self.signals = WorkerSignals()

    def run(self):
        try:
            result, info = self.organizer.process_file(self.file_path, self.user_approved)
            self.signals.finished.emit(self.file_path, result, info)
        except Exception as e:
            self.signals.error.emit(self.file_path, str(e))

class MonitorThread(QThread):
    new_file_signal = pyqtSignal(str)
    
    def __init__(self, watch_path, organizer):
        super().__init__()
        self.watch_path = watch_path
        self.organizer = organizer
        self.monitor = FileMonitor(self.watch_path, self.organizer, self.new_file_signal.emit)

    def run(self):
        self.monitor.start()
        self.exec() # Keep thread alive

    def stop(self):
        self.monitor.stop()
        self.quit()

    def get_handler(self):
        return self.monitor.event_handler

class SmartSortGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SmartSort - File Organizer")
        self.resize(800, 600)
        
        # Initialize Core
        self.config = ConfigManager(config_path="config/config.json", default_path="config/default_config.json")
        self.logger = SmartSortLogger()
        self.organizer = FileOrganizer(self.config, self.logger)
        self.threadpool = QThreadPool()
        
        self.stats = {"processed": 0, "duplicates": 0, "errors": 0}
        
        self.init_notification_system()
        self.init_ui()
        self.start_monitor()

    def init_notification_system(self):
        self.notifications_enabled = False
        try:
            import notify2
            notify2.init("SmartSort")
            self.notifications_enabled = True
        except Exception as e:
            print(f"Notifications disabled: {e}")

    def init_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.tab_dashboard = QWidget()
        self.tab_logs = QWidget()
        self.tab_rules = QWidget()
        self.tab_settings = QWidget()
        
        self.tabs.addTab(self.tab_dashboard, "Dashboard")
        self.tabs.addTab(self.tab_logs, "Logs")
        self.tabs.addTab(self.tab_rules, "Rules")
        self.tabs.addTab(self.tab_settings, "Settings")
        
        self.setup_dashboard()
        self.setup_logs()
        self.setup_settings()
        self.setup_rules()

    def setup_dashboard(self):
        layout = QVBoxLayout()
        self.lbl_status = QLabel("Status: Monitoring Downloads...")
        self.lbl_stats = QLabel("Files Processed: 0 | Duplicates: 0 | Errors: 0")
        
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.lbl_stats)
        layout.addWidget(QLabel("Recent Activity:"))
        layout.addWidget(self.log_display)
        
        self.tab_dashboard.setLayout(layout)

    def setup_logs(self):
        layout = QVBoxLayout()
        self.table_logs = QTableWidget(0, 5)
        self.table_logs.setHorizontalHeaderLabels(["Timestamp", "File", "Action", "Result", "Message"])
        layout.addWidget(self.table_logs)
        
        btn_refresh = QPushButton("Refresh Logs")
        btn_refresh.clicked.connect(self.refresh_logs)
        layout.addWidget(btn_refresh)
        
        self.tab_logs.setLayout(layout)

    def setup_rules(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Manage Categorization Rules (JSON Viewer/Editor)"))
        self.rules_edit = QTextEdit()
        import json
        self.rules_edit.setPlainText(json.dumps(self.config.get("categories"), indent=4))
        layout.addWidget(self.rules_edit)
        
        btn_save = QPushButton("Save Rules")
        btn_save.clicked.connect(self.save_rules)
        layout.addWidget(btn_save)
        self.tab_rules.setLayout(layout)

    def setup_settings(self):
        layout = QVBoxLayout()
        
        # Downloads Path
        h_down = QHBoxLayout()
        self.txt_downloads = QLabel(self.config.get("downloads_folder"))
        btn_browse_down = QPushButton("Browse")
        btn_browse_down.clicked.connect(self.browse_downloads)
        h_down.addWidget(QLabel("Downloads Folder:"))
        h_down.addWidget(self.txt_downloads)
        h_down.addWidget(btn_browse_down)
        layout.addLayout(h_down)
        
        # Threshold
        h_thresh = QHBoxLayout()
        self.spin_thresh = QSpinBox()
        self.spin_thresh.setValue(int(self.config.get("large_file_threshold_gb")))
        h_thresh.addWidget(QLabel("Large File Threshold (GB):"))
        h_thresh.addWidget(self.spin_thresh)
        layout.addLayout(h_thresh)
        
        # Toggles
        self.chk_notif = QCheckBox("Enable Notifications")
        self.chk_notif.setChecked(self.config.get("enable_notifications"))
        layout.addWidget(self.chk_notif)
        
        self.chk_dup = QCheckBox("Enable Duplicate Detection")
        self.chk_dup.setChecked(self.config.get("enable_duplicate_detection"))
        layout.addWidget(self.chk_dup)
        
        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self.save_settings)
        layout.addWidget(btn_save)
        
        self.tab_settings.setLayout(layout)

    def browse_downloads(self):
        path = QFileDialog.getExistingDirectory(self, "Select Downloads Folder")
        if path:
            self.txt_downloads.setText(path)

    def save_settings(self):
        self.config.set("downloads_folder", self.txt_downloads.text())
        self.config.set("large_file_threshold_gb", self.spin_thresh.value())
        self.config.set("enable_notifications", self.chk_notif.isChecked())
        self.config.set("enable_duplicate_detection", self.chk_dup.isChecked())
        QMessageBox.information(self, "Success", "Settings saved successfully!")

    def save_rules(self):
        try:
            import json
            rules = json.loads(self.rules_edit.toPlainText())
            self.config.set("categories", rules)
            QMessageBox.information(self, "Success", "Rules saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Invalid JSON: {str(e)}")

    def refresh_logs(self):
        log_dir = "logs"
        if not os.path.exists(log_dir):
            return
            
        # Get the latest log file
        log_files = sorted([f for f in os.listdir(log_dir) if f.startswith("smartsort_") and f.endswith(".log")], reverse=True)
        if not log_files:
            return
            
        log_path = os.path.join(log_dir, log_files[0])
        
        try:
            with open(log_path, 'r') as f:
                lines = f.readlines()
            
            self.table_logs.setRowCount(0)
            for line in lines:
                if " - INFO - File: " in line:
                    parts = line.split(" - INFO - ")
                    timestamp = parts[0]
                    content = parts[1]
                    
                    # Parse content: File: {filename} | Source: {source} | Dest: {destination} | Action: {action} | Result: {result}
                    data = {}
                    for item in content.split(" | "):
                        if ":" in item:
                            k, v = item.split(":", 1)
                            data[k.strip()] = v.strip()
                    
                    row = self.table_logs.rowCount()
                    self.table_logs.insertRow(row)
                    self.table_logs.setItem(row, 0, QTableWidgetItem(timestamp))
                    self.table_logs.setItem(row, 1, QTableWidgetItem(data.get("File", "")))
                    self.table_logs.setItem(row, 2, QTableWidgetItem(data.get("Action", "")))
                    self.table_logs.setItem(row, 3, QTableWidgetItem(data.get("Result", "")))
                    
                    msg = data.get("Error", "")
                    self.table_logs.setItem(row, 4, QTableWidgetItem(msg))
                    
            self.table_logs.resizeColumnsToContents()
        except Exception as e:
            print(f"Error reading logs: {e}")

    def start_monitor(self):
        watch_path = self.config.get("downloads_folder")
        if not os.path.exists(watch_path):
            QMessageBox.warning(self, "Warning", f"Downloads folder not found: {watch_path}")
            return
            
        self.monitor_thread = MonitorThread(watch_path, self.organizer)
        self.monitor_thread.new_file_signal.connect(self.handle_new_file)
        self.monitor_thread.start()

    def handle_new_file(self, file_path):
        # This is called from the monitor thread (via signal)
        self.log_display.append(f"Detected: {os.path.basename(file_path)}")
        self.start_file_worker(file_path)

    def start_file_worker(self, file_path, user_approved=False):
        worker = FileWorker(self.organizer, file_path, user_approved)
        worker.signals.finished.connect(self.on_worker_finished)
        worker.signals.error.connect(self.on_worker_error)
        self.threadpool.start(worker)

    def update_stats(self, category):
        self.stats[category] += 1
        self.lbl_stats.setText(f"Files Processed: {self.stats['processed']} | "
                               f"Duplicates: {self.stats['duplicates']} | "
                               f"Errors: {self.stats['errors']}")

    def on_worker_finished(self, file_path, result, info):
        filename = os.path.basename(file_path)
        if result == "AWAIT_APPROVAL":
            self.ask_approval(file_path, info)
        elif result == "SUCCESS":
            self.update_stats("processed")
            self.log_display.append(f"Moved {filename} to: {info}")
            if self.config.get("enable_notifications"):
                self.show_notification("File Organized", f"{filename} moved to {info}")
            self.refresh_logs()
        elif result == "DUPLICATE":
            self.update_stats("duplicates")
            self.log_display.append(f"Duplicate found for {filename} at: {info}")
            QMessageBox.information(self, "Duplicate Detected", f"A matching file already exists:\n{info}")
        elif result == "SKIPPED":
            self.log_display.append(f"Skipped: {filename} ({info})")
        elif result == "ERROR":
            self.update_stats("errors")
            self.log_display.append(f"Error processing {filename}: {info}")
            if hasattr(self, 'monitor_thread'):
                self.monitor_thread.get_handler().mark_as_unprocessed(file_path)

    def on_worker_error(self, file_path, error_msg):
        self.log_display.append(f"Critical error processing {os.path.basename(file_path)}: {error_msg}")
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.get_handler().mark_as_unprocessed(file_path)

    def ask_approval(self, file_path, dest_path):
        filename = os.path.basename(file_path)
        size_gb = os.path.getsize(file_path) / (1024**3)
        msg = f"Large file detected:\n{filename}\nSize: {size_gb:.2f} GB\n\nMove to {dest_path}?"
        
        reply = QMessageBox.question(self, "Large File Approval", msg, 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.start_file_worker(file_path, user_approved=True)

    def show_notification(self, title, message):
        if not self.notifications_enabled:
            return
        try:
            import notify2
            n = notify2.Notification(title, message)
            n.show()
        except:
            pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SmartSortGUI()
    window.show()
    sys.exit(app.exec())
