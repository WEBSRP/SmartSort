import sys
import os
import re
import uuid
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, 
                             QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QTextEdit, QTableWidget, QTableWidgetItem, 
                             QFileDialog, QSpinBox, QCheckBox, QMessageBox,
                             QFormLayout, QGroupBox, QLineEdit, QComboBox, 
                             QDialog, QDialogButtonBox)
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
            if result == "ERROR":
                self.organizer.logger.error(f"Error processing {self.file_path}: {info}")
            self.signals.finished.emit(self.file_path, result, info)
        except Exception as e:
            self.organizer.logger.error(f"Critical exception in FileWorker for {self.file_path}: {str(e)}")
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
        self.tab_tester = QWidget()
        
        self.tabs.addTab(self.tab_dashboard, "Dashboard")
        self.tabs.addTab(self.tab_logs, "Logs")
        self.tabs.addTab(self.tab_rules, "Rules")
        self.tabs.addTab(self.tab_settings, "Settings")
        self.tabs.addTab(self.tab_tester, "Rule Tester")
        
        self.setup_dashboard()
        self.setup_logs()
        self.setup_settings()
        self.setup_rules()
        self.setup_tester()

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
        layout = QHBoxLayout()
        
        # Table of rules
        self.table_rules = QTableWidget(0, 4)
        self.table_rules.setHorizontalHeaderLabels(["Name", "Priority", "Enabled", "Destination"])
        self.table_rules.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_rules.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table_rules)
        
        # Buttons layout
        btn_layout = QVBoxLayout()
        self.btn_add_rule = QPushButton("Add")
        self.btn_edit_rule = QPushButton("Edit")
        self.btn_delete_rule = QPushButton("Delete")
        self.btn_move_up = QPushButton("Move Up")
        self.btn_move_down = QPushButton("Move Down")
        self.btn_enable_rule = QPushButton("Enable")
        self.btn_disable_rule = QPushButton("Disable")
        
        self.btn_add_rule.clicked.connect(self.add_rule_clicked)
        self.btn_edit_rule.clicked.connect(self.edit_rule_clicked)
        self.btn_delete_rule.clicked.connect(self.delete_rule_clicked)
        self.btn_move_up.clicked.connect(self.move_rule_up)
        self.btn_move_down.clicked.connect(self.move_rule_down)
        self.btn_enable_rule.clicked.connect(self.enable_rule_clicked)
        self.btn_disable_rule.clicked.connect(self.disable_rule_clicked)
        
        btn_layout.addWidget(self.btn_add_rule)
        btn_layout.addWidget(self.btn_edit_rule)
        btn_layout.addWidget(self.btn_delete_rule)
        btn_layout.addWidget(self.btn_move_up)
        btn_layout.addWidget(self.btn_move_down)
        btn_layout.addWidget(self.btn_enable_rule)
        btn_layout.addWidget(self.btn_disable_rule)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        self.tab_rules.setLayout(layout)
        self.refresh_rules_table()

    def bytes_to_human_string(self, num_bytes: int) -> str:
        if num_bytes is None:
            return "2.5GB"
        num_bytes = int(num_bytes)
        if num_bytes < 10000:
            num_bytes = int(num_bytes * (1024**3))
            
        if num_bytes >= 1024**3:
            val = num_bytes / (1024**3)
            return f"{int(val)}GB" if val.is_integer() else f"{val:.2f}GB"
        elif num_bytes >= 1024**2:
            val = num_bytes / (1024**2)
            return f"{int(val)}MB" if val.is_integer() else f"{val:.2f}MB"
        elif num_bytes >= 1024:
            val = num_bytes / 1024
            return f"{int(val)}KB" if val.is_integer() else f"{val:.2f}KB"
        else:
            return f"{num_bytes}B"

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
        self.txt_thresh = QLineEdit()
        self.txt_thresh.setPlaceholderText("Examples: 500MB, 1.5GB, 2GB")
        
        current_bytes = self.config.get("large_file_threshold_gb")
        if isinstance(current_bytes, (int, float)) and current_bytes < 10000:
            current_bytes = int(current_bytes * (1024**3))
        self.txt_thresh.setText(self.bytes_to_human_string(current_bytes))
        
        h_thresh.addWidget(QLabel("Large File Threshold:"))
        h_thresh.addWidget(self.txt_thresh)
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
        thresh_str = self.txt_thresh.text().strip()
        if not thresh_str:
            QMessageBox.critical(self, "Error", "Large File Threshold cannot be empty")
            return
            
        try:
            from src.rules.conditions import parse_size_to_bytes
            bytes_val = parse_size_to_bytes(thresh_str)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Invalid Large File Threshold: {str(e)}")
            return
            
        try:
            self.config.set("downloads_folder", self.txt_downloads.text())
            self.config.set("large_file_threshold_gb", bytes_val)
            self.config.set("enable_notifications", self.chk_notif.isChecked())
            self.config.set("enable_duplicate_detection", self.chk_dup.isChecked())
            QMessageBox.information(self, "Success", "Settings saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")

    def refresh_rules_table(self):
        self.table_rules.setRowCount(0)
        rules = self.organizer.rule_manager.rules
        for r in rules:
            row = self.table_rules.rowCount()
            self.table_rules.insertRow(row)
            
            name_item = QTableWidgetItem(r.name)
            name_item.setData(Qt.ItemDataRole.UserRole, r.id)
            
            self.table_rules.setItem(row, 0, name_item)
            self.table_rules.setItem(row, 1, QTableWidgetItem(str(r.priority)))
            self.table_rules.setItem(row, 2, QTableWidgetItem("Yes" if r.enabled else "No"))
            self.table_rules.setItem(row, 3, QTableWidgetItem(r.destination))
            
        self.table_rules.resizeColumnsToContents()

    def get_selected_rule_id(self) -> str:
        selected_ranges = self.table_rules.selectedRanges()
        if not selected_ranges:
            return ""
        row = selected_ranges[0].topRow()
        item = self.table_rules.item(row, 0)
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return ""

    def move_rule_up(self):
        rule_id = self.get_selected_rule_id()
        if not rule_id:
            return
        rules = self.organizer.rule_manager.rules
        idx = next((i for i, r in enumerate(rules) if r.id == rule_id), -1)
        if idx > 0:
            rules[idx].priority, rules[idx - 1].priority = rules[idx - 1].priority, rules[idx].priority
            try:
                self.organizer.rule_manager.save_rules(rules)
                self.refresh_rules_table()
                self.select_rule_by_id(rule_id)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not move rule: {str(e)}")

    def move_rule_down(self):
        rule_id = self.get_selected_rule_id()
        if not rule_id:
            return
        rules = self.organizer.rule_manager.rules
        idx = next((i for i, r in enumerate(rules) if r.id == rule_id), -1)
        if idx >= 0 and idx < len(rules) - 1:
            rules[idx].priority, rules[idx + 1].priority = rules[idx + 1].priority, rules[idx].priority
            try:
                self.organizer.rule_manager.save_rules(rules)
                self.refresh_rules_table()
                self.select_rule_by_id(rule_id)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not move rule: {str(e)}")

    def select_rule_by_id(self, rule_id):
        for row in range(self.table_rules.rowCount()):
            item = self.table_rules.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == rule_id:
                self.table_rules.selectRow(row)
                break

    def enable_rule_clicked(self):
        rule_id = self.get_selected_rule_id()
        if not rule_id:
            return
        rules = self.organizer.rule_manager.rules
        rule = next((r for r in rules if r.id == rule_id), None)
        if rule:
            rule.enabled = True
            try:
                self.organizer.rule_manager.save_rules(rules)
                self.refresh_rules_table()
                self.select_rule_by_id(rule_id)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not enable rule: {str(e)}")

    def disable_rule_clicked(self):
        rule_id = self.get_selected_rule_id()
        if not rule_id:
            return
        rules = self.organizer.rule_manager.rules
        rule = next((r for r in rules if r.id == rule_id), None)
        if rule:
            rule.enabled = False
            try:
                self.organizer.rule_manager.save_rules(rules)
                self.refresh_rules_table()
                self.select_rule_by_id(rule_id)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not disable rule: {str(e)}")

    def add_rule_clicked(self):
        rules = self.organizer.rule_manager.rules
        existing_priorities = {r.priority for r in rules}
        
        dialog = RuleDialog(self, existing_priorities=existing_priorities)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.organizer.rule_manager.add_rule(dialog.result_rule)
                self.refresh_rules_table()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save rule: {str(e)}")

    def edit_rule_clicked(self):
        rule_id = self.get_selected_rule_id()
        if not rule_id:
            QMessageBox.warning(self, "Warning", "Please select a rule to edit.")
            return
            
        rules = self.organizer.rule_manager.rules
        rule = next((r for r in rules if r.id == rule_id), None)
        if not rule:
            return
            
        existing_priorities = {r.priority for r in rules}
        dialog = RuleDialog(self, rule=rule, existing_priorities=existing_priorities)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.organizer.rule_manager.update_rule(dialog.result_rule)
                self.refresh_rules_table()
                self.select_rule_by_id(rule_id)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save rule: {str(e)}")

    def delete_rule_clicked(self):
        rule_id = self.get_selected_rule_id()
        if not rule_id:
            QMessageBox.warning(self, "Warning", "Please select a rule to delete.")
            return
            
        reply = QMessageBox.question(self, "Confirm Delete", "Are you sure you want to delete this rule?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.organizer.rule_manager.delete_rule(rule_id)
                self.refresh_rules_table()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete rule: {str(e)}")

    def setup_tester(self):
        layout = QVBoxLayout()
        form = QFormLayout()
        
        self.txt_test_filename = QLineEdit("wallpaper.jpg")
        self.txt_test_size = QLineEdit("1.2MB")
        self.txt_test_size.setPlaceholderText("e.g. 1.2MB, 500KB, 2.5GB")
        
        self.txt_test_ext = QLineEdit(".jpg")
        self.txt_test_ext.setPlaceholderText("e.g. .jpg, .png (optional)")
        
        form.addRow("Filename:", self.txt_test_filename)
        form.addRow("File Size:", self.txt_test_size)
        form.addRow("Extension:", self.txt_test_ext)
        
        layout.addLayout(form)
        
        btn_test = QPushButton("Test Rule Matching")
        btn_test.clicked.connect(self.run_rule_test)
        layout.addWidget(btn_test)
        
        group = QGroupBox("Test Output")
        g_layout = QFormLayout()
        
        self.lbl_test_match = QLabel("None")
        self.lbl_test_priority = QLabel("N/A")
        self.lbl_test_dest = QLabel("N/A")
        
        g_layout.addRow("Matched Rule:", self.lbl_test_match)
        g_layout.addRow("Priority:", self.lbl_test_priority)
        g_layout.addRow("Destination:", self.lbl_test_dest)
        
        group.setLayout(g_layout)
        layout.addWidget(group)
        layout.addStretch()
        
        self.tab_tester.setLayout(layout)

    def run_rule_test(self):
        filename = self.txt_test_filename.text().strip()
        size_str = self.txt_test_size.text().strip()
        ext = self.txt_test_ext.text().strip()
        
        if not filename:
            QMessageBox.critical(self, "Error", "Filename cannot be empty")
            return
            
        file_size = 0
        if size_str:
            try:
                from src.rules.conditions import parse_size_to_bytes
                file_size = parse_size_to_bytes(size_str)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Invalid size format: {str(e)}")
                return
                
        if ext and not filename.lower().endswith(ext.lower()):
            eval_path = filename + (ext if ext.startswith(".") else "." + ext)
        else:
            eval_path = filename
            
        from src.rules.engine import RuleEngine
        engine = RuleEngine(self.organizer.rule_manager.rules)
        rule, dest = engine.evaluate_file(eval_path, file_size)
        
        if rule:
            self.lbl_test_match.setText(rule.name)
            self.lbl_test_priority.setText(str(rule.priority))
        else:
            self.lbl_test_match.setText("None (Fallback Rule)")
            self.lbl_test_priority.setText("N/A")
            
        self.lbl_test_dest.setText(dest)

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
            if self.config.get("enable_notifications"):
                self.show_notification("SmartSort Error", f"Failed to organize {filename}: {info}")
            if hasattr(self, 'monitor_thread'):
                self.monitor_thread.get_handler().mark_as_unprocessed(file_path)

    def on_worker_error(self, file_path, error_msg):
        self.log_display.append(f"Critical error processing {os.path.basename(file_path)}: {error_msg}")
        if self.config.get("enable_notifications"):
            self.show_notification("SmartSort Critical Error", f"Error organizing {os.path.basename(file_path)}: {error_msg}")
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

class RuleDialog(QDialog):
    def __init__(self, parent=None, rule=None, existing_priorities=None):
        super().__init__(parent)
        self.rule = rule
        self.existing_priorities = existing_priorities or set()
        if self.rule:
            self.setWindowTitle("Edit Rule")
        else:
            self.setWindowTitle("Add Rule")
            
        self.init_ui()
        if self.rule:
            self.load_rule_data()
            
    def init_ui(self):
        layout = QVBoxLayout()
        form = QFormLayout()
        
        self.txt_name = QLineEdit()
        self.spin_priority = QSpinBox()
        self.spin_priority.setRange(0, 9999)
        if not self.rule:
            max_p = max(self.existing_priorities) if self.existing_priorities else 0
            self.spin_priority.setValue(max_p + 1)
            
        self.chk_enabled = QCheckBox()
        self.chk_enabled.setChecked(True)
        
        self.txt_dest = QLineEdit()
        self.txt_dest.textChanged.connect(self.update_preview)
        
        self.lbl_preview = QLabel("Preview: (Enter a destination template)")
        
        form.addRow("Rule Name:", self.txt_name)
        form.addRow("Priority:", self.spin_priority)
        form.addRow("Enabled:", self.chk_enabled)
        form.addRow("Destination Template:", self.txt_dest)
        form.addRow("Destination Preview:", self.lbl_preview)
        
        layout.addLayout(form)
        
        group = QGroupBox("Conditions (AND logic between checked conditions)")
        g_layout = QVBoxLayout()
        
        h1 = QHBoxLayout()
        self.chk_cond_ext = QCheckBox("Extension matching:")
        self.txt_cond_ext = QLineEdit()
        self.txt_cond_ext.setPlaceholderText(".jpg, .png, .gif (comma separated)")
        h1.addWidget(self.chk_cond_ext)
        h1.addWidget(self.txt_cond_ext)
        g_layout.addLayout(h1)
        
        h2 = QHBoxLayout()
        self.chk_cond_fn = QCheckBox("Filename contains:")
        self.txt_cond_fn = QLineEdit()
        self.txt_cond_fn.setPlaceholderText("assignment, wireshark (comma separated)")
        h2.addWidget(self.chk_cond_fn)
        h2.addWidget(self.txt_cond_fn)
        g_layout.addLayout(h2)
        
        h3 = QHBoxLayout()
        self.chk_cond_size = QCheckBox("File Size condition:")
        self.combo_size_op = QComboBox()
        self.combo_size_op.addItems([">", "<", ">=", "<=", "=="])
        self.txt_cond_size = QLineEdit()
        self.txt_cond_size.setPlaceholderText("2.5GB, 100KB")
        h3.addWidget(self.chk_cond_size)
        h3.addWidget(self.combo_size_op)
        h3.addWidget(self.txt_cond_size)
        g_layout.addLayout(h3)
        
        h4 = QHBoxLayout()
        self.chk_cond_regex = QCheckBox("Regex Match:")
        self.txt_cond_regex = QLineEdit()
        self.txt_cond_regex.setPlaceholderText("^IMG_.*\\.png$")
        h4.addWidget(self.chk_cond_regex)
        h4.addWidget(self.txt_cond_regex)
        g_layout.addLayout(h4)
        
        group.setLayout(g_layout)
        layout.addWidget(group)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.save_clicked)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
        self.setLayout(layout)
        self.update_preview()

    def update_preview(self):
        template = self.txt_dest.text().strip()
        if not template:
            self.lbl_preview.setText("Preview: (Empty destination)")
            return
        placeholders = re.findall(r'\{([^}]+)\}', template)
        allowed = {"extension", "filename"}
        for p in placeholders:
            if p not in allowed:
                self.lbl_preview.setText(f"Preview: ERROR (Invalid placeholder {{{p}}})")
                return
        
        example_ext = "JPG"
        example_fn = "wallpaper.jpg"
        preview_text = template.replace("{extension}", example_ext).replace("{filename}", example_fn)
        self.lbl_preview.setText(f"Preview: {preview_text} (using example 'wallpaper.jpg')")

    def load_rule_data(self):
        self.txt_name.setText(self.rule.name)
        self.spin_priority.setValue(self.rule.priority)
        self.chk_enabled.setChecked(self.rule.enabled)
        self.txt_dest.setText(self.rule.destination)
        
        from src.rules.conditions import ExtensionCondition, FilenameContainsCondition, SizeCondition, RegexCondition
        for c in self.rule.conditions:
            if isinstance(c, ExtensionCondition):
                self.chk_cond_ext.setChecked(True)
                self.txt_cond_ext.setText(", ".join(c.extensions))
            elif isinstance(c, FilenameContainsCondition):
                self.chk_cond_fn.setChecked(True)
                self.txt_cond_fn.setText(", ".join(c.substrings))
            elif isinstance(c, SizeCondition):
                self.chk_cond_size.setChecked(True)
                self.combo_size_op.setCurrentText(c.operator)
                self.txt_cond_size.setText(c.value_str)
            elif isinstance(c, RegexCondition):
                self.chk_cond_regex.setChecked(True)
                self.txt_cond_regex.setText(c.pattern_str)
        self.update_preview()

    def save_clicked(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.critical(self, "Error", "Rule name cannot be empty")
            return
            
        priority = self.spin_priority.value()
        current_priority = self.rule.priority if self.rule else None
        if priority in self.existing_priorities and priority != current_priority:
            QMessageBox.critical(self, "Error", f"Priority {priority} is already assigned to another rule. Priority values must be unique.")
            return
            
        destination = self.txt_dest.text().strip()
        if not destination:
            QMessageBox.critical(self, "Error", "Destination cannot be empty")
            return
            
        placeholders = re.findall(r'\{([^}]+)\}', destination)
        for p in placeholders:
            if p not in {"extension", "filename"}:
                QMessageBox.critical(self, "Error", f"Invalid placeholder: {{{p}}}. Only {{extension}} and {{filename}} are allowed.")
                return

        conditions = []
        
        if self.chk_cond_ext.isChecked():
            val = self.txt_cond_ext.text().strip()
            if not val:
                QMessageBox.critical(self, "Error", "Extension condition is checked but empty")
                return
            exts = [e.strip() for e in val.split(",") if e.strip()]
            conditions.append({"type": "extension", "value": exts})
            
        if self.chk_cond_fn.isChecked():
            val = self.txt_cond_fn.text().strip()
            if not val:
                QMessageBox.critical(self, "Error", "Filename contains condition is checked but empty")
                return
            substrings = [s.strip() for s in val.split(",") if s.strip()]
            conditions.append({"type": "filename", "value": substrings})
            
        if self.chk_cond_size.isChecked():
            val = self.txt_cond_size.text().strip()
            if not val:
                QMessageBox.critical(self, "Error", "Size condition is checked but empty")
                return
            try:
                from src.rules.conditions import parse_size_to_bytes
                parse_size_to_bytes(val)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Invalid size format: {str(e)}")
                return
            conditions.append({"type": "size", "operator": self.combo_size_op.currentText(), "value": val})
            
        if self.chk_cond_regex.isChecked():
            val = self.txt_cond_regex.text().strip()
            if not val:
                QMessageBox.critical(self, "Error", "Regex condition is checked but empty")
                return
            try:
                re.compile(val)
            except re.error as e:
                QMessageBox.critical(self, "Error", f"Invalid regex pattern: {str(e)}")
                return
            conditions.append({"type": "regex", "value": val})

        rule_dict = {
            "id": self.rule.id if self.rule else str(uuid.uuid4()),
            "name": name,
            "enabled": self.chk_enabled.isChecked(),
            "priority": priority,
            "conditions": conditions,
            "destination": destination
        }
        
        try:
            from src.rules.rule import Rule
            self.result_rule = Rule.from_dict(rule_dict)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Validation error: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SmartSortGUI()
    window.show()
    sys.exit(app.exec())
