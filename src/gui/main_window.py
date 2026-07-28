import sys
from pathlib import Path
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
from src.utils.packaging import detect_package_type, PackageType, Capability, has_capability, check_appimage_moved

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
        self._stop_requested = False

    def run(self):
        if self._stop_requested or self.isInterruptionRequested():
            return

        try:
            self.monitor.start()
        except Exception:
            return

        if self._stop_requested or self.isInterruptionRequested():
            try:
                self.monitor.stop()
            except Exception:
                pass
            return

        self.exec() # Keep thread alive

    def stop(self):
        self._stop_requested = True
        self.requestInterruption()
        try:
            self.monitor.stop()
        except Exception:
            pass
        finally:
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
        from src.utils.paths import AppPaths
        
        # Add assets/icons to theme paths just in case it is not registered yet
        icon_dir = str(AppPaths.resource_dir() / "icons")
        current_paths = QIcon.themeSearchPaths()
        if icon_dir not in current_paths:
            QIcon.setThemeSearchPaths(current_paths + [icon_dir])
            
        theme_icon = QIcon.fromTheme("logo")
        if not theme_icon.isNull():
            self.setWindowIcon(theme_icon)
        else:
            icon_path = Path(icon_dir) / "logo.png"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
        
        # Initialize Core
        self.config = ConfigManager()
        self.logger = SmartSortLogger()
        self.organizer = FileOrganizer(self.config, self.logger)
        from src.utils.autostart import AutostartManager
        self.autostart_manager = AutostartManager(self.logger)
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
        if not "PYTEST_CURRENT_TEST" in os.environ:
            self.status_timer.start(3000)
        
        self.start_monitor()
        
        if self.tray_available and not "PYTEST_CURRENT_TEST" in os.environ:
            QTimer.singleShot(2000, self.finish_startup)
            
        # Run startup verification and repair check on launch
        if not "PYTEST_CURRENT_TEST" in os.environ:
            QTimer.singleShot(1000, self.verify_and_repair_startup_config)

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
        
        logo_path = AppPaths.resource_dir() / "icons" / "logo.png"
        if logo_path.is_file():
            pixmap = QPixmap(str(logo_path))
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
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_file_dir))
        reports_dir = os.path.join(project_root, "reports")
        import subprocess
        try:
            os.makedirs(reports_dir, exist_ok=True)
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
                font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
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
                padding: 10px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                border: 1px solid #303030;
                border-bottom: none;
                font-weight: 500;
            }
            QTabBar::tab:hover {
                background-color: #353535;
                color: #ffffff;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #ffffff;
                font-weight: bold;
                border-bottom: 2px solid #3584e4;
            }
            QFrame {
                background-color: transparent;
            }
            QFrame.Card {
                background-color: #262626;
                border: 1px solid #333333;
                border-radius: 12px;
                padding: 12px;
            }
            QFrame.Card:hover {
                border-color: #3584e4;
                background-color: #2d2d2d;
            }
            QLabel {
                background-color: transparent;
                color: #e0e0e0;
            }
            QLabel#card_title {
                font-size: 11px;
                font-weight: bold;
                color: #909090;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QLabel#card_value {
                font-size: 18px;
                font-weight: bold;
                color: #ffffff;
            }
            QCheckBox, QRadioButton {
                background-color: transparent;
                color: #e0e0e0;
                spacing: 8px;
            }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #2b2b2b;
            }
            QCheckBox::indicator:hover, QRadioButton::indicator:hover {
                border-color: #3584e4;
                background-color: #323232;
            }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background-color: #3584e4;
                border-color: #3584e4;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20'><path fill='%23ffffff' d='M14.8 5.3L8.1 12 5.2 9.1c-.4-.4-1-.4-1.4 0s-.4 1 0 1.4l3.5 3.5c.2.2.4.3.7.3.3 0 .5-.1.7-.3l7.4-7.4c.4-.4.4-1 0-1.4s-1-.4-1.4 0z'/></svg>");
            }
            QCheckBox::indicator:checked:hover, QRadioButton::indicator:checked:hover {
                background-color: #1b6acb;
                border-color: #1b6acb;
            }
            QGroupBox {
                border: 1px solid #333333;
                border-radius: 8px;
                margin-top: 16px;
                font-weight: bold;
                color: #ffffff;
                background-color: #242424;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 15px;
                padding: 0 5px 0 5px;
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
                padding: 8px;
                color: #e0e0e0;
            }
            QLineEdit:focus, QTextEdit:focus, QTableWidget:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #3584e4;
            }
            QHeaderView::section {
                background-color: #262626;
                color: #e0e0e0;
                padding: 6px;
                border: 1px solid #303030;
                font-weight: bold;
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
                padding: 8px 16px;
                color: #e0e0e0;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #353535;
                border-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #404040;
            }
            QPushButton:disabled {
                background-color: #1e1e1e;
                color: #666666;
                border-color: #2a2a2a;
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
            QScrollBar:vertical {
                border: none;
                background: #181818;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #3e3e3e;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #555555;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
            QScrollBar:horizontal {
                border: none;
                background: #181818;
                height: 10px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #3e3e3e;
                min-width: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #555555;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
            }
            """
        else:
            qss = """
            QWidget {
                background-color: #f6f5f4;
                color: #2e3436;
                font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
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
                color: #505050;
                padding: 10px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                border: 1px solid #e1dedb;
                border-bottom: none;
                font-weight: 500;
            }
            QTabBar::tab:hover {
                background-color: #eae7e4;
                color: #2e3436;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #2e3436;
                font-weight: bold;
                border-bottom: 2px solid #3584e4;
            }
            QFrame {
                background-color: transparent;
            }
            QFrame.Card {
                background-color: #ffffff;
                border: 1px solid #e1dedb;
                border-radius: 12px;
                padding: 12px;
            }
            QFrame.Card:hover {
                border-color: #3584e4;
                background-color: #faf9f9;
            }
            QLabel {
                background-color: transparent;
                color: #2e3436;
            }
            QLabel#card_title {
                font-size: 11px;
                font-weight: bold;
                color: #777777;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QLabel#card_value {
                font-size: 18px;
                font-weight: bold;
                color: #2e3436;
            }
            QCheckBox, QRadioButton {
                background-color: transparent;
                color: #2e3436;
                spacing: 8px;
            }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #c0bab4;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:hover, QRadioButton::indicator:hover {
                border-color: #3584e4;
                background-color: #f6f5f4;
            }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background-color: #3584e4;
                border-color: #3584e4;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20'><path fill='%23ffffff' d='M14.8 5.3L8.1 12 5.2 9.1c-.4-.4-1-.4-1.4 0s-.4 1 0 1.4l3.5 3.5c.2.2.4.3.7.3.3 0 .5-.1.7-.3l7.4-7.4c.4-.4.4-1 0-1.4s-1-.4-1.4 0z'/></svg>");
            }
            QCheckBox::indicator:checked:hover, QRadioButton::indicator:checked:hover {
                background-color: #1b6acb;
                border-color: #1b6acb;
            }
            QPushButton {
                background-color: #e1dedb;
                border: 1px solid #c0bab4;
                border-radius: 6px;
                padding: 8px 16px;
                color: #2e3436;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #d5d1cc;
            }
            QPushButton:pressed {
                background-color: #c0bab4;
            }
            QPushButton:disabled {
                background-color: #f6f5f4;
                color: #888888;
                border-color: #e1dedb;
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
                padding: 8px;
                color: #2e3436;
            }
            QLineEdit:focus, QTextEdit:focus, QTableWidget:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #3584e4;
            }
            QGroupBox {
                border: 1px solid #e1dedb;
                border-radius: 8px;
                margin-top: 16px;
                font-weight: bold;
                color: #2e3436;
                background-color: #ffffff;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 15px;
                padding: 0 5px 0 5px;
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
                padding: 6px;
                border: 1px solid #c0bab4;
                font-weight: bold;
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
            QScrollBar:vertical {
                border: none;
                background: #f6f5f4;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #c0bab4;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #a09a94;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
            QScrollBar:horizontal {
                border: none;
                background: #f6f5f4;
                height: 10px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #c0bab4;
                min-width: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #a09a94;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
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
        layout.setSpacing(4)
        layout.setContentsMargins(12, 12, 12, 12)
        
        lbl_title = QLabel(title)
        lbl_title.setObjectName("card_title")
        lbl_val = QLabel(val)
        lbl_val.setObjectName("card_value")
        
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
            pkg_type = detect_package_type()
            if pkg_type == PackageType.FLATPAK:
                self.lbl_service_control_status.setText("Background Service: Unavailable")
            else:
                self.lbl_service_control_status.setText(f"Service status: {svc_status}")
            
        pkg_type = detect_package_type()
        if pkg_type == PackageType.APPIMAGE:
            if hasattr(self, "btn_install_service") and hasattr(self, "btn_update_service") and hasattr(self, "btn_remove_service"):
                if svc_status == "Not Installed":
                    self.btn_install_service.setEnabled(True)
                    self.btn_update_service.setEnabled(False)
                    self.btn_remove_service.setEnabled(False)
                else:
                    self.btn_install_service.setEnabled(False)
                    self.btn_update_service.setEnabled(True)
                    self.btn_remove_service.setEnabled(True)
        elif pkg_type != PackageType.FLATPAK:
            if hasattr(self, "btn_install_service"):
                if svc_status == "Not Installed":
                    self.btn_install_service.setEnabled(True)
                    self.btn_remove_service.setEnabled(False)
                    self.btn_start_service.setEnabled(False)
                    self.btn_stop_service.setEnabled(False)
                    self.btn_restart_service.setEnabled(False)
                    self.btn_enable_service.setEnabled(False)
                    self.btn_disable_service.setEnabled(False)
                else:
                    self.btn_install_service.setEnabled(False)
                    self.btn_remove_service.setEnabled(True)
                    self.btn_start_service.setEnabled(svc_status != "Running")
                    self.btn_stop_service.setEnabled(svc_status == "Running")
                    self.btn_restart_service.setEnabled(svc_status == "Running")
                    
                    # To determine enable/disable button state:
                    # check systemctl is-enabled
                    is_enabled_now = False
                    try:
                        import subprocess
                        res_enabled = subprocess.run(
                            ["systemctl", "--user", "is-enabled", "smartsort.service"],
                            capture_output=True, text=True, check=False, timeout=2.0
                        )
                        is_enabled_now = (res_enabled.stdout.strip() == "enabled")
                    except Exception:
                        is_enabled_now = (svc_status == "Stopped")
                        
                    self.btn_enable_service.setEnabled(not is_enabled_now)
                    self.btn_disable_service.setEnabled(is_enabled_now)
                
        from src.gui.tray_manager import TrayState
        if self.tray_available and self.tray_manager.current_state in [TrayState.IDLE, TrayState.PAUSED, TrayState.ERROR]:
            if getattr(self, "monitoring_active", True):
                self.tray_manager.set_monitoring(self.stats.get("processed", 0), active_rules)
            else:
                self.tray_manager.set_paused(self.stats.get("processed", 0), active_rules)

    def verify_and_repair_startup_config(self):
        # 1. Verify autostart desktop entry
        autostart_expected = bool(self.config.get("autostart", False))
        pkg_type = detect_package_type()
        
        # Check if AppImage has moved for autostart
        if pkg_type == PackageType.APPIMAGE:
            if hasattr(self, "autostart_manager"):
                autostart_moved, current_app_path, old_app_path = self.autostart_manager.check_appimage_moved()
                if autostart_moved:
                    reply = QMessageBox.question(
                        self,
                        "AppImage Path Changed (Autostart)",
                        f"The AppImage has moved from:\n{old_app_path}\n\nto:\n{current_app_path}\n\nUpdate automatic startup (autostart) configuration?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        if self.autostart_manager.enable_autostart():
                            self.show_notification("SmartSort Autostart", "Autostart path updated successfully.")
                        else:
                            QMessageBox.critical(self, "Error", "Failed to update autostart path.")

        # Verify autostart entry presence and validity (missing or corrupted)
        if autostart_expected and hasattr(self, "autostart_manager"):
            desktop_file_exists = self.autostart_manager.desktop_file.exists()
            corrupted = False
            if desktop_file_exists:
                try:
                    content = self.autostart_manager.desktop_file.read_text()
                    expected_cmd = self.autostart_manager.get_command()
                    if "Name=SmartSort" not in content or "Exec=" not in content:
                        corrupted = True
                    else:
                        exec_line = ""
                        for line in content.splitlines():
                            if line.strip().startswith("Exec="):
                                exec_line = line.split("=", 1)[1].strip()
                        if exec_line != expected_cmd:
                            corrupted = True
                except Exception:
                    corrupted = True

            if not desktop_file_exists or corrupted:
                reason = "missing" if not desktop_file_exists else "corrupted"
                reply = QMessageBox.question(
                    self,
                    "Startup Entry Repair",
                    f"SmartSort detected that the automatic startup entry is {reason}.\n\nWould you like to repair it now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    if self.autostart_manager.enable_autostart():
                        self.show_notification("SmartSort Startup Repair", "Startup entry successfully repaired.")
                    else:
                        QMessageBox.critical(self, "Error", "Failed to repair startup entry.")

        # 2. Verify systemd background service (only for non-Flatpak)
        if pkg_type != PackageType.FLATPAK:
            # Check if AppImage has moved for systemd service
            has_moved, current_path, service_path = check_appimage_moved()
            if has_moved:
                reply = QMessageBox.question(
                    self,
                    "AppImage Location Changed (Service)",
                    f"The AppImage has moved from:\n{service_path}\n\nto:\n{current_path}\n\nUpdate background service?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.install_service()

    def get_service_status(self) -> str:
        pkg_type = detect_package_type()
        if pkg_type == PackageType.FLATPAK:
            return "Unavailable"
            
        from pathlib import Path
        import subprocess
        service_file = Path.home() / ".config" / "systemd" / "user" / "smartsort.service"
        try:
            res_enabled = subprocess.run(
                ["systemctl", "--user", "is-enabled", "smartsort.service"],
                capture_output=True, text=True, check=False, timeout=2.0
            )
            enabled_out = res_enabled.stdout.strip()
            
            if not service_file.exists() and (enabled_out == "not-found" or "No such file" in res_enabled.stderr or res_enabled.returncode == 4):
                return "Not Installed"
                
            res_active = subprocess.run(
                ["systemctl", "--user", "is-active", "smartsort.service"],
                capture_output=True, text=True, check=False, timeout=2.0
            )
            active_out = res_active.stdout.strip()
            
            if active_out == "active":
                return "Running"
            elif pkg_type == PackageType.APPIMAGE:
                return "Installed"
            elif enabled_out == "enabled":
                return "Stopped"
            else:
                return "Disabled"
        except Exception:
            if not service_file.exists():
                return "Not Installed"
            if pkg_type == PackageType.APPIMAGE:
                return "Installed"
            return "Stopped"

    def install_service(self):
        pkg_type = detect_package_type()
        if pkg_type == PackageType.FLATPAK:
            return
            
        from pathlib import Path
        import os
        try:
            service_dir = Path.home() / ".config" / "systemd" / "user"
            service_dir.mkdir(parents=True, exist_ok=True)
            service_file = service_dir / "smartsort.service"
            
            if pkg_type == PackageType.APPIMAGE:
                appimage_path = os.environ.get("APPIMAGE")
                if not appimage_path:
                    appimage_path = Path(sys.argv[0]).resolve()
                
                content = f"""[Unit]
Description=SmartSort File Organizer Service (AppImage)
After=network.target

[Service]
Type=simple
ExecStart={appimage_path} --daemon
Restart=on-failure

[Install]
WantedBy=default.target
"""
            else:
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
            subprocess.run(["systemctl", "--user", "start", "smartsort.service"], check=True, timeout=2.0)
            
            self.logger.info("Systemd user service installed, enabled, and started successfully.")
            self.update_dashboard_stats()
            QMessageBox.information(self, "Success", "Systemd user service installed, enabled, and started successfully.")
        except Exception as e:
            self.logger.error(f"Failed to install systemd service: {e}")
            QMessageBox.critical(self, "Error", f"Failed to install systemd service: {str(e)}")

    def enable_service(self):
        import subprocess
        try:
            subprocess.run(["systemctl", "--user", "enable", "smartsort.service"], check=True, timeout=2.0)
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, timeout=2.0)
            self.logger.info("Systemd user service enabled successfully.")
            self.update_dashboard_stats()
            QMessageBox.information(self, "Success", "Systemd user service enabled successfully.")
        except Exception as e:
            self.logger.error(f"Failed to enable systemd service: {e}")
            QMessageBox.critical(self, "Error", f"Failed to enable systemd service: {str(e)}")

    def disable_service(self):
        import subprocess
        try:
            res_active = subprocess.run(
                ["systemctl", "--user", "is-active", "smartsort.service"],
                capture_output=True, text=True, check=False, timeout=2.0
            )
            if res_active.stdout.strip() == "active":
                subprocess.run(["systemctl", "--user", "stop", "smartsort.service"], check=True, timeout=2.0)
            
            subprocess.run(["systemctl", "--user", "disable", "smartsort.service"], check=True, timeout=2.0)
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, timeout=2.0)
            self.logger.info("Systemd user service disabled successfully.")
            self.update_dashboard_stats()
            QMessageBox.information(self, "Success", "Systemd user service disabled successfully.")
        except Exception as e:
            self.logger.error(f"Failed to disable systemd service: {e}")
            QMessageBox.critical(self, "Error", f"Failed to disable systemd service: {str(e)}")

    def toggle_install_or_enable_service(self):
        status = self.get_service_status()
        if status == "Not Installed":
            self.install_service()
        elif status == "Disabled":
            self.enable_service()
        else:
            self.disable_service()

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

    def update_appimage_service(self):
        self.install_service()

    def remove_appimage_service(self):
        import subprocess
        from pathlib import Path
        try:
            subprocess.run(["systemctl", "--user", "stop", "smartsort.service"], check=False, timeout=2.0)
            subprocess.run(["systemctl", "--user", "disable", "smartsort.service"], check=False, timeout=2.0)
            service_file = Path.home() / ".config" / "systemd" / "user" / "smartsort.service"
            if service_file.exists():
                service_file.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, timeout=2.0)
            
            self.logger.info("Systemd user service removed successfully.")
            self.update_dashboard_stats()
            QMessageBox.information(self, "Success", "Systemd user service removed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to remove systemd service: {e}")
            QMessageBox.critical(self, "Error", f"Failed to remove systemd service: {str(e)}")

    def update_autostart_setting(self, enabled: bool):
        if not hasattr(self, "autostart_manager"):
            from src.utils.autostart import AutostartManager
            self.autostart_manager = AutostartManager(self.logger)
        if enabled:
            self.autostart_manager.enable_autostart()
        else:
            self.autostart_manager.disable_autostart()

    def on_autostart_clicked(self, checked: bool):
        if not hasattr(self, "autostart_manager"):
            from src.utils.autostart import AutostartManager
            self.autostart_manager = AutostartManager(self.logger)
        if checked:
            success = self.autostart_manager.enable_autostart()
            if success:
                self.config.set("autostart", True)
                self.show_notification("SmartSort Startup", "SmartSort will start automatically when you log in.")
            else:
                self.chk_autostart.setChecked(False)
                self.config.set("autostart", False)
                self.show_notification("SmartSort Error", "Failed to enable automatic startup.")
                QMessageBox.critical(self, "Error", "Failed to enable automatic startup.")
        else:
            success = self.autostart_manager.disable_autostart()
            if success:
                self.config.set("autostart", False)
                self.show_notification("SmartSort Startup", "Automatic startup disabled.")
            else:
                self.chk_autostart.setChecked(True)
                self.config.set("autostart", True)
                self.show_notification("SmartSort Error", "Failed to disable automatic startup.")
                QMessageBox.critical(self, "Error", "Failed to disable automatic startup.")

    def on_start_minimized_clicked(self, checked: bool):
        self.config.set("start_minimized", checked)
        if checked:
            self.show_notification("SmartSort Startup", "SmartSort will start minimized to the system tray.")
        else:
            self.show_notification("SmartSort Startup", "SmartSort will start with the dashboard visible.")

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
            if hasattr(self, "show_notification"):
                self.show_notification("SmartSort", "SmartSort is still running in the system tray.")
            else:
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
        if detect_package_type() == PackageType.FLATPAK:
            self.notifications_enabled = True
        else:
            try:
                import notify2
                notify2.init("SmartSort")
                self.notifications_enabled = True
            except Exception:
                pass

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
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)
        
        # Header layout
        header_layout = QHBoxLayout()
        lbl_header = QLabel("SmartSort Dashboard")
        lbl_header.setObjectName("dashboard_header_title")
        lbl_header.setStyleSheet("font-size: 20px; font-weight: bold;")
        header_layout.addWidget(lbl_header)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)
        
        # Grid of cards
        grid_layout = QGridLayout()
        grid_layout.setSpacing(12)
        
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
        
        # Status layout
        status_card = QFrame()
        status_card.setProperty("class", "Card")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(12, 10, 12, 10)
        self.lbl_status = QLabel("Status: Monitoring Downloads...")
        self.lbl_status.setStyleSheet("font-weight: bold; font-size: 13px;")
        status_layout.addWidget(self.lbl_status)
        status_layout.addStretch()
        main_layout.addWidget(status_card)
        
        # Log display
        main_layout.addWidget(QLabel("Recent Activity (Daemon Logs):"))
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("font-family: 'Courier New', monospace; font-size: 11px;")
        main_layout.addWidget(self.log_display)
        
        self.tab_dashboard.setLayout(main_layout)

    def setup_logs(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header
        lbl_header = QLabel("Operation History")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(lbl_header)
        
        # Table of logs
        self.table_logs = QTableWidget(0, 5)
        self.table_logs.setHorizontalHeaderLabels(["Timestamp", "File", "Action", "Result", "Message"])
        self.table_logs.setAlternatingRowColors(True)
        self.table_logs.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_logs.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_logs.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table_logs)
        
        # Buttons layout
        btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("Refresh Logs")
        btn_refresh.setObjectName("primary")
        btn_refresh.clicked.connect(self.refresh_logs)
        btn_layout.addWidget(btn_refresh)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        self.tab_logs.setLayout(layout)

    def setup_rules(self):
        layout = QHBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Table of rules
        self.table_rules = QTableWidget(0, 4)
        self.table_rules.setHorizontalHeaderLabels(["Name", "Priority", "Enabled", "Destination"])
        self.table_rules.setAlternatingRowColors(True)
        self.table_rules.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_rules.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_rules.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table_rules)
        
        # Buttons layout
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)
        self.btn_add_rule = QPushButton("Add")
        self.btn_add_rule.setObjectName("primary")
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
        
        # Add a subtle line separator for rule management vs order
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        sep1.setStyleSheet("background-color: #333333;" if self.config.get("theme", "system") == "dark" else "background-color: #e1dedb;")
        btn_layout.addWidget(sep1)
        
        btn_layout.addWidget(self.btn_move_up)
        btn_layout.addWidget(self.btn_move_down)
        
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        sep2.setStyleSheet("background-color: #333333;" if self.config.get("theme", "system") == "dark" else "background-color: #e1dedb;")
        btn_layout.addWidget(sep2)
        
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
        
        # 1. Application Startup Group
        group_general = QGroupBox("Application Startup")
        gen_layout = QVBoxLayout(group_general)
        
        from src.utils.autostart import AutostartManager
        if not hasattr(self, "autostart_manager"):
            self.autostart_manager = AutostartManager(self.logger)
        actual_autostart = self.autostart_manager.is_autostart_enabled()
        self.chk_autostart = QCheckBox("Start SmartSort automatically when I log in")
        self.chk_autostart.setChecked(actual_autostart)
        if self.config.get("autostart") != actual_autostart:
            self.config.set("autostart", actual_autostart)
        self.chk_autostart.clicked.connect(self.on_autostart_clicked)
        
        self.chk_start_minimized = QCheckBox("Start minimized to tray")
        self.chk_start_minimized.setChecked(bool(self.config.get("start_minimized", False)))
        self.chk_start_minimized.clicked.connect(self.on_start_minimized_clicked)
        
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
        
        # 4. Background Monitoring Group
        group_service = QGroupBox("Background Monitoring")
        svc_layout = QVBoxLayout(group_service)
        
        self.lbl_service_control_status = QLabel("Service status: Checking...")
        self.lbl_service_control_status.setStyleSheet("font-weight: bold;")
        svc_layout.addWidget(self.lbl_service_control_status)
        
        # Create all buttons
        self.btn_install_service = QPushButton("Install Service")
        self.btn_remove_service = QPushButton("Remove Service")
        self.btn_update_service = QPushButton("Update Service")
        self.btn_start_service = QPushButton("Start")
        self.btn_stop_service = QPushButton("Stop")
        self.btn_restart_service = QPushButton("Restart")
        self.btn_enable_service = QPushButton("Enable")
        self.btn_disable_service = QPushButton("Disable")
        
        # Connect click handlers
        self.btn_install_service.clicked.connect(self.install_service)
        self.btn_remove_service.clicked.connect(self.remove_appimage_service)
        self.btn_update_service.clicked.connect(self.update_appimage_service)
        self.btn_start_service.clicked.connect(self.start_service)
        self.btn_stop_service.clicked.connect(self.stop_service)
        self.btn_restart_service.clicked.connect(self.restart_service)
        self.btn_enable_service.clicked.connect(self.enable_service)
        self.btn_disable_service.clicked.connect(self.disable_service)
        
        pkg_type = detect_package_type()
        if pkg_type == PackageType.FLATPAK:
            self.lbl_service_control_status.setText("Background Service: Unavailable")
            self.lbl_service_info = QLabel("Background services are not available inside the Flatpak sandbox.")
            self.lbl_service_info.setWordWrap(True)
            self.lbl_service_info.setStyleSheet("color: #a0a0a0; font-style: italic;")
            svc_layout.addWidget(self.lbl_service_info)
            
            # Hide all buttons
            self.btn_install_service.setVisible(False)
            self.btn_remove_service.setVisible(False)
            self.btn_update_service.setVisible(False)
            self.btn_start_service.setVisible(False)
            self.btn_stop_service.setVisible(False)
            self.btn_restart_service.setVisible(False)
            self.btn_enable_service.setVisible(False)
            self.btn_disable_service.setVisible(False)
        elif pkg_type == PackageType.APPIMAGE:
            self.btn_install_service.setText("Install Background Service")
            self.btn_remove_service.setText("Remove")
            self.btn_update_service.setText("Update")
            
            h_svc_btns = QHBoxLayout()
            h_svc_btns.addWidget(self.btn_install_service)
            h_svc_btns.addWidget(self.btn_update_service)
            h_svc_btns.addWidget(self.btn_remove_service)
            svc_layout.addLayout(h_svc_btns)
            
            # Hide non-AppImage buttons
            self.btn_start_service.setVisible(False)
            self.btn_stop_service.setVisible(False)
            self.btn_restart_service.setVisible(False)
            self.btn_enable_service.setVisible(False)
            self.btn_disable_service.setVisible(False)
        else: # DEBIAN / SOURCE
            self.btn_install_service.setText("Install Service")
            self.btn_remove_service.setText("Remove Service")
            
            h_row1 = QHBoxLayout()
            h_row1.addWidget(self.btn_install_service)
            h_row1.addWidget(self.btn_remove_service)
            h_row1.addWidget(self.btn_enable_service)
            h_row1.addWidget(self.btn_disable_service)
            svc_layout.addLayout(h_row1)
            
            h_row2 = QHBoxLayout()
            h_row2.addWidget(self.btn_start_service)
            h_row2.addWidget(self.btn_stop_service)
            h_row2.addWidget(self.btn_restart_service)
            svc_layout.addLayout(h_row2)
            
            # Hide AppImage specific buttons
            self.btn_update_service.setVisible(False)
            
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
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header
        lbl_header = QLabel("Rule Matching Tester")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(lbl_header)
        
        # Input Form
        form_widget = QWidget()
        form_widget.setProperty("class", "Card")
        form = QFormLayout(form_widget)
        form.setSpacing(10)
        
        self.txt_test_filename = QLineEdit("wallpaper.jpg")
        self.txt_test_size = QLineEdit("1.2MB")
        self.txt_test_size.setPlaceholderText("e.g. 1.2MB, 500KB, 2.5GB")
        
        self.txt_test_ext = QLineEdit(".jpg")
        self.txt_test_ext.setPlaceholderText("e.g. .jpg, .png (optional)")
        
        form.addRow("Filename:", self.txt_test_filename)
        form.addRow("File Size:", self.txt_test_size)
        form.addRow("Extension:", self.txt_test_ext)
        layout.addWidget(form_widget)
        
        btn_test = QPushButton("Test Rule Matching")
        btn_test.setObjectName("primary")
        btn_test.clicked.connect(self.run_rule_test)
        layout.addWidget(btn_test)
        
        group = QGroupBox("Test Results Output")
        g_layout = QFormLayout()
        g_layout.setSpacing(10)
        
        self.lbl_test_match = QLabel("None")
        self.lbl_test_match.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.lbl_test_priority = QLabel("N/A")
        self.lbl_test_priority.setStyleSheet("font-weight: bold;")
        self.lbl_test_dest = QLabel("N/A")
        self.lbl_test_dest.setStyleSheet("font-weight: bold;")
        
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
        log_dir = self.logger.log_dir
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
        if detect_package_type() == PackageType.FLATPAK:
            import subprocess
            try:
                # Use Desktop Notifications portal via gdbus call
                res = subprocess.run([
                    "gdbus", "call", "--session",
                    "--dest", "org.freedesktop.portal.Desktop",
                    "--object-path", "/org/freedesktop/portal/desktop",
                    "--method", "org.freedesktop.portal.Notification.AddNotification",
                    "",
                    f"{{'title': <'{title}'>, 'body': <'{message}'>}}"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0)
                if res.returncode == 0:
                    return
            except Exception:
                pass
            
            # Fallback to tray message if gdbus fails
            try:
                if hasattr(self, "tray_manager") and self.tray_manager and self.tray_manager.tray_icon:
                    self.tray_manager.tray_icon.showMessage(title, message)
            except Exception:
                pass
        else:
            try:
                import notify2
                n = notify2.Notification(title, message)
                n.show()
            except:
                try:
                    if hasattr(self, "tray_manager") and self.tray_manager and self.tray_manager.tray_icon:
                        self.tray_manager.tray_icon.showMessage(title, message)
                except Exception:
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
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        form = QFormLayout()
        form.setSpacing(10)
        
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
