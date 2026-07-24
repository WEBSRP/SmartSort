import sys
import os
import re
import uuid
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, 
                             QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QTextEdit, QTableWidget, QTableWidgetItem, 
                             QFileDialog, QSpinBox, QCheckBox, QMessageBox,
                             QFormLayout, QGroupBox, QLineEdit, QComboBox, 
                             QDialog, QDialogButtonBox, QSystemTrayIcon, QMenu, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRunnable, QThreadPool, QObject, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from datetime import datetime

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
        
        # Set Window Icon using absolute path resolution based on project root
        from PyQt6.QtGui import QIcon
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_file_dir))
        
        # Add assets/icons to theme paths just in case it is not registered yet
        icon_dir = os.path.join(project_root, "assets", "icons")
        current_paths = QIcon.themeSearchPaths()
        if icon_dir not in current_paths:
            QIcon.setThemeSearchPaths(current_paths + [icon_dir])
            
        theme_icon = QIcon.fromTheme("logo")
        if not theme_icon.isNull():
            self.setWindowIcon(theme_icon)
        else:
            icon_path = os.path.join(icon_dir, "logo.png")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        
        # Initialize Core
        self.config = ConfigManager(config_path="config/config.json", default_path="config/default_config.json")
        self.logger = SmartSortLogger()
        self.organizer = FileOrganizer(self.config, self.logger)
        self.threadpool = QThreadPool()
        
        self.stats = {"processed": 0, "duplicates": 0, "errors": 0}
        self.really_exit = False
        self.monitoring_active = True
        self.last_activity_time = "Never"
        
        self.init_notification_system()
        self.init_ui()
        
        self.tray_available = False
        try:
            self.setup_system_tray()
            self.tray_available = True
        except Exception as e:
            self.logger.warning(f"System tray initialization failed: {e}")
            
        self.apply_theme()
        
        from PyQt6.QtCore import QTimer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_dashboard_stats)
        self.status_timer.start(3000)
        
        self.start_monitor()
        
        if self.tray_available:
            QTimer.singleShot(2000, self.finish_startup)

    def setup_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        from src.gui.tray_manager import TrayStateManager
        self.tray_manager = TrayStateManager(self.tray_icon, self)
        self.tray_manager.set_startup()
        
        menu = QMenu()
        
        act_dashboard = menu.addAction("Open Dashboard")
        act_dashboard.triggered.connect(lambda: self.show_tab(0))
        
        act_rules = menu.addAction("Open Rules")
        act_rules.triggered.connect(lambda: self.show_tab(2))
        
        act_tester = menu.addAction("Open Rule Tester")
        act_tester.triggered.connect(lambda: self.show_tab(4))
        
        act_settings = menu.addAction("Open Settings")
        act_settings.triggered.connect(lambda: self.show_tab(3))
        
        menu.addSeparator()
        
        self.act_pause = menu.addAction("Pause Monitoring")
        self.act_pause.triggered.connect(self.pause_monitoring)
        
        self.act_resume = menu.addAction("Resume Monitoring")
        self.act_resume.triggered.connect(self.resume_monitoring)
        self.act_resume.setEnabled(False)
        
        menu.addSeparator()
        
        act_stats = menu.addAction("Show Statistics")
        act_stats.triggered.connect(self.show_statistics)
        
        act_reports = menu.addAction("Open Reports Folder")
        act_reports.triggered.connect(self.open_reports_folder)
        
        act_about = menu.addAction("About SmartSort")
        if hasattr(self, "show_about_dialog"):
            act_about.triggered.connect(self.show_about_dialog)
        
        act_restart = menu.addAction("Restart SmartSort")
        act_restart.triggered.connect(self.restart_application)
        
        menu.addSeparator()
        
        act_exit = menu.addAction("Exit SmartSort")
        act_exit.triggered.connect(self.exit_application)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def finish_startup(self):
        if self.tray_available:
            active_rules = len([r for r in self.organizer.rule_manager.rules if r.enabled])
            if getattr(self, "monitoring_active", True):
                self.tray_manager.set_monitoring(self.stats.get("processed", 0), active_rules)
            else:
                self.tray_manager.set_paused(self.stats.get("processed", 0), active_rules)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_tab(0)

    def show_about_dialog(self):
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtCore import Qt
        msg = QMessageBox(self)
        msg.setWindowTitle("About SmartSort")
        msg.setText("<b>SmartSort File Organizer</b><br>Version 2.0.0<br><br>An intelligent, rule-based daemon and GUI to organize your downloads folder automatically.")
        
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_file_dir))
        logo_path = os.path.join(project_root, "assets", "icons", "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scaled = pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            msg.setIconPixmap(scaled)
            
        msg.exec()

    def show_tab(self, index):
        self.tabs.setCurrentIndex(index)
        self.showNormal()
        self.activateWindow()

    def pause_monitoring(self):
        self.monitoring_active = False
        self.lbl_monitoring_val.setText("Paused")
        self.lbl_status.setText("Status: Monitoring Paused")
        self.act_pause.setEnabled(False)
        self.act_resume.setEnabled(True)
        self.logger.info("Monitoring paused by user")
        if self.tray_available:
            active_rules = len([r for r in self.organizer.rule_manager.rules if r.enabled])
            self.tray_manager.set_paused(self.stats.get("processed", 0), active_rules)

    def resume_monitoring(self):
        self.monitoring_active = True
        self.lbl_monitoring_val.setText("Running")
        self.lbl_status.setText("Status: Monitoring Downloads...")
        self.act_pause.setEnabled(True)
        self.act_resume.setEnabled(False)
        self.logger.info("Monitoring resumed by user")
        if self.tray_available:
            active_rules = len([r for r in self.organizer.rule_manager.rules if r.enabled])
            self.tray_manager.set_monitoring(self.stats.get("processed", 0), active_rules)

    def show_statistics(self):
        QMessageBox.information(
            self, "Statistics", 
            f"Files Processed: {self.stats['processed']}\n"
            f"Duplicates Skipped: {self.stats['duplicates']}\n"
            f"Errors Encountered: {self.stats['errors']}"
        )

    def open_reports_folder(self):
        reports_dir = os.path.abspath("reports")
        import subprocess
        try:
            subprocess.run(["xdg-open", reports_dir], check=False, timeout=2.0)
        except Exception as e:
            self.logger.error(f"Failed to open reports folder: {e}")

    def restart_application(self):
        self.really_exit = True
        self.close()
        import subprocess
        subprocess.Popen([sys.executable, sys.argv[0]] + sys.argv[1:])
        QApplication.quit()

    def exit_application(self):
        self.really_exit = True
        self.close()
        QApplication.quit()

    def is_system_dark_mode(self) -> bool:
        try:
            import subprocess
            res = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True, check=False, timeout=2.0
            )
            if "prefer-dark" in res.stdout:
                return True
        except Exception:
            pass
        return False

    def apply_theme(self):
        theme_setting = self.config.get("theme", "system")
        is_dark = False
        if theme_setting == "dark":
            is_dark = True
        elif theme_setting == "light":
            is_dark = False
        else:
            is_dark = self.is_system_dark_mode()
            
        if is_dark:
            qss = """
            QWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QMainWindow {
                background-color: #1a1a1a;
            }
            QTabWidget::pane {
                border: 1px solid #303030;
                background-color: #1e1e1e;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #2b2b2b;
                color: #b0b0b0;
                padding: 8px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                border: 1px solid #303030;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #ffffff;
                font-weight: bold;
                border-bottom: 1px solid #1e1e1e;
            }
            QFrame {
                background-color: transparent;
            }
            QFrame.Card {
                background-color: #262626;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                background-color: transparent;
                color: #e0e0e0;
            }
            QCheckBox, QRadioButton {
                background-color: transparent;
                color: #e0e0e0;
            }
            QGroupBox {
                border: 1px solid #333333;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                color: #ffffff;
                background-color: #242424;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                background-color: #1e1e1e;
            }
            QScrollArea {
                border: none;
                background-color: #1e1e1e;
            }
            QScrollArea::viewport {
                background-color: #1e1e1e;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #1e1e1e;
            }
            QLineEdit, QTextEdit, QTableWidget, QListWidget, QComboBox, QSpinBox {
                background-color: #181818;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 6px;
                color: #e0e0e0;
            }
            QLineEdit:focus, QTextEdit:focus, QTableWidget:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #3584e4;
            }
            QHeaderView::section {
                background-color: #262626;
                color: #e0e0e0;
                padding: 4px;
                border: 1px solid #303030;
            }
            QTableCornerButton::section {
                background-color: #262626;
                border: 1px solid #303030;
            }
            QComboBox::drop-down {
                border: none;
                background: transparent;
            }
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 6px 12px;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: #353535;
                border: 1px solid #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #404040;
            }
            QPushButton#primary {
                background-color: #3584e4;
                color: white;
                border: none;
            }
            QPushButton#primary:hover {
                background-color: #1b6acb;
            }
            QPushButton#primary:pressed {
                background-color: #1555a3;
            }
            code {
                background-color: #262626;
                color: #e0e0e0;
                padding: 2px 4px;
                border-radius: 4px;
            }
            """
        else:
            qss = """
            QWidget {
                background-color: #f6f5f4;
                color: #2e3436;
            }
            QMainWindow {
                background-color: #f6f5f4;
            }
            QTabWidget::pane {
                border: 1px solid #e1dedb;
                background-color: #ffffff;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #e1dedb;
                color: #2e3436;
                padding: 8px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                border: 1px solid #e1dedb;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #2e3436;
                font-weight: bold;
                border-bottom: 1px solid #ffffff;
            }
            QFrame {
                background-color: transparent;
            }
            QFrame.Card {
                background-color: #ffffff;
                border: 1px solid #e1dedb;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                background-color: transparent;
                color: #2e3436;
            }
            QCheckBox, QRadioButton {
                background-color: transparent;
                color: #2e3436;
            }
            QPushButton {
                background-color: #e1dedb;
                border: 1px solid #c0bab4;
                border-radius: 6px;
                padding: 6px 12px;
                color: #2e3436;
            }
            QPushButton:hover {
                background-color: #d5d1cc;
            }
            QPushButton:pressed {
                background-color: #c0bab4;
            }
            QPushButton#primary {
                background-color: #3584e4;
                color: white;
                border: none;
            }
            QPushButton#primary:hover {
                background-color: #1b6acb;
            }
            QPushButton#primary:pressed {
                background-color: #1555a3;
            }
            QLineEdit, QTextEdit, QTableWidget, QListWidget, QComboBox, QSpinBox {
                background-color: #ffffff;
                border: 1px solid #e1dedb;
                border-radius: 6px;
                padding: 4px;
                color: #2e3436;
            }
            QLineEdit:focus, QTextEdit:focus, QTableWidget:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #3584e4;
            }
            QGroupBox {
                border: 1px solid #e1dedb;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                color: #2e3436;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                background-color: #f6f5f4;
            }
            QScrollArea {
                border: none;
                background-color: #f6f5f4;
            }
            QScrollArea::viewport {
                background-color: #f6f5f4;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #f6f5f4;
            }
            QHeaderView::section {
                background-color: #e1dedb;
                color: #2e3436;
                padding: 4px;
                border: 1px solid #c0bab4;
            }
            QTableCornerButton::section {
                background-color: #e1dedb;
                border: 1px solid #c0bab4;
            }
            code {
                background-color: #f0ede9;
                color: #2e3436;
                padding: 2px 4px;
                border-radius: 4px;
            }
            """
        self.setStyleSheet(qss)

    def create_card(self, title, val):
        from PyQt6.QtWidgets import QFrame
        card = QFrame()
        card.setObjectName(title.replace(" ", "_").lower())
        card.setProperty("class", "Card")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        
        layout = QVBoxLayout(card)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #777777;")
        lbl_val = QLabel(val)
        lbl_val.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)
        layout.addStretch()
        return card, lbl_val

    def update_dashboard_stats(self):
        self.lbl_processed_val.setText(str(self.stats.get("processed", 0)))
        self.lbl_duplicates_val.setText(str(self.stats.get("duplicates", 0)))
        self.lbl_errors_val.setText(str(self.stats.get("errors", 0)))
        
        mon_status = "Running" if getattr(self, "monitoring_active", True) else "Paused"
        self.lbl_monitoring_val.setText(mon_status)
        if mon_status == "Running":
            self.lbl_monitoring_val.setStyleSheet("font-size: 16px; font-weight: bold; color: #2ec27e;")
        else:
            self.lbl_monitoring_val.setStyleSheet("font-size: 16px; font-weight: bold; color: #e01b24;")
            
        svc_status = self.get_service_status()
        self.lbl_service_val.setText(svc_status)
        if svc_status == "Running":
            self.lbl_service_val.setStyleSheet("font-size: 16px; font-weight: bold; color: #2ec27e;")
        elif svc_status == "Stopped":
            self.lbl_service_val.setStyleSheet("font-size: 16px; font-weight: bold; color: #f5c211;")
        else:
            self.lbl_service_val.setStyleSheet("font-size: 16px; font-weight: bold; color: #e01b24;")
            
        active_rules = len([r for r in self.organizer.rule_manager.rules if r.enabled])
        total_rules = len(self.organizer.rule_manager.rules)
        self.lbl_rules_val.setText(f"{active_rules} / {total_rules}")
        
        self.lbl_activity_val.setText(getattr(self, "last_activity_time", "Never"))
        
        if hasattr(self, "lbl_service_control_status"):
            self.lbl_service_control_status.setText(f"Service status: {svc_status}")
            
        from src.gui.tray_manager import TrayState
        if self.tray_available and self.tray_manager.current_state in [TrayState.IDLE, TrayState.PAUSED, TrayState.ERROR]:
            if getattr(self, "monitoring_active", True):
                self.tray_manager.set_monitoring(self.stats.get("processed", 0), active_rules)
            else:
                self.tray_manager.set_paused(self.stats.get("processed", 0), active_rules)

    def get_service_status(self) -> str:
        from pathlib import Path
        import subprocess
        service_file = Path.home() / ".config" / "systemd" / "user" / "smartsort.service"
        try:
            # Query if enabled
            res_enabled = subprocess.run(
                ["systemctl", "--user", "is-enabled", "smartsort.service"],
                capture_output=True, text=True, check=False, timeout=2.0
            )
            enabled_out = res_enabled.stdout.strip()
            
            # Check if not installed
            if not service_file.exists() and (enabled_out == "not-found" or "No such file" in res_enabled.stderr or res_enabled.returncode == 4):
                return "Not Installed"
                
            # Check if active/running
            res_active = subprocess.run(
                ["systemctl", "--user", "is-active", "smartsort.service"],
                capture_output=True, text=True, check=False, timeout=2.0
            )
            active_out = res_active.stdout.strip()
            
            if active_out == "active":
                return "Running"
            elif enabled_out == "enabled":
                return "Stopped"
            else:
                return "Disabled"
        except Exception:
            if not service_file.exists():
                return "Not Installed"
            return "Stopped"

    def install_service(self):
        from pathlib import Path
        try:
            service_dir = Path.home() / ".config" / "systemd" / "user"
            service_dir.mkdir(parents=True, exist_ok=True)
            service_file = service_dir / "smartsort.service"
            
            main_path = Path(sys.argv[0]).resolve()
            content = f"""[Unit]
Description=SmartSort File Organizer Service
After=network.target

[Service]
Type=simple
WorkingDirectory={main_path.parent}
ExecStart={sys.executable} {main_path} --daemon
Restart=on-failure

[Install]
WantedBy=default.target
"""
            service_file.write_text(content)
            
            import subprocess
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, timeout=2.0)
            subprocess.run(["systemctl", "--user", "enable", "smartsort.service"], check=True, timeout=2.0)
            
            self.logger.info("Systemd user service installed and enabled successfully.")
            self.update_dashboard_stats()
            QMessageBox.information(self, "Success", "Systemd user service installed and enabled successfully.")
        except Exception as e:
            self.logger.error(f"Failed to install systemd service: {e}")
            QMessageBox.critical(self, "Error", f"Failed to install systemd service: {str(e)}")

    def start_service(self):
        import subprocess
        try:
            subprocess.run(["systemctl", "--user", "start", "smartsort.service"], check=True, timeout=2.0)
            self.update_dashboard_stats()
            QMessageBox.information(self, "Success", "Systemd service started successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start service: {str(e)}")
            
    def stop_service(self):
        import subprocess
        try:
            subprocess.run(["systemctl", "--user", "stop", "smartsort.service"], check=True, timeout=2.0)
            self.update_dashboard_stats()
            QMessageBox.information(self, "Success", "Systemd service stopped successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to stop service: {str(e)}")
            
    def restart_service(self):
        import subprocess
        try:
            subprocess.run(["systemctl", "--user", "restart", "smartsort.service"], check=True, timeout=2.0)
            self.update_dashboard_stats()
            QMessageBox.information(self, "Success", "Systemd service restarted successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to restart service: {str(e)}")

    def update_autostart_setting(self, enabled: bool):
        from pathlib import Path
        autostart_dir = Path.home() / ".config" / "autostart"
        autostart_file = autostart_dir / "smartsort.desktop"
        
        if enabled:
            try:
                autostart_dir.mkdir(parents=True, exist_ok=True)
                main_path = Path(sys.argv[0]).resolve()
                content = f"""[Desktop Entry]
Type=Application
Exec={sys.executable} {main_path} --service
Path={main_path.parent}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=SmartSort
Comment=SmartSort File Organizer Background Service
Icon={main_path.parent}/assets/icons/logo.png
"""
                autostart_file.write_text(content)
                self.logger.info(f"Autostart entry created at {autostart_file}")
            except Exception as e:
                self.logger.error(f"Failed to create autostart entry: {e}")
        else:
            if autostart_file.exists():
                try:
                    autostart_file.unlink()
                    self.logger.info(f"Autostart entry removed from {autostart_file}")
                except Exception as e:
                    self.logger.error(f"Failed to remove autostart entry: {e}")

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized() and getattr(self, "tray_available", False):
                self.hide()
                event.accept()
                return
        super().changeEvent(event)

    def closeEvent(self, event):
        if not getattr(self, "tray_available", False):
            self.really_exit = True
            
        if not getattr(self, "really_exit", False):
            event.ignore()
            self.hide()
            if getattr(self, "notifications_enabled", False):
                try:
                    import notify2
                    n = notify2.Notification("SmartSort", "SmartSort is still running in the system tray.")
                    n.show()
                except Exception:
                    pass
        else:
            if hasattr(self, "monitor_thread"):
                try:
                    self.monitor_thread.stop()
                except Exception:
                    pass
            event.accept()

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
        from PyQt6.QtWidgets import QFrame, QGridLayout
        main_layout = QVBoxLayout()
        
        # Grid of cards
        grid_layout = QGridLayout()
        
        self.card_processed, self.lbl_processed_val = self.create_card("Files Processed", "0")
        self.card_duplicates, self.lbl_duplicates_val = self.create_card("Duplicates Skipped", "0")
        self.card_errors, self.lbl_errors_val = self.create_card("Errors Encountered", "0")
        self.card_monitoring, self.lbl_monitoring_val = self.create_card("Monitoring Status", "Running")
        self.card_service, self.lbl_service_val = self.create_card("Service Status", "Checking...")
        self.card_rules, self.lbl_rules_val = self.create_card("Rules Active", "0")
        self.card_activity, self.lbl_activity_val = self.create_card("Last Activity", "Never")
        
        grid_layout.addWidget(self.card_processed, 0, 0)
        grid_layout.addWidget(self.card_duplicates, 0, 1)
        grid_layout.addWidget(self.card_errors, 0, 2)
        grid_layout.addWidget(self.card_monitoring, 0, 3)
        grid_layout.addWidget(self.card_service, 1, 0)
        grid_layout.addWidget(self.card_rules, 1, 1)
        grid_layout.addWidget(self.card_activity, 1, 2, 1, 2) # spanning 2 columns
        
        main_layout.addLayout(grid_layout)
        
        # Status label
        self.lbl_status = QLabel("Status: Monitoring Downloads...")
        self.lbl_status.setStyleSheet("font-weight: bold; margin-top: 10px;")
        main_layout.addWidget(self.lbl_status)
        
        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        main_layout.addWidget(QLabel("Recent Activity:"))
        main_layout.addWidget(self.log_display)
        
        self.tab_dashboard.setLayout(main_layout)

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

    def bytes_to_human_string(self, num_bytes) -> str:
        if num_bytes is None:
            return "2.5GB"
        try:
            if isinstance(num_bytes, str):
                from src.rules.conditions import parse_size_to_bytes
                num_bytes = parse_size_to_bytes(num_bytes)
            else:
                num_bytes = int(num_bytes)
        except Exception:
            return "2.5GB"
            
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
        from PyQt6.QtWidgets import QGroupBox, QFormLayout, QComboBox, QScrollArea
        
        # Use scroll area to ensure all settings fit neatly
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        container = QWidget()
        scroll.setWidget(container)
        
        layout = QVBoxLayout(container)
        
        # 1. General Group
        group_general = QGroupBox("General Settings")
        gen_layout = QVBoxLayout(group_general)
        
        self.chk_autostart = QCheckBox("Start SmartSort Automatically at Login")
        self.chk_autostart.setChecked(bool(self.config.get("autostart", False)))
        
        self.chk_start_minimized = QCheckBox("Start SmartSort Minimized (to Tray)")
        self.chk_start_minimized.setChecked(bool(self.config.get("start_minimized", False)))
        
        h_theme = QHBoxLayout()
        h_theme.addWidget(QLabel("Application Theme:"))
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(["System Theme", "Dark Mode", "Light Mode"])
        
        theme_val = str(self.config.get("theme", "system")).lower()
        if theme_val == "dark":
            self.cmb_theme.setCurrentIndex(1)
        elif theme_val == "light":
            self.cmb_theme.setCurrentIndex(2)
        else:
            self.cmb_theme.setCurrentIndex(0)
            
        h_theme.addWidget(self.cmb_theme)
        h_theme.addStretch()
        
        gen_layout.addWidget(self.chk_autostart)
        gen_layout.addWidget(self.chk_start_minimized)
        gen_layout.addLayout(h_theme)
        layout.addWidget(group_general)
        
        # 2. Monitoring Group
        group_monitoring = QGroupBox("Monitoring Settings")
        mon_layout = QFormLayout(group_monitoring)
        
        h_down = QHBoxLayout()
        self.txt_downloads = QLabel(str(self.config.get("downloads_folder", "~/Downloads")))
        self.txt_downloads.setWordWrap(True)
        btn_browse_down = QPushButton("Browse")
        btn_browse_down.clicked.connect(self.browse_downloads)
        h_down.addWidget(self.txt_downloads, 1)
        h_down.addWidget(btn_browse_down)
        
        mon_layout.addRow("Downloads Folder:", h_down)
        
        self.txt_thresh = QLineEdit()
        self.txt_thresh.setPlaceholderText("Examples: 500MB, 1.5GB, 2GB")
        current_bytes = self.config.get("large_file_threshold_gb", 2684354560)
        if isinstance(current_bytes, (int, float)) and current_bytes < 10000:
            current_bytes = int(current_bytes * (1024**3))
        self.txt_thresh.setText(self.bytes_to_human_string(current_bytes))
        
        mon_layout.addRow("Large File Threshold:", self.txt_thresh)
        layout.addWidget(group_monitoring)
        
        # 3. Notifications Group
        group_notif = QGroupBox("Notifications")
        notif_layout = QVBoxLayout(group_notif)
        
        self.chk_notif = QCheckBox("Enable Desktop Notifications")
        self.chk_notif.setChecked(bool(self.config.get("enable_notifications", True)))
        notif_layout.addWidget(self.chk_notif)
        layout.addWidget(group_notif)
        
        # 4. Service Group
        group_service = QGroupBox("Background Service Controls (Systemd)")
        svc_layout = QVBoxLayout(group_service)
        
        self.lbl_service_control_status = QLabel("Service status: Checking...")
        self.lbl_service_control_status.setStyleSheet("font-weight: bold;")
        svc_layout.addWidget(self.lbl_service_control_status)
        
        h_svc_btns = QHBoxLayout()
        btn_inst_svc = QPushButton("Install Service")
        btn_inst_svc.clicked.connect(self.install_service)
        btn_start_svc = QPushButton("Start Service")
        btn_start_svc.clicked.connect(self.start_service)
        btn_stop_svc = QPushButton("Stop Service")
        btn_stop_svc.clicked.connect(self.stop_service)
        btn_restart_svc = QPushButton("Restart Service")
        btn_restart_svc.clicked.connect(self.restart_service)
        
        h_svc_btns.addWidget(btn_inst_svc)
        h_svc_btns.addWidget(btn_start_svc)
        h_svc_btns.addWidget(btn_stop_svc)
        h_svc_btns.addWidget(btn_restart_svc)
        svc_layout.addLayout(h_svc_btns)
        
        layout.addWidget(group_service)
        
        # 5. Advanced Group
        group_adv = QGroupBox("Advanced Settings")
        adv_layout = QFormLayout(group_adv)
        
        self.chk_dup = QCheckBox("Enable Duplicate Detection (SHA256 Hash check)")
        self.chk_dup.setChecked(bool(self.config.get("enable_duplicate_detection", True)))
        adv_layout.addRow(self.chk_dup)
        
        self.cmb_conflict = QComboBox()
        self.cmb_conflict.addItems(["rename", "overwrite", "skip"])
        conflict_val = self.config.get("conflict_resolution", "rename")
        if conflict_val not in ["rename", "overwrite", "skip"]:
            conflict_val = "rename"
        self.cmb_conflict.setCurrentText(str(conflict_val))
        adv_layout.addRow("Collision Policy:", self.cmb_conflict)
        
        layout.addWidget(group_adv)
        
        # Save Button
        btn_save = QPushButton("Save All Settings")
        btn_save.setObjectName("primary")
        btn_save.clicked.connect(self.save_settings)
        layout.addWidget(btn_save)
        
        # Wrap container in scroll area
        main_settings_layout = QVBoxLayout()
        main_settings_layout.addWidget(scroll)
        self.tab_settings.setLayout(main_settings_layout)

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
            self.config.set("conflict_resolution", self.cmb_conflict.currentText())
            self.config.set("start_minimized", self.chk_start_minimized.isChecked())
            
            prev_autostart = self.config.get("autostart", False)
            new_autostart = self.chk_autostart.isChecked()
            self.config.set("autostart", new_autostart)
            
            if prev_autostart != new_autostart:
                self.update_autostart_setting(new_autostart)
                
            theme_map = {"System Theme": "system", "Dark Mode": "dark", "Light Mode": "light"}
            theme_val = theme_map.get(self.cmb_theme.currentText(), "system")
            self.config.set("theme", theme_val)
            
            # Apply theme immediately
            self.apply_theme()
            
            QMessageBox.information(self, "Success", "All settings saved successfully!")
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
            
            priority_badge = f"P{r.priority}"
            priority_item = QTableWidgetItem(priority_badge)
            priority_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            enabled_indicator = "🟢" if r.enabled else "🔴"
            enabled_item = QTableWidgetItem(enabled_indicator)
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            dest_item = QTableWidgetItem(r.destination)
            
            self.table_rules.setItem(row, 0, name_item)
            self.table_rules.setItem(row, 1, priority_item)
            self.table_rules.setItem(row, 2, enabled_item)
            self.table_rules.setItem(row, 3, dest_item)
            
        self.table_rules.resizeColumnsToContents()
        self.table_rules.horizontalHeader().setStretchLastSection(True)

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
            self.lbl_test_match.setText(f"<span style='color: #2ec27e; font-weight: bold;'>{rule.name}</span>")
            self.lbl_test_priority.setText(f"<span style='background-color: #3584e4; color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold;'>P{rule.priority}</span>")
        else:
            self.lbl_test_match.setText("<span style='color: #f5c211; font-weight: bold;'>None (Fallback Rule)</span>")
            self.lbl_test_priority.setText("<span style='color: #888888;'>N/A</span>")
            
        self.lbl_test_dest.setText(f"<code>{dest}</code>")

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
        if not getattr(self, "monitoring_active", True):
            self.logger.info(f"Monitoring is paused. Ignoring file: {file_path}")
            if hasattr(self, 'monitor_thread'):
                self.monitor_thread.get_handler().mark_as_unprocessed(file_path)
            return
        # This is called from the monitor thread (via signal)
        self.log_display.append(f"Detected: {os.path.basename(file_path)}")
        if self.tray_available:
            try:
                size_bytes = os.path.getsize(file_path)
            except Exception:
                size_bytes = 0
            self.tray_manager.set_processing(os.path.basename(file_path), size_bytes)
        self.start_file_worker(file_path)

    def start_file_worker(self, file_path, user_approved=False):
        worker = FileWorker(self.organizer, file_path, user_approved)
        worker.signals.finished.connect(self.on_worker_finished)
        worker.signals.error.connect(self.on_worker_error)
        self.threadpool.start(worker)

    def update_stats(self, category):
        self.stats[category] += 1
        self.last_activity_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.update_dashboard_stats()

    def on_worker_finished(self, file_path, result, info):
        filename = os.path.basename(file_path)
        active_rules = len([r for r in self.organizer.rule_manager.rules if r.enabled])
        if result == "AWAIT_APPROVAL":
            self.ask_approval(file_path, info)
        elif result == "SUCCESS":
            self.update_stats("processed")
            self.log_display.append(f"Moved {filename} to: {info}")
            if self.config.get("enable_notifications"):
                self.show_notification("File Organized", f"{filename} moved to {info}")
            self.refresh_logs()
            if self.tray_available:
                self.tray_manager.set_success(self.stats.get("processed", 0), active_rules)
        elif result == "DUPLICATE":
            self.update_stats("duplicates")
            self.log_display.append(f"Duplicate found for {filename} at: {info}")
            QMessageBox.information(self, "Duplicate Detected", f"A matching file already exists:\n{info}")
            if self.tray_available:
                self.tray_manager.set_success(self.stats.get("processed", 0), active_rules)
        elif result == "SKIPPED":
            self.log_display.append(f"Skipped: {filename} ({info})")
            if self.tray_available:
                self.tray_manager.set_success(self.stats.get("processed", 0), active_rules)
        elif result == "ERROR":
            self.update_stats("errors")
            self.log_display.append(f"Error processing {filename}: {info}")
            if self.config.get("enable_notifications"):
                self.show_notification("SmartSort Error", f"Failed to organize {filename}: {info}")
            if hasattr(self, 'monitor_thread'):
                self.monitor_thread.get_handler().mark_as_unprocessed(file_path)
            if self.tray_available:
                self.tray_manager.set_error(info)

    def on_worker_error(self, file_path, error_msg):
        self.log_display.append(f"Critical error processing {os.path.basename(file_path)}: {error_msg}")
        if self.config.get("enable_notifications"):
            self.show_notification("SmartSort Critical Error", f"Error organizing {os.path.basename(file_path)}: {error_msg}")
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.get_handler().mark_as_unprocessed(file_path)
        if self.tray_available:
            self.tray_manager.set_error(error_msg)

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
