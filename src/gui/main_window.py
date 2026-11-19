import sys
from pathlib import Path
import os
import re
import uuid
import threading
import time
import copy
import json
import math
from types import SimpleNamespace
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, 
                             QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QTextEdit, QTableWidget, QTableWidgetItem, 
                             QFileDialog, QSpinBox, QCheckBox, QMessageBox,
                             QFormLayout, QGroupBox, QLineEdit, QComboBox, 
                             QDialog, QDialogButtonBox, QSystemTrayIcon, QMenu, QFrame,
                             QProgressBar, QScrollArea, QButtonGroup, QPlainTextEdit,
                             QAbstractItemView, QHeaderView)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRunnable, QThreadPool, QObject, QEvent, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFontDatabase
from datetime import datetime

from src.utils.config import ConfigManager
from src.utils.logger import SmartSortLogger
from src.organizer import FileOrganizer
from src.monitor import FileMonitor
from src.utils.packaging import detect_package_type, PackageType, Capability, has_capability
from src.core.directory_organizer import (
    DirectoryOrganizer, OrganizePlan, OrganizeResult,
    DirectoryPreviewSummary, OperationStatus
)

class SortingTestSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(object)


class SortingTestWorker(QRunnable):
    def __init__(self, request_id, key, settings, rules, file_path):
        super().__init__()
        self.request_id, self.key = request_id, key
        self.settings, self.rules = copy.deepcopy(settings), copy.deepcopy(rules)
        self.file_path = file_path
        self.signals = SortingTestSignals()

    def run(self):
        from src.core.sorting_tester import preview_sorting
        try:
            result = preview_sorting(self.settings, self.rules, file_path=self.file_path)
            self.signals.finished.emit((self.request_id, self.key, result))
        except Exception as error:
            self.signals.error.emit((self.request_id, self.key, str(error)))


class DirectoryOrganizerSignals(QObject):
    progress = pyqtSignal(int, int, str)       # (processed, total, current_file)
    preview_ready = pyqtSignal(object)         # (DirectoryPreviewSummary)
    finished = pyqtSignal(object, str)         # (OrganizeResult, report_path)
    reversed = pyqtSignal(int, object)
    error = pyqtSignal(str)                    # (error_message)

class DirectoryOrganizerWorker(QRunnable):
    def __init__(self, organizer: DirectoryOrganizer, root_dir: str, mode: str = "organize",
                 recursive: bool = False, generate_report: bool = True, plan=None, review_key=None,
                 execution_options=None):
        super().__init__()
        self.organizer = organizer
        if mode == "preview":
            # Bind queued previews to the selected mode and rules at creation.
            selected_mode = organizer.config.get("sorting_mode", "rules_first")
            original_config = organizer.config
            self.organizer = copy.copy(organizer)
            self.organizer.config = SimpleNamespace(get=lambda key, default=None:
                selected_mode if key == "sorting_mode" else original_config.get(key, default))
            self.organizer.rule_manager = SimpleNamespace(rules=copy.deepcopy(organizer.rule_manager.rules))
        self.root_dir = root_dir
        self.mode = mode
        self.recursive = recursive
        self.generate_report = generate_report
        self.review_plan = copy.deepcopy(plan)
        self.undo = None
        self.review_key = review_key
        self.execution_options = dict(execution_options) if execution_options else None
        self.signals = DirectoryOrganizerSignals()
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            if self.mode == "reverse":
                self.signals.reversed.emit(*self.undo.reverse())
            elif self.mode == "preview":
                if self.cancel_event.is_set():
                    self.signals.finished.emit(OrganizeResult(records=[], cancelled=True), "")
                    return
                files = self.organizer.scan(self.root_dir, recursive=self.recursive)
                plan = self.organizer.plan(self.root_dir, files)
                self.review_plan = copy.deepcopy(plan)
                summary = DirectoryPreviewSummary(plan.total_files, dict(plan.category_counts),
                    copy.deepcopy(plan.items), plan.cluster_count, list(plan.warnings))
                if self.cancel_event.is_set():
                    self.signals.finished.emit(OrganizeResult(records=[], cancelled=True), "")
                else:
                    self.signals.preview_ready.emit(summary)
            elif self.mode == "organize":
                if self.cancel_event.is_set():
                    res = OrganizeResult(records=[], cancelled=True)
                    self.signals.finished.emit(res, "")
                    return
                plan = self.review_plan
                if plan is None:
                    # Legacy direct-worker callers retain scan/plan behavior.
                    files = self.organizer.scan(self.root_dir, recursive=self.recursive)
                    plan = self.organizer.plan(self.root_dir, files)
                if self.cancel_event.is_set():
                    res = OrganizeResult(records=[], cancelled=True)
                    self.signals.finished.emit(res, "")
                    return

                def progress_cb(processed, total, cur_file):
                    self.signals.progress.emit(processed, total, cur_file)

                def cancel_check():
                    return self.cancel_event.is_set()

                executor = self.organizer
                if self.execution_options is not None:
                    executor = copy.copy(self.organizer)
                    original_config = self.organizer.config
                    options = self.execution_options
                    executor.config = SimpleNamespace(get=lambda key, default=None:
                        options[key] if key in options else original_config.get(key, default))
                result = executor.execute(plan, progress_callback=progress_cb,
                                                cancel_check=cancel_check, capture_undo=True)
                report_path = ""
                if self.generate_report and (result.success_count > 0 or result.collision_count > 0
                                             or result.duplicate_count > 0 or result.error_count > 0):
                    try:
                        report_path = self.organizer.generate_report(self.root_dir, result)
                    except OSError as error:
                        result.warnings.append(f"Could not write arrangement report: {error}")
                if result.undo:
                    result.undo.complete()
                self.signals.finished.emit(result, report_path)
        except Exception as e:
            self.signals.error.emit(str(e))

class WorkerSignals(QObject):
    finished = pyqtSignal(str, str, str) # file_path, result, info
    error = pyqtSignal(str, str) # file_path, error_msg


_REVIEW_CONTROLS = {i: f"\\x{i:02x}" for i in (*range(32), 127)}


def review_text(value):
    """Keep Unicode literal while preventing controls from forging review rows."""
    return str(value).translate(_REVIEW_CONTROLS)


def confidence_tag(item):
    level = getattr(item, "confidence", "UNKNOWN")
    if level not in ("CONFIRMED", "PROBABLE", "UNCERTAIN", "UNKNOWN", "NOT_AVAILABLE"):
        level = "UNKNOWN"
    score = getattr(item, "confidence_score", None)
    if (isinstance(score, bool) or not isinstance(score, (int, float)) or
            not math.isfinite(score) or not 0 <= score <= 1):
        return f"[{level}]"
    return f"[{level} ({score:.0%})]"


def format_directory_review(summary, root_dir):
    root_prefix = os.path.join(os.path.abspath(root_dir), "")
    lines = ["=== DRY-RUN PREVIEW SUMMARY ===", f"Planned moves: {summary.total_files}",
             f"Clusters discovered: {summary.cluster_count}"]
    if not summary.items:
        lines.append("  No moves proposed; sources may already be organized or excluded.")
    if summary.warnings:
        lines.extend(["", f"Planning warnings ({len(summary.warnings)}):"])
        lines.extend(f"  • {review_text(warning)}" for warning in summary.warnings)
    lines.extend(["", "Planned Moves:"])
    for index, item in enumerate(summary.items, 1):
        try:
            destination = (item.target_path[len(root_prefix):] if item.target_path.startswith(root_prefix)
                           else os.path.relpath(item.target_path, root_dir))
        except ValueError:
            destination = item.target_path
        lines.append(f"  {index}. {review_text(os.path.basename(item.source_path))} -> {review_text(destination)} {confidence_tag(item)}")
        if item.cluster_name:
            lines.append(f"    Cluster: {review_text(item.cluster_name)}")
        if item.evidence:
            lines.extend(f"    Evidence: {review_text(reason)}" for reason in item.evidence[:8])
            if len(item.evidence) > 8:
                lines.append(f"    {len(item.evidence) - 8} further reasons — use Inspect evidence for the full list.")
        else:
            lines.append("    Evidence: No detailed evidence available.")
    lines.extend(["", "Category Breakdown:"])
    lines.extend(f"  • {review_text(cat)}: {count} file(s)" for cat, count in sorted(summary.category_counts.items()))
    lines.extend(["", "Confidence is a classification estimate, not a correctness probability.",
                  "Configured rules take priority; a confirmed rule match confirms that policy."])
    return "\n".join(lines)


class EvidenceDialog(QDialog):
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.setWindowTitle("File evidence")
        self.resize(720, 480)
        layout = QVBoxLayout(self)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.details.setStyleSheet("font-family: 'DejaVu Sans Mono', monospace; font-size: 12px;")
        lines = [review_text(os.path.basename(item.source_path)), confidence_tag(item),
                 f"Source: {review_text(item.source_path)}", f"Destination: {review_text(item.target_path)}",
                 f"Rule: {review_text(item.rule_name)}", f"Cluster: {review_text(item.cluster_name) or 'None'}",
                 "", "Classification estimate; not a probability of correctness.", "", "Evidence:"]
        lines.extend(f"• {review_text(reason)}" for reason in item.evidence)
        if not item.evidence:
            lines.append("No detailed evidence available.")
        self.details.setPlainText("\n".join(lines))
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ServiceStatusSignals(QObject):
    ready = pyqtSignal(str, bool)


class ServiceStatusWorker(QRunnable):
    """Keep potentially slow systemctl calls out of the GUI event loop."""

    def __init__(self, query):
        super().__init__()
        self.query = query
        self.signals = ServiceStatusSignals()

    def run(self):
        status, enabled = "Unavailable", False
        try:
            status = self.query()
            if status in ("Running", "Stopped", "Disabled"):
                import subprocess
                result = subprocess.run(
                    ["systemctl", "--user", "is-enabled", "smartsort.service"],
                    capture_output=True, text=True, check=False, timeout=2.0)
                enabled = result.stdout.strip() == "enabled"
        except Exception:
            enabled = status == "Stopped"
        self.signals.ready.emit(status, enabled)


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
    def __init__(self, config=None):
        super().__init__()
        self.setWindowTitle("SmartSort - File Organizer")
        self.resize(1100, 780)
        self.setMinimumSize(860, 620)
        
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
        self.config = config if config is not None else ConfigManager()
        self.logger = SmartSortLogger()
        self.organizer = FileOrganizer(self.config, self.logger)
        self.dir_organizer = DirectoryOrganizer(self.config, self.logger)
        self.active_dir_worker = None
        self._reviewed_plan = None
        self._review_key = None
        self._review_items = []
        self._sorting_mode_labels = []
        self._executing_review = None
        self.last_report_path = ""
        from src.utils.autostart import AutostartManager
        self.autostart_manager = AutostartManager(self.logger)
        self.threadpool = QThreadPool()
        self._service_status = "Checking…"
        self._service_enabled = False
        self._service_worker = None
        
        self.stats = {"processed": 0, "duplicates": 0, "errors": 0}
        self.really_exit = False
        self.monitoring_active = True
        self.last_activity_time = "Never"
        
        self.init_notification_system()
        self.init_ui()
        
        self.tray_available = False
        try:
            self.setup_system_tray()
            self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
            if not self.tray_available:
                self.tray_icon.hide()
        except Exception as e:
            self.logger.warning(f"System tray initialization failed: {e}")
            
        self.apply_theme()
        
        from PyQt6.QtCore import QTimer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_dashboard)
        self.update_dashboard_stats()
        if "PYTEST_CURRENT_TEST" not in os.environ:
            self.status_timer.start(3000)
            self.refresh_dashboard()
        
        if "PYTEST_CURRENT_TEST" not in os.environ:
            QTimer.singleShot(0, self.start_monitor)
        
        if self.tray_available and "PYTEST_CURRENT_TEST" not in os.environ:
            QTimer.singleShot(2000, self.finish_startup)
            
        # Run startup verification and repair check on launch
        if "PYTEST_CURRENT_TEST" not in os.environ:
            QTimer.singleShot(1000, self.verify_and_repair_startup_config)

    def setup_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        from src.gui.tray_manager import TrayStateManager
        self.tray_manager = TrayStateManager(self.tray_icon, self)
        self.tray_manager.set_startup()
        
        menu = QMenu(self)
        
        act_dashboard = menu.addAction("Open Dashboard")
        act_dashboard.triggered.connect(lambda: self.show_tab(0))
        
        act_rules = menu.addAction("Open Rules")
        act_rules.triggered.connect(lambda: self.show_tab(self.tabs.indexOf(self.tab_rules)))
        
        act_tester = menu.addAction("Open Rule Tester")
        act_tester.triggered.connect(lambda: self.show_tab(self.tabs.indexOf(self.tab_tester)))
        
        act_settings = menu.addAction("Open Settings")
        act_settings.triggered.connect(lambda: self.show_tab(self.tabs.indexOf(self.tab_settings)))
        
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
        from src.utils.paths import AppPaths
        from src.version import VERSION
        msg = QMessageBox(self)
        msg.setWindowTitle("About SmartSort")
        msg.setText(f"<b>SmartSort File Organizer</b><br>Version {VERSION}<br><br>An intelligent, rule-based daemon and GUI to organize your downloads folder automatically.")
        
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
        self.set_label_tone(self.lbl_monitoring_val, "warning")
        self.btn_toggle_monitor.setText("Resume monitoring")
        self.lbl_status.setText("Status: Monitoring Paused")
        if hasattr(self, "act_pause"):
            self.act_pause.setEnabled(False)
            self.act_resume.setEnabled(True)
        self.logger.info("Monitoring paused by user")
        if self.tray_available:
            active_rules = len([r for r in self.organizer.rule_manager.rules if r.enabled])
            self.tray_manager.set_paused(self.stats.get("processed", 0), active_rules)

    def resume_monitoring(self):
        self.monitoring_active = True
        self.lbl_monitoring_val.setText("Running")
        self.set_label_tone(self.lbl_monitoring_val, "success")
        self.btn_toggle_monitor.setText("Pause monitoring")
        self.lbl_status.setText("Status: Monitoring Downloads...")
        if hasattr(self, "act_pause"):
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
            f"Duplicate sources removed: {self.stats['duplicates']}\n"
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
        guard = getattr(self, "_instance_guard", None)
        if guard is not None:
            guard.close()
        import subprocess
        subprocess.Popen([sys.executable, sys.argv[0]] + sys.argv[1:])
        QApplication.quit()

    def exit_application(self):
        self.really_exit = True
        self.close()
        QApplication.quit()

    def is_system_dark_mode(self) -> bool:
        # Use Qt's platform preference; do not spawn gsettings on every change.
        hints = QApplication.styleHints()
        if hasattr(hints, "colorScheme") and hints.colorScheme() != Qt.ColorScheme.Unknown:
            return hints.colorScheme() == Qt.ColorScheme.Dark
        from PyQt6.QtGui import QPalette
        return QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128

    def apply_theme(self):
        from src.gui.theme import DARK, LIGHT, palette, stylesheet
        theme_setting = self.config.get("theme", "system")
        self.is_dark_theme = (theme_setting == "dark" or
                              (theme_setting == "system" and self.is_system_dark_mode()))
        self.theme_colors = DARK if self.is_dark_theme else LIGHT
        self.setPalette(palette(self.theme_colors))
        self.setStyleSheet(stylesheet(self.theme_colors))
        for combo in (self.theme_picker, self.cmb_theme):
            combo.blockSignals(True)
            combo.setCurrentIndex({"system": 0, "dark": 1, "light": 2}.get(theme_setting, 0))
            combo.blockSignals(False)

    def change_theme(self, index):
        self.config.set("theme", ("system", "dark", "light")[index])
        self.apply_theme()

    def on_system_theme_changed(self, _scheme):
        if self.config.get("theme", "system") == "system":
            self.apply_theme()

    @staticmethod
    def set_label_tone(label, tone):
        label.setProperty("tone", tone)
        label.style().unpolish(label)
        label.style().polish(label)

    def create_card(self, title, val):
        from PyQt6.QtWidgets import QFrame
        card = QFrame()
        card.setObjectName(title.replace(" ", "_").lower())
        card.setProperty("class", "Card")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        
        layout = QVBoxLayout(card)
        layout.setSpacing(4)
        layout.setContentsMargins(18, 16, 18, 16)
        
        lbl_title = QLabel(title)
        lbl_title.setObjectName("card_title")
        lbl_title.setWordWrap(True)
        lbl_val = QLabel(val)
        lbl_val.setObjectName("card_value")
        lbl_val.setWordWrap(True)
        
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
        self.set_label_tone(self.lbl_monitoring_val, "success" if self.monitoring_active else "warning")
        self.btn_toggle_monitor.setText("Pause monitoring" if self.monitoring_active else "Resume monitoring")
        svc_status = self._service_status
        self.lbl_service_val.setText(svc_status)
        self.set_label_tone(self.lbl_service_val, "success" if svc_status == "Running" else "warning")

        active_rules = len([r for r in self.organizer.rule_manager.rules if r.enabled])
        total_rules = len(self.organizer.rule_manager.rules)
        manual_rules = sum(r.enabled and r.apply_in_intelligence for r in self.organizer.rule_manager.rules)
        self.lbl_rules_val.setText((f"{manual_rules} manual" if manual_rules else "Not applied")
            if self.config.get("sorting_mode", "rules_first") == "intelligence" else f"{active_rules} / {total_rules}")
        
        self.lbl_activity_val.setText(getattr(self, "last_activity_time", "Never"))
        
        if hasattr(self, "lbl_service_control_status"):
            self.lbl_service_control_status.setText(f"Service status: {svc_status}")
            
        if hasattr(self, "btn_install_service"):
            if svc_status == "Not Installed":
                self.btn_install_service.setEnabled(True)
                self.btn_remove_service.setEnabled(False)
                self.btn_start_service.setEnabled(False)
                self.btn_stop_service.setEnabled(False)
                self.btn_restart_service.setEnabled(False)
                self.btn_enable_service.setEnabled(False)
                self.btn_disable_service.setEnabled(False)
            elif svc_status in ("Checking…", "Unavailable"):
                for button in (self.btn_install_service, self.btn_remove_service,
                               self.btn_start_service, self.btn_stop_service,
                               self.btn_restart_service, self.btn_enable_service,
                               self.btn_disable_service):
                    button.setEnabled(False)
            else:
                self.btn_install_service.setEnabled(False)
                self.btn_remove_service.setEnabled(True)
                self.btn_start_service.setEnabled(svc_status != "Running")
                self.btn_stop_service.setEnabled(svc_status == "Running")
                self.btn_restart_service.setEnabled(svc_status == "Running")

                self.btn_enable_service.setEnabled(not self._service_enabled)
                self.btn_disable_service.setEnabled(self._service_enabled)
                
        from src.gui.tray_manager import TrayState
        if self.tray_available and self.tray_manager.current_state in [TrayState.IDLE, TrayState.PAUSED, TrayState.ERROR]:
            if getattr(self, "monitoring_active", True):
                self.tray_manager.set_monitoring(self.stats.get("processed", 0), active_rules)
            else:
                self.tray_manager.set_paused(self.stats.get("processed", 0), active_rules)

    def refresh_dashboard(self):
        self.update_dashboard_stats()
        if self._service_worker is None:
            worker = ServiceStatusWorker(self.get_service_status)
            worker.signals.ready.connect(self.on_service_status_ready)
            self._service_worker = worker
            self.threadpool.start(worker)

    def on_service_status_ready(self, status, enabled):
        self._service_status = status
        self._service_enabled = enabled
        self._service_worker = None
        self.update_dashboard_stats()

    def verify_and_repair_startup_config(self):
        # 1. Verify autostart desktop entry
        autostart_expected = bool(self.config.get("autostart", False))

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

    def get_service_status(self) -> str:
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
        import os
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
            if hasattr(self, "active_dir_worker") and self.active_dir_worker:
                try:
                    self.active_dir_worker.cancel()
                except Exception:
                    pass
            if hasattr(self, "threadpool"):
                try:
                    self.threadpool.waitForDone(2000)
                except Exception:
                    pass
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
        except Exception:
            pass

    def init_ui(self):
        shell = QWidget()
        shell.setObjectName("shell")
        outer = QHBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(shell)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(188)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 28, 16, 22)
        side.setSpacing(5)
        mark = QLabel("S")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(42, 42)
        side.addWidget(mark)
        brand = QLabel("SmartSort")
        brand.setObjectName("brand")
        side.addWidget(brand)
        tagline = QLabel("A place for every file.")
        tagline.setProperty("role", "muted")
        side.addWidget(tagline)
        side.addSpacing(30)
        eyebrow = QLabel("WORKSPACE")
        eyebrow.setObjectName("eyebrow")
        side.addWidget(eyebrow)
        side.addSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tab_dashboard = QWidget()
        self.tab_organizer = QWidget()
        self.tab_logs = QWidget()
        self.tab_rules = QWidget()
        self.tab_settings = QWidget()
        self.tab_tester = QWidget()
        pages = [
            (self.tab_dashboard, "Dashboard", "Overview", "Your files, quietly in order."),
            (self.tab_organizer, "Directory Organizer", "Organize a folder", "Preview the plan, then organize with confidence."),
            (self.tab_logs, "Logs", "Activity history", "A clear record of every file operation."),
            (self.tab_rules, "Rules", "Sorting rules", "Make your filing system work your way."),
            (self.tab_settings, "Settings", "Preferences", "Fine-tune the details of your workspace."),
            (self.tab_tester, "Rule Tester", "Rule tester", "Preview sorting decisions and evidence without moving files."),
        ]
        self.page_details = [(title, subtitle) for _, _, title, subtitle in pages]
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for i, (page, name, _, _) in enumerate(pages):
            self.tabs.addTab(page, name)
            button = QPushButton("Organize folder" if page is self.tab_organizer else name)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setToolTip(name)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav_group.addButton(button, i)
            self.nav_buttons.append(button)
            side.addWidget(button)
        self.nav_group.idClicked.connect(self.tabs.setCurrentIndex)
        self.nav_buttons[0].setChecked(True)
        side.addStretch()
        from src.version import VERSION
        footer = QLabel(f"LOCAL & PRIVATE\nSmartSort {VERSION}")
        footer.setProperty("role", "muted")
        side.addWidget(footer)
        outer.addWidget(sidebar)

        workspace = QVBoxLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(0)
        header = QFrame()
        header.setObjectName("pageHeader")
        head = QHBoxLayout(header)
        head.setContentsMargins(26, 24, 26, 22)
        titles = QVBoxLayout()
        titles.setSpacing(6)
        self.page_title = QLabel(self.page_details[0][0])
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel(self.page_details[0][1])
        self.page_subtitle.setObjectName("pageSubtitle")
        self.page_subtitle.setWordWrap(True)
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        head.addLayout(titles, 1)
        theme_box = QVBoxLayout()
        theme_caption = QLabel("APPEARANCE")
        theme_caption.setObjectName("eyebrow")
        self.theme_picker = QComboBox()
        self.theme_picker.setAccessibleName("Application appearance")
        self.theme_picker.addItems(["System", "Dark", "Light"])
        self.theme_picker.setMinimumWidth(112)
        theme_box.addWidget(theme_caption)
        theme_box.addWidget(self.theme_picker)
        head.addLayout(theme_box)
        workspace.addWidget(header)
        workspace.addWidget(self.tabs, 1)
        outer.addLayout(workspace, 1)
        self.tabs.currentChanged.connect(self.on_page_changed)

        self.setup_dashboard()
        self.setup_directory_organizer()
        self.setup_logs()
        self.setup_settings()
        self.setup_rules()
        self.setup_tester()
        self.theme_picker.currentIndexChanged.connect(self.change_theme)
        self.cmb_theme.currentIndexChanged.connect(self.change_theme)
        hints = QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self.on_system_theme_changed)
        for table in (self.table_logs, self.table_rules):
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setShowGrid(False)
            table.verticalHeader().hide()
            table.verticalHeader().setDefaultSectionSize(38)
            table.horizontalHeader().setMinimumSectionSize(70)
        self.log_display.setPlaceholderText("All clear. New file activity will appear here.")
        self.txt_organize_summary.setPlaceholderText("Choose a folder and preview the planned moves to get started.")
        self.refresh_logs()

    def on_page_changed(self, index):
        self.nav_buttons[index].setChecked(True)
        title, subtitle = self.page_details[index]
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        if self.tabs.widget(index) is self.tab_logs:
            self.refresh_logs()

    @staticmethod
    def scroll_page(page, content):
        """Keep every control reachable on small windows and scaled displays."""
        content.setObjectName("scrollContent")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    @staticmethod
    def _sorting_mode_description(mode):
        if mode == "intelligence":
            return "Content, filenames and context choose destinations. Marked manual rules apply; other saved rules are not applied."
        return "Matching rules choose destinations first. Content intelligence handles only unmatched files."

    def _sorting_mode_card(self):
        card = QFrame()
        card.setProperty("class", "Card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        description = QLabel()
        description.setTextFormat(Qt.TextFormat.PlainText)
        description.setWordWrap(True)
        layout.addWidget(description, 1)
        button = QPushButton("Change mode")
        button.setAccessibleName("Change sorting mode")
        button.clicked.connect(self._open_sorting_mode_settings)
        layout.addWidget(button)
        self._sorting_mode_labels.append(description)
        self._refresh_sorting_mode_summary()
        return card

    def _refresh_sorting_mode_summary(self):
        if hasattr(self, "lbl_test_match"):
            self._invalidate_tester_result()
        mode = self.config.get("sorting_mode", "rules_first")
        if mode == "intelligence":
            title = "Sorting mode: Content intelligence"
        else:
            count = sum(rule.enabled for rule in self.organizer.rule_manager.rules)
            title = f"Sorting mode: Rules first ({count} enabled)"
        if hasattr(self, "lbl_rules_val"):
            active = sum(rule.enabled for rule in self.organizer.rule_manager.rules)
            total = len(self.organizer.rule_manager.rules)
            manual = sum(r.enabled and r.apply_in_intelligence for r in self.organizer.rule_manager.rules)
            self.lbl_rules_val.setText((f"{manual} manual" if manual else "Not applied") if mode == "intelligence" else f"{active} / {total}")
        for label in self._sorting_mode_labels:
            label.setText(title + "\n" + self._sorting_mode_description(mode))

    def _open_sorting_mode_settings(self):
        self.tabs.setCurrentWidget(self.tab_settings)
        for scroll in self.tab_settings.findChildren(QScrollArea):
            scroll.ensureWidgetVisible(self.cmb_sorting_mode)
        self.cmb_sorting_mode.setFocus()

    def setup_dashboard(self):
        from PyQt6.QtWidgets import QGridLayout
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(18)
        main_layout.setContentsMargins(26, 24, 26, 24)
        main_layout.addWidget(self._sorting_mode_card())
        grid_layout = QGridLayout()
        grid_layout.setSpacing(12)
        self.card_processed, self.lbl_processed_val = self.create_card("Files processed", "0")
        self.card_duplicates, self.lbl_duplicates_val = self.create_card("Duplicate sources removed", "0")
        self.card_errors, self.lbl_errors_val = self.create_card("Errors encountered", "0")
        self.card_monitoring, self.lbl_monitoring_val = self.create_card("Download monitor", "Running")
        self.card_service, self.lbl_service_val = self.create_card("Background service", "Checking…")
        self.card_rules, self.lbl_rules_val = self.create_card("Configured rules", "0")
        self.card_activity, self.lbl_activity_val = self.create_card("Last activity", "Never")
        for col, card in enumerate((self.card_processed, self.card_duplicates, self.card_errors)):
            grid_layout.addWidget(card, 0, col)
            grid_layout.setColumnStretch(col, 1)
        for col, card in enumerate((self.card_monitoring, self.card_service, self.card_rules)):
            grid_layout.addWidget(card, 1, col)
        grid_layout.addWidget(self.card_activity, 2, 0, 1, 3)
        main_layout.addLayout(grid_layout)

        status_card = QFrame()
        status_card.setProperty("class", "Card")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(18, 14, 18, 14)
        self.lbl_status = QLabel("Monitoring your Downloads folder")
        self.lbl_status.setWordWrap(True)
        status_layout.addWidget(self.lbl_status, 1)
        self.btn_toggle_monitor = QPushButton("Pause monitoring")
        self.btn_toggle_monitor.clicked.connect(
            lambda: self.pause_monitoring() if self.monitoring_active else self.resume_monitoring())
        status_layout.addWidget(self.btn_toggle_monitor)
        btn_folder = QPushButton("Organize a folder")
        btn_folder.setObjectName("primary")
        btn_folder.clicked.connect(lambda: self.tabs.setCurrentWidget(self.tab_organizer))
        status_layout.addWidget(btn_folder)
        main_layout.addWidget(status_card)
        activity_title = QLabel("Recent activity")
        activity_title.setObjectName("sectionTitle")
        main_layout.addWidget(activity_title)
        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumBlockCount(500)
        self.log_display.setMinimumHeight(140)
        main_layout.addWidget(self.log_display, 1)
        self.scroll_page(self.tab_dashboard, content)

    def setup_directory_organizer(self):
        from PyQt6.QtWidgets import QFrame, QProgressBar
        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)
        
        
        # Target Directory Card
        dir_card = QFrame()
        dir_card.setProperty("class", "Card")
        dir_layout = QVBoxLayout(dir_card)
        dir_layout.setSpacing(8)
        dir_layout.setContentsMargins(12, 12, 12, 12)
        
        lbl_select = QLabel("Select Directory to Organize:")
        lbl_select.setStyleSheet("font-weight: bold;")
        dir_layout.addWidget(lbl_select)
        
        dir_input_layout = QHBoxLayout()
        self.txt_target_dir = QLineEdit()
        self.txt_target_dir.setPlaceholderText("/path/to/directory")
        last_path = self.config.get("dir_organizer_last_path", "")
        self.txt_target_dir.setText(last_path)
        self.btn_browse_dir = QPushButton("Browse...")
        dir_input_layout.addWidget(self.txt_target_dir)
        dir_input_layout.addWidget(self.btn_browse_dir)
        dir_layout.addLayout(dir_input_layout)
        
        options_layout = QVBoxLayout()
        self.chk_recursive = QCheckBox("Include subfolders")
        self.chk_recursive.setToolTip("Analyze nested files beneath the selected folder. Application and project bundles stay intact.")
        self.chk_recursive.setChecked(self._folder_recursion_enabled())
        self.chk_gen_report = QCheckBox("Generate Arrangement Index (SmartSort_Arrangement.md)")
        self.chk_gen_report.setChecked(self.config.get("dir_organizer_generate_markdown", True))
        options_layout.addWidget(self.chk_recursive)
        options_layout.addWidget(self.chk_gen_report)
        options_layout.addStretch()
        dir_layout.addLayout(options_layout)
        
        main_layout.addWidget(dir_card)
        
        main_layout.addWidget(self._sorting_mode_card())

        # Action Controls Layout
        actions_layout = QHBoxLayout()
        self.btn_preview = QPushButton("Preview / Dry Run")
        self.btn_organize = QPushButton("Review moves")
        self.btn_organize.setObjectName("primary")
        self.btn_cancel_organize = QPushButton("Cancel")
        self.btn_cancel_organize.setEnabled(False)
        
        actions_layout.addWidget(self.btn_preview)
        actions_layout.addWidget(self.btn_organize)
        actions_layout.addWidget(self.btn_cancel_organize)
        actions_layout.addStretch()
        main_layout.addLayout(actions_layout)
        
        # Progress Card
        progress_card = QFrame()
        progress_card.setProperty("class", "Card")
        prog_layout = QVBoxLayout(progress_card)
        prog_layout.setSpacing(6)
        prog_layout.setContentsMargins(12, 12, 12, 12)
        
        self.lbl_organize_status = QLabel("Status: Ready")
        self.lbl_organize_status.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_organize_status.setStyleSheet("font-weight: bold;")
        self.progress_organize = QProgressBar()
        self.progress_organize.setRange(0, 100)
        self.progress_organize.setValue(0)
        self.progress_organize.setTextVisible(False)
        self.lbl_organize_details = QLabel("No active operation")
        self.lbl_organize_details.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_organize_details.setProperty("role", "muted")
        self.lbl_organize_details.setWordWrap(True)
        
        prog_layout.addWidget(self.lbl_organize_status)
        prog_layout.addWidget(self.progress_organize)
        prog_layout.addWidget(self.lbl_organize_details)
        main_layout.addWidget(progress_card)
        
        # Results & Preview Card
        results_card = QFrame()
        results_card.setProperty("class", "Card")
        res_layout = QVBoxLayout(results_card)
        res_layout.setSpacing(8)
        res_layout.setContentsMargins(12, 12, 12, 12)
        
        self.lbl_results_title = QLabel("Review proposed moves")
        self.lbl_results_title.setStyleSheet("font-weight: bold;")
        res_layout.addWidget(self.lbl_results_title)
        
        self.txt_organize_summary = QPlainTextEdit()
        self.txt_organize_summary.setReadOnly(True)
        self.txt_organize_summary.setMinimumHeight(220)
        self.txt_organize_summary.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.txt_organize_summary.setStyleSheet("font-family: 'DejaVu Sans Mono', monospace; font-size: 12px;")
        res_layout.addWidget(self.txt_organize_summary)

        evidence_layout = QHBoxLayout()
        self.cmb_review_file = QComboBox()
        self.cmb_review_file.setMinimumContentsLength(18)
        self.cmb_review_file.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_review_file.setToolTip("Choose a reviewed file to inspect all of its evidence.")
        self.btn_inspect_evidence = QPushButton("Inspect evidence…")
        self.btn_inspect_evidence.setEnabled(False)
        self.cmb_review_file.setEnabled(False)
        evidence_layout.addWidget(self.cmb_review_file, 1)
        evidence_layout.addWidget(self.btn_inspect_evidence)
        res_layout.addLayout(evidence_layout)
        
        btn_results_layout = QHBoxLayout()
        self.btn_open_target_folder = QPushButton("Open Folder")
        self.btn_open_target_folder.setEnabled(False)
        self.btn_open_arrangement_md = QPushButton("Open Arrangement Report")
        self.btn_open_arrangement_md.setEnabled(False)
        btn_results_layout.addWidget(self.btn_open_target_folder)
        btn_results_layout.addWidget(self.btn_open_arrangement_md)
        btn_results_layout.addStretch()
        res_layout.addLayout(btn_results_layout)
        self.undo_layout = QVBoxLayout()
        res_layout.addLayout(self.undo_layout)
        self.undo_offers = []
        self.undo_timer = QTimer(self)
        self.undo_timer.setInterval(1000)
        self.undo_timer.timeout.connect(self._refresh_undo_offers)
        
        main_layout.addWidget(results_card)
        
        content = QWidget()
        content.setLayout(main_layout)
        self.scroll_page(self.tab_organizer, content)
        
        # Connect signals
        self.btn_browse_dir.clicked.connect(self.on_browse_target_dir)
        self.btn_preview.clicked.connect(self.on_preview_dir)
        self.btn_organize.clicked.connect(self.on_organize_dir)
        self.btn_inspect_evidence.clicked.connect(self.on_inspect_evidence)
        self.btn_cancel_organize.clicked.connect(self.on_cancel_organize)
        self.btn_open_target_folder.clicked.connect(self.on_open_target_folder)
        self.btn_open_arrangement_md.clicked.connect(self.on_open_arrangement_report)
        self.chk_recursive.stateChanged.connect(self.on_dir_organizer_options_changed)
        self.chk_gen_report.stateChanged.connect(self.on_dir_organizer_options_changed)
        self.txt_target_dir.textChanged.connect(self.on_dir_organizer_options_changed)

    def on_browse_target_dir(self):
        cur = self.txt_target_dir.text().strip() or os.path.expanduser("~")
        selected = QFileDialog.getExistingDirectory(self, "Select Directory to Organize", cur)
        if selected:
            self.txt_target_dir.setText(selected)
            self.config.set("dir_organizer_last_path", selected)
            self.config.save_config()

    def _folder_recursion_enabled(self):
        if self.config.get("sorting_mode", "rules_first") == "intelligence":
            return self.config.get("intelligence_recursive", True)
        return self.config.get("dir_organizer_recursive", False)

    def on_dir_organizer_options_changed(self):
        if self._review_key is not None and self._review_key != self._directory_review_key():
            self._invalidate_dir_review()
        path = self.txt_target_dir.text().strip()
        if path != self.config.get("dir_organizer_last_path", ""):
            self.last_report_path = ""
            self.btn_open_arrangement_md.setEnabled(False)
            self.btn_open_target_folder.setEnabled(False)
        self.config.set("dir_organizer_last_path", path)
        recursive_key = "intelligence_recursive" if self.config.get("sorting_mode", "rules_first") == "intelligence" else "dir_organizer_recursive"
        self.config.set(recursive_key, self.chk_recursive.isChecked())
        self.config.set("dir_organizer_generate_markdown", self.chk_gen_report.isChecked())
        self.config.save_config()

    def _validate_organizer_input(self):
        target_dir = self.txt_target_dir.text().strip()
        if not target_dir:
            QMessageBox.warning(self, "Directory Organizer", "Please select a directory to organize.")
            return None
        target_dir = os.path.abspath(os.path.expanduser(target_dir))
        if not os.path.exists(target_dir):
            QMessageBox.warning(self, "Directory Organizer", f"Directory does not exist:\n{target_dir}")
            return None
        if not os.path.isdir(target_dir):
            QMessageBox.warning(self, "Directory Organizer", f"Selected path is not a directory:\n{target_dir}")
            return None
        try:
            target_dir = self.dir_organizer._validate_root(target_dir)
        except ValueError as exc:
            QMessageBox.critical(self, "Directory Organizer", str(exc))
            return None
        return target_dir

    def _directory_review_key(self):
        if not hasattr(self, "txt_target_dir"):
            return None
        settings = tuple(self.config.get(key, default) for key, default in (
            ("enable_origin_detection", True), ("enable_deep_content_extraction", True),
            ("conflict_resolution", "rename"), ("enable_duplicate_detection", True),
            ("sorting_mode", "rules_first")))
        rules = json.dumps([rule.to_dict() for rule in self.organizer.rule_manager.rules], sort_keys=True)
        return (os.path.realpath(os.path.expanduser(self.txt_target_dir.text().strip())),
                self.chk_recursive.isChecked(), self.chk_gen_report.isChecked(), settings, rules)

    def _invalidate_dir_review(self):
        had_review = self._reviewed_plan is not None
        self._reviewed_plan = None
        self._review_key = None
        self._review_items = []
        if hasattr(self, "btn_organize"):
            self.btn_organize.setText("Review moves")
            self.cmb_review_file.clear()
            self.cmb_review_file.setEnabled(False)
            self.btn_inspect_evidence.setEnabled(False)
            if had_review:
                self.lbl_organize_details.setText("Review is out of date. Preview again before organizing.")

    def on_inspect_evidence(self):
        index = self.cmb_review_file.currentIndex()
        if 0 <= index < len(self._review_items):
            dialog = EvidenceDialog(self._review_items[index], self)
            try:
                dialog.exec()
            finally:
                dialog.deleteLater()

    def on_preview_dir(self):
        if self.active_dir_worker is not None:
            return
        target_dir = self._validate_organizer_input()
        if not target_dir:
            return
        self.txt_target_dir.setText(target_dir)
        self._invalidate_dir_review()
        self.dir_organizer.rule_manager.rules = copy.deepcopy(self.organizer.rule_manager.rules)
            
        self._set_organizer_running_ui(True)
        self.lbl_organize_status.setText("Status: Scanning and planning preview...")
        self.lbl_organize_details.setText(f"Scanning {target_dir}")
        self.progress_organize.setRange(0, 0)
        
        worker = DirectoryOrganizerWorker(
            organizer=self.dir_organizer,
            root_dir=target_dir,
            mode="preview",
            recursive=self.chk_recursive.isChecked(),
            review_key=self._directory_review_key()
        )
        self.active_dir_worker = worker
        worker.signals.preview_ready.connect(self.on_dir_worker_preview_ready)
        worker.signals.finished.connect(self.on_dir_worker_finished)
        worker.signals.error.connect(self.on_dir_worker_error)
        self.threadpool.start(worker)

    def on_organize_dir(self):
        if self.active_dir_worker is not None:
            return
        target_dir = self._validate_organizer_input()
        if not target_dir:
            return
        self.txt_target_dir.setText(target_dir)
        if self._reviewed_plan is None or self._review_key != self._directory_review_key():
            self.on_preview_dir()
            return
        if not self._reviewed_plan.items:
            QMessageBox.information(self, "Directory Organizer", "There are no reviewed moves to organize.")
            return
        plan = self._reviewed_plan
        key = self._review_key
        low = sum(item.confidence in ("UNCERTAIN", "UNKNOWN", "NOT_AVAILABLE") for item in plan.items)
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Organize reviewed moves")
        confirm.setTextFormat(Qt.TextFormat.PlainText)
        confirm.setText(f"Move exactly {len(plan.items)} reviewed file(s)?\n\nFolder: {plan.root_dir}\n"
                        f"Low-confidence moves: {low}\nPlanning warnings: {len(plan.warnings)}\n"
                        f"Sorting mode: {'Content intelligence' if key[3][4] == 'intelligence' else 'Rules first'}\n\n"
                        f"Existing files: {key[3][2]}\nDuplicate source removal: {'on (SHA-256 verified)' if key[3][3] else 'off'}\n\n"
                        "Only the moves listed in this review will run.")
        confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm.setDefaultButton(QMessageBox.StandardButton.No)
        try:
            answer = confirm.exec()
        finally:
            confirm.deleteLater()
        if answer != QMessageBox.StandardButton.Yes:
            return
        if key != self._directory_review_key():
            self._invalidate_dir_review()
            return
        self._executing_review = copy.deepcopy(plan)
        self._invalidate_dir_review()
            
        self._set_organizer_running_ui(True)
        self.lbl_organize_status.setText("Status: Organizing reviewed moves…")
        self.lbl_organize_details.setText(f"Executing {len(plan.items)} reviewed move(s)")
        self.progress_organize.setRange(0, 0)
        
        worker = DirectoryOrganizerWorker(
            organizer=self.dir_organizer,
            root_dir=target_dir,
            mode="organize",
            recursive=self.chk_recursive.isChecked(),
            generate_report=self.chk_gen_report.isChecked(),
            plan=plan,
            execution_options={"conflict_resolution": key[3][2], "enable_duplicate_detection": key[3][3]}
        )
        self.active_dir_worker = worker
        worker.signals.progress.connect(self.on_dir_worker_progress)
        worker.signals.finished.connect(self.on_dir_worker_finished)
        worker.signals.error.connect(self.on_dir_worker_error)
        self.threadpool.start(worker)

    def on_cancel_organize(self):
        if self.active_dir_worker:
            self.active_dir_worker.cancel()
            self.lbl_organize_status.setText("Status: Cancelling operation...")
            self.btn_cancel_organize.setEnabled(False)

    def _set_organizer_running_ui(self, running: bool):
        self.btn_preview.setEnabled(not running)
        self.btn_organize.setEnabled(not running)
        self.btn_browse_dir.setEnabled(not running)
        self.btn_cancel_organize.setEnabled(running)
        self.txt_target_dir.setEnabled(not running)
        self.chk_recursive.setEnabled(not running)
        self.chk_gen_report.setEnabled(not running)
        self.cmb_review_file.setEnabled(not running and bool(self._review_items))
        self.btn_inspect_evidence.setEnabled(not running and bool(self._review_items))

    def on_dir_worker_progress(self, processed: int, total: int, current_file: str):
        if total > 0:
            self.progress_organize.setRange(0, total)
            self.progress_organize.setValue(processed)
            pct = int((processed / total) * 100)
            self.lbl_organize_status.setText(f"Status: Organizing... ({processed}/{total} - {pct}%)")
        else:
            self.progress_organize.setRange(0, 100)
            self.progress_organize.setValue(0)
            self.lbl_organize_status.setText("Status: Organizing...")
        self.lbl_organize_details.setText(f"Processing: {current_file}")

    def on_dir_worker_preview_ready(self, summary: DirectoryPreviewSummary):
        worker = self.active_dir_worker
        if worker is not None and worker.cancel_event.is_set():
            self.on_dir_worker_finished(OrganizeResult(records=[], cancelled=True), "")
            return
        self._invalidate_dir_review()
        valid = (worker is not None and worker.review_plan is not None and
                 worker.review_key == self._directory_review_key() and
                 summary.items == worker.review_plan.items and
                 summary.total_files == worker.review_plan.total_files and
                 summary.category_counts == worker.review_plan.category_counts and
                 summary.cluster_count == worker.review_plan.cluster_count and
                 summary.warnings == worker.review_plan.warnings)
        if valid:
            self._reviewed_plan = copy.deepcopy(worker.review_plan)
            self._review_key = worker.review_key
        self._review_items = copy.deepcopy(summary.items)
        self.cmb_review_file.addItems([f"{index + 1}. {os.path.basename(item.source_path)}"
                                      for index, item in enumerate(self._review_items)])
        self.btn_organize.setText("Organize reviewed moves" if valid and summary.items else "Review moves")
        self._set_organizer_running_ui(False)
        self.active_dir_worker = None
        self.progress_organize.setRange(0, 100)
        self.progress_organize.setValue(100)
        self.lbl_organize_status.setText("Status: Preview Complete (No files modified)")
        self.lbl_organize_details.setText(
            f"{summary.total_files} planned move(s) · {summary.cluster_count} cluster(s) · {len(summary.warnings)} warning(s)"
            if valid else "Preview displayed. Settings changed or no executable snapshot is available; preview again to organize.")
        root = worker.review_plan.root_dir if worker is not None and worker.review_plan is not None else self.txt_target_dir.text().strip()
        self.lbl_results_title.setText("Review proposed moves — no files modified")
        self.txt_organize_summary.setPlainText(format_directory_review(summary, root))
        self.btn_open_target_folder.setEnabled(True)
        self.btn_open_arrangement_md.setEnabled(False)

    def on_dir_worker_finished(self, result: OrganizeResult, report_path: str):
        reviewed = self._executing_review
        self._executing_review = None
        self._invalidate_dir_review()
        self._set_organizer_running_ui(False)
        self.active_dir_worker = None
        self.progress_organize.setRange(0, 100)
        self.progress_organize.setValue(100)
        
        status_text = "Status: Organization Complete"
        if result.cancelled:
            status_text = "Status: Operation Cancelled by User"
        elif result.error_count > 0:
            status_text = f"Status: Completed with {result.error_count} Error(s)"
        elif reviewed and reviewed.warnings:
            status_text = f"Status: Completed with {len(reviewed.warnings)} planning warning(s)"
            
        self.lbl_organize_status.setText(status_text)
        self.lbl_organize_details.setText(
            f"Moved: {result.success_count} | Renamed/Collisions: {result.collision_count} | "
            f"Duplicate sources removed: {result.duplicate_count} | Skipped: {result.skip_count} | Errors: {result.error_count}"
        )
        
        lines = [
            "=== ORGANIZATION EXECUTION SUMMARY ===",
            f"Status: {'CANCELLED' if result.cancelled else 'COMPLETED'}",
            f"Verified & Moved: {result.success_count}",
            f"Collisions Resolved (Renamed): {result.collision_count}",
            f"Duplicate sources removed: {result.duplicate_count}",
            f"Skipped: {result.skip_count}",
            f"Errors: {result.error_count}",
            ""
        ]
        if report_path and os.path.exists(report_path):
            lines.append(f"Arrangement Index: {report_path}")
            lines.append("")
            self.last_report_path = report_path
            self.btn_open_arrangement_md.setEnabled(True)
        else:
            self.last_report_path = ""
            self.btn_open_arrangement_md.setEnabled(False)
            
        for warning in result.warnings:
            if not reviewed or warning not in reviewed.warnings:
                lines.append(review_text(warning))
        if reviewed and reviewed.warnings:
            lines.append("Planning warnings:")
            lines.extend(f"  • {review_text(warning)}" for warning in reviewed.warnings)
        if result.records:
            by_source = {item.source_path: item for item in reviewed.items} if reviewed else {}
            lines.append("Operation Log:")
            for r in result.records:
                err_suffix = f" [ERROR: {r.error}]" if r.error else ""
                item = by_source.get(r.source)
                estimate = f" {confidence_tag(item)}" if item else ""
                lines.append(f"  [{r.status.value}] {review_text(os.path.basename(r.source))} -> {review_text(r.target)}{estimate}{review_text(err_suffix)}")
                
        self.txt_organize_summary.setPlainText("\n".join(lines))
        self.lbl_results_title.setText("Execution results")
        self.btn_open_target_folder.setEnabled(True)

        if result.undo:
            title = status_text[len("Status: "):]
            if result.undo.entries:
                self._offer_folder_undo(result.undo, title)
            else:
                result.undo.close()
                QMessageBox.information(self, title, "No completed moves to reverse.")

    def _offer_folder_undo(self, journal, title):
        button = QPushButton()
        button.setObjectName("primary")
        button.setToolTip(journal.root)
        self.undo_layout.addWidget(button)
        popup = QMessageBox(self)
        popup.setWindowTitle(title)
        popup.setTextFormat(Qt.TextFormat.PlainText)
        popup.setText(f"{title} · {journal.root}")
        popup.setInformativeText("You have 10 minutes to return files to their original locations. "
                                 "You can also reverse this batch from Organize folder.")
        action = popup.addButton("Reverse moves", QMessageBox.ButtonRole.ActionRole)
        action.setObjectName("primary")
        done = popup.addButton("Done", QMessageBox.ButtonRole.AcceptRole)
        popup.setDefaultButton(done)
        offer = (journal, button, popup, action)
        self.undo_offers.append(offer)
        button.clicked.connect(lambda: self._reverse_folder(offer))
        action.clicked.connect(lambda: self._reverse_folder(offer))
        self.undo_timer.start()
        self._refresh_undo_offers()
        if offer in self.undo_offers:
            popup.open()

    def _remove_undo_offer(self, offer):
        self.undo_offers.remove(offer)
        journal, button, popup, action = offer
        button.hide()
        button.deleteLater()
        popup.close()
        popup.deleteLater()
        if not self.undo_offers:
            self.undo_timer.stop()

    def _refresh_undo_offers(self):
        for offer in list(self.undo_offers):
            journal, button, popup, action = offer
            remaining = math.ceil(journal.deadline - time.monotonic())
            if remaining <= 0:
                self._remove_undo_offer(offer)
                journal.close()
                continue
            button.setText(f"Reverse moves · {os.path.basename(journal.root)} · {remaining//60}:{remaining%60:02}")
            button.setEnabled(self.active_dir_worker is None)
            action.setEnabled(self.active_dir_worker is None)

    def _reverse_folder(self, offer):
        if offer not in self.undo_offers or self.active_dir_worker is not None:
            return
        journal = offer[0]
        if time.monotonic() >= journal.deadline:
            self._refresh_undo_offers()
            return
        self._remove_undo_offer(offer)
        self._invalidate_dir_review()
        worker = DirectoryOrganizerWorker(self.dir_organizer, journal.root, mode="reverse")
        worker.undo = journal
        self.active_dir_worker = worker
        self._set_organizer_running_ui(True)
        self.btn_cancel_organize.setEnabled(False)
        self.lbl_organize_status.setText("Restoring original files…")
        self.lbl_organize_details.setText(journal.root)
        self.progress_organize.setRange(0, 0)
        worker.signals.reversed.connect(self._folder_reversed)
        worker.signals.error.connect(self.on_dir_worker_error)
        self.threadpool.start(worker)

    def _folder_reversed(self, restored, errors):
        self.active_dir_worker = None
        self._set_organizer_running_ui(False)
        self.progress_organize.setRange(0, 100)
        self.progress_organize.setValue(100)
        self.lbl_organize_status.setText("Reversal complete")
        self.lbl_organize_details.setText(f"Restored {restored} · Could not fully restore {len(errors)}")
        self.lbl_results_title.setText("Reversal results")
        self.txt_organize_summary.setPlainText("\n".join(map(review_text, errors)) or "All files returned to their original locations.")

    def on_dir_worker_error(self, error_msg: str):
        self._executing_review = None
        self._invalidate_dir_review()
        self._set_organizer_running_ui(False)
        self.active_dir_worker = None
        self.progress_organize.setRange(0, 100)
        self.progress_organize.setValue(0)
        self.lbl_organize_status.setText("Status: Error encountered")
        self.lbl_organize_details.setText(f"Error: {error_msg}")
        self.txt_organize_summary.setPlainText(f"Error during directory organization:\n{error_msg}")
        QMessageBox.critical(self, "Directory Organizer Error", f"An error occurred:\n{error_msg}")

    def on_open_target_folder(self):
        target_dir = self.txt_target_dir.text().strip()
        if target_dir and os.path.exists(target_dir):
            from src.core.notifications import open_file_in_manager
            open_file_in_manager(target_dir)

    def on_open_arrangement_report(self):
        if self.last_report_path and os.path.exists(self.last_report_path):
            from src.core.notifications import open_file_in_manager
            open_file_in_manager(self.last_report_path)

    def setup_logs(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        
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
        self.table_rules.setHorizontalHeaderLabels(["Name", "Priority", "Status", "Destination"])
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
        sep1.setObjectName("separator")
        btn_layout.addWidget(sep1)
        
        btn_layout.addWidget(self.btn_move_up)
        btn_layout.addWidget(self.btn_move_down)
        
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        sep2.setObjectName("separator")
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
        container.setObjectName("scrollContent")
        scroll.setWidget(container)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(26, 16, 26, 24)
        layout.setSpacing(12)
        
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

        group_intelligence = QGroupBox("File intelligence")
        intelligence_layout = QVBoxLayout(group_intelligence)
        intelligence_layout.addWidget(QLabel("Sorting mode:"))
        self.cmb_sorting_mode = QComboBox()
        self.cmb_sorting_mode.setAccessibleName("Sorting mode")
        self.cmb_sorting_mode.addItem("Rules first — existing behavior", "rules_first")
        self.cmb_sorting_mode.addItem("Content intelligence — analyze all files", "intelligence")
        self.cmb_sorting_mode.setCurrentIndex(max(0, self.cmb_sorting_mode.findData(
            self.config.get("sorting_mode", "rules_first"))))
        intelligence_layout.addWidget(self.cmb_sorting_mode)
        self.chk_downloads_recursive = QCheckBox("Include Downloads subfolders in Content intelligence")
        self.chk_downloads_recursive.setChecked(self.config.get("downloads_recursive", True))
        self.chk_downloads_recursive.setToolTip("Watch new files in nested folders. Use Organize folder to preview existing files.")
        intelligence_layout.addWidget(self.chk_downloads_recursive)
        self.chk_desktop_folders = QCheckBox("Use Linux default folders when sorting downloads to Home")
        self.chk_desktop_folders.setChecked(self.config.get("use_desktop_folders", True))
        self.chk_desktop_folders.setToolTip("Use your existing Pictures, Videos, Music and Documents locations. Explicit custom destination bases are respected.")
        intelligence_layout.addWidget(self.chk_desktop_folders)
        from src.utils.desktop_folders import desktop_folders
        locations = desktop_folders()
        self.lbl_desktop_folders = QLabel("\n".join(f"{title}: {locations[key]}" for title, key in (
            ("Pictures", "PICTURES"), ("Videos", "VIDEOS"), ("Music", "MUSIC"), ("Documents", "DOCUMENTS"))))
        self.lbl_desktop_folders.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_desktop_folders.setWordWrap(True)
        self.lbl_desktop_folders.setProperty("role", "muted")
        intelligence_layout.addWidget(self.lbl_desktop_folders)
        self.cmb_sorting_mode.currentIndexChanged.connect(lambda: self.chk_downloads_recursive.setEnabled(
            self.cmb_sorting_mode.currentData() == "intelligence"))
        self.chk_downloads_recursive.setEnabled(self.cmb_sorting_mode.currentData() == "intelligence")

        self.lbl_sorting_mode_help = QLabel()
        self.lbl_sorting_mode_help.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_sorting_mode_help.setWordWrap(True)
        self.lbl_sorting_mode_help.setProperty("role", "muted")
        def show_sorting_mode_help():
            self.lbl_sorting_mode_help.setText(self._sorting_mode_description(
                self.cmb_sorting_mode.currentData()) + " Save settings to apply to new downloads and folder previews.")
        self.cmb_sorting_mode.currentIndexChanged.connect(show_sorting_mode_help)
        show_sorting_mode_help()
        intelligence_layout.addWidget(self.lbl_sorting_mode_help)
        self.chk_origin_detection = QCheckBox("Enable Browser Origin Detection")
        self.chk_origin_detection.setChecked(self.config.get("enable_origin_detection", True))
        self.chk_origin_detection.setToolTip("Use local browser history and file origin attributes. No network requests.")
        self.chk_deep_content = QCheckBox("Enable Deep Document Content Extraction")
        self.chk_deep_content.setChecked(self.config.get("enable_deep_content_extraction", True))
        self.chk_deep_content.setToolTip("Read bounded document text and metadata. Off uses filenames and optional origin evidence.")
        intelligence_layout.addWidget(self.chk_origin_detection)
        intelligence_layout.addWidget(self.chk_deep_content)
        intelligence_note = QLabel("Preview a folder to inspect destinations and evidence. In Rules, mark a manual rule to apply it in Content intelligence. Restart a separate background service after changing settings.")
        intelligence_note.setWordWrap(True)
        intelligence_note.setProperty("role", "muted")
        intelligence_layout.addWidget(intelligence_note)
        layout.addWidget(group_intelligence)
        
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
        # DEBIAN / SOURCE: show full systemd service controls
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

        # Hide AppImage-specific update button (not used in Debian/SOURCE)
        self.btn_update_service.setVisible(False)

        layout.addWidget(group_service)

        
        # 5. Advanced Group
        group_adv = QGroupBox("Advanced Settings")
        adv_layout = QFormLayout(group_adv)
        
        self.chk_dup = QCheckBox("Remove matching source duplicates (SHA-256 verified)")
        self.chk_dup.setChecked(bool(self.config.get("enable_duplicate_detection", True)))
        adv_layout.addRow(self.chk_dup)
        
        self.cmb_conflict = QComboBox()
        self.cmb_conflict.addItems(["rename", "overwrite", "skip"])
        conflict_val = self.config.get("conflict_resolution", "rename")
        if conflict_val not in ["rename", "overwrite", "skip"]:
            conflict_val = "rename"
        self.cmb_conflict.setCurrentText(str(conflict_val))
        adv_layout.addRow("Collision Policy:", self.cmb_conflict)
        
        self.chk_smart_cleanup = QCheckBox("Enable Smart Filename Cleanup (rename generic/meaningless filenames)")
        self.chk_smart_cleanup.setChecked(bool(self.config.get("smart_filename_cleanup", False)))
        adv_layout.addRow(self.chk_smart_cleanup)
        
        layout.addWidget(group_adv)
        
        # Save Button
        btn_save = QPushButton("Save preferences")
        self.btn_save_settings = btn_save
        btn_save.setObjectName("primary")
        btn_save.clicked.connect(self.save_settings)
        layout.addWidget(btn_save)
        
        # Wrap container in scroll area
        main_settings_layout = QVBoxLayout()
        main_settings_layout.setContentsMargins(0, 0, 0, 0)
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
            
        old_sorting_mode = self.config.get("sorting_mode", "rules_first")
        old_watch_recursive = old_sorting_mode == "intelligence" and self.config.get("downloads_recursive", True)
        old_downloads = self.config.get("downloads_folder")
        new_downloads = os.path.abspath(os.path.expanduser(self.txt_downloads.text()))
        folder_changed = os.path.normpath(old_downloads) != new_downloads
        if folder_changed and not os.path.isdir(new_downloads):
            QMessageBox.critical(self, "Error", "Please choose an existing Downloads folder.")
            return

        try:
            prev_autostart = self.config.get("autostart", False)
            new_autostart = self.chk_autostart.isChecked()
            settings = dict(self.config.config)
            settings.update({
                "downloads_folder": new_downloads,
                "large_file_threshold_gb": bytes_val,
                "enable_notifications": self.chk_notif.isChecked(),
                "enable_duplicate_detection": self.chk_dup.isChecked(),
                "conflict_resolution": self.cmb_conflict.currentText(),
                "start_minimized": self.chk_start_minimized.isChecked(),
                "smart_filename_cleanup": self.chk_smart_cleanup.isChecked(),
                "autostart": new_autostart,
                "theme": ("system", "dark", "light")[self.cmb_theme.currentIndex()],
                "enable_origin_detection": self.chk_origin_detection.isChecked(),
                "enable_deep_content_extraction": self.chk_deep_content.isChecked(),
                "sorting_mode": self.cmb_sorting_mode.currentData(),
                "downloads_recursive": self.chk_downloads_recursive.isChecked(),
                "use_desktop_folders": self.chk_desktop_folders.isChecked(),
            })
            # One validated write avoids repeatedly rewriting the configuration.
            self.config.save_config(settings)
            self._invalidate_dir_review()
            blocked = self.chk_recursive.blockSignals(True)
            self.chk_recursive.setChecked(self._folder_recursion_enabled())
            self.chk_recursive.blockSignals(blocked)
            self._refresh_sorting_mode_summary()
            self.organizer.filename_cleanup.enabled = self.chk_smart_cleanup.isChecked()
            if prev_autostart != new_autostart:
                self.update_autostart_setting(new_autostart)
            self.apply_theme()

            new_watch_recursive = self.config.get("sorting_mode", "rules_first") == "intelligence" and self.config.get("downloads_recursive", True)
            if (folder_changed or old_watch_recursive != new_watch_recursive) and (hasattr(self, "monitor_thread") or
                                   "PYTEST_CURRENT_TEST" not in os.environ):
                if hasattr(self, "monitor_thread"):
                    self.monitor_thread.stop()
                    if not self.monitor_thread.wait(2000):
                        QMessageBox.warning(self, "Settings saved",
                                            "The previous monitor is still stopping. Restart SmartSort to apply the monitoring changes.")
                        return
                self.start_monitor()
            message = "All settings saved successfully!"
            if old_sorting_mode != self.config.get("sorting_mode", "rules_first"):
                message += ("\n\nThe new sorting mode applies to new downloads and folder previews. "
                            "If the separate Background Monitoring service is running, use its Restart button to reload settings.")
            QMessageBox.information(self, "Success", message)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")

    def refresh_rules_table(self):
        self._refresh_sorting_mode_summary()
        self._invalidate_dir_review()
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
            
            enabled_indicator = "Enabled" if r.enabled else "Disabled"
            enabled_item = QTableWidgetItem(enabled_indicator)
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            dest_item = QTableWidgetItem(r.destination)
            
            self.table_rules.setItem(row, 0, name_item)
            self.table_rules.setItem(row, 1, priority_item)
            self.table_rules.setItem(row, 2, enabled_item)
            self.table_rules.setItem(row, 3, dest_item)
            
        self.table_rules.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_rules.setColumnWidth(1, 76)
        self.table_rules.setColumnWidth(2, 92)
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
        self._tester_worker = None
        self._tester_request_id = 0
        self._tester_result_key = None
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self._sorting_mode_card())
        note = QLabel("Test a filename, or choose an existing file to analyze its content. Nothing is moved or removed.")
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        layout.addWidget(note)
        form_widget = QWidget()
        form_widget.setProperty("class", "Card")
        form = QFormLayout(form_widget)
        form.setSpacing(10)
        self.cmb_test_source = QComboBox()
        self.cmb_test_source.addItem("Filename and size", "filename")
        self.cmb_test_source.addItem("Existing file — content analysis", "file")
        self.cmb_test_source.setAccessibleName("Test input")
        form.addRow("Test input:", self.cmb_test_source)
        file_row = QHBoxLayout()
        self.txt_test_path = QLineEdit()
        self.txt_test_path.setPlaceholderText("Choose a file to preview its actual sorting destination")
        self.btn_browse_test_file = QPushButton("Browse…")
        self.btn_browse_test_file.clicked.connect(self.browse_test_file)
        file_row.addWidget(self.txt_test_path, 1)
        file_row.addWidget(self.btn_browse_test_file)
        form.addRow("Existing file:", file_row)
        self.txt_test_filename = QLineEdit("wallpaper.jpg")
        self.txt_test_size = QLineEdit("1.2MB")
        self.txt_test_size.setPlaceholderText("e.g. 1.2MB, 500KB, 2.5GB")
        self.txt_test_ext = QLineEdit(".jpg")
        self.txt_test_ext.setPlaceholderText("Used only when the filename has no extension")
        form.addRow("Filename:", self.txt_test_filename)
        form.addRow("File size:", self.txt_test_size)
        form.addRow("Extension:", self.txt_test_ext)
        layout.addWidget(form_widget)
        self.btn_test_sorting = QPushButton("Test sorting")
        self.btn_test_sorting.setObjectName("primary")
        self.btn_test_sorting.clicked.connect(self.run_rule_test)
        layout.addWidget(self.btn_test_sorting)
        group = QGroupBox("Sorting preview")
        g_layout = QFormLayout(group)
        g_layout.setSpacing(10)
        self.lbl_test_match = QLabel("Not tested")
        self.lbl_test_priority = QLabel("N/A")
        self.lbl_test_dest = QLabel("N/A")
        self.lbl_test_confidence = QLabel("N/A")
        self.lbl_test_scope = QLabel("")
        for label in (self.lbl_test_match, self.lbl_test_priority, self.lbl_test_dest,
                      self.lbl_test_confidence, self.lbl_test_scope):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_test_confidence.setToolTip("Classification strength, not a probability. File-type fallback has unknown semantic confidence.")
        g_layout.addRow("Decision:", self.lbl_test_match)
        g_layout.addRow("Rule priority:", self.lbl_test_priority)
        g_layout.addRow("Destination:", self.lbl_test_dest)
        g_layout.addRow("Confidence:", self.lbl_test_confidence)
        g_layout.addRow("Analysis:", self.lbl_test_scope)
        self.txt_test_evidence = QPlainTextEdit()
        self.txt_test_evidence.setReadOnly(True)
        self.txt_test_evidence.setAccessibleName("Sorting evidence")
        self.txt_test_evidence.setMinimumHeight(100)
        self.txt_test_evidence.setMaximumHeight(180)
        g_layout.addRow("Reasons:", self.txt_test_evidence)
        layout.addWidget(group)
        layout.addStretch()
        content = QWidget()
        content.setLayout(layout)
        self.scroll_page(self.tab_tester, content)
        for control in (self.txt_test_filename, self.txt_test_size, self.txt_test_ext, self.txt_test_path):
            control.textChanged.connect(self._invalidate_tester_result)
        self.cmb_test_source.currentIndexChanged.connect(self._test_source_changed)
        self._test_source_changed()

    def _test_source_changed(self):
        real_file = self.cmb_test_source.currentData() == "file"
        self.txt_test_path.setEnabled(real_file)
        self.btn_browse_test_file.setEnabled(real_file)
        for control in (self.txt_test_filename, self.txt_test_size, self.txt_test_ext):
            control.setEnabled(not real_file)
        self._invalidate_tester_result()

    def browse_test_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose file to test")
        if path:
            self.txt_test_path.setText(path)

    def _tester_key(self):
        from src.utils.desktop_folders import DesktopDestinations
        routes = DesktopDestinations(os.path.expanduser(self.config.get("destination_base", "~")), self.config)
        return (self.cmb_test_source.currentData(), self.txt_test_path.text().strip(),
                self.txt_test_filename.text().strip(), self.txt_test_size.text().strip(),
                self.txt_test_ext.text().strip(),
                json.dumps({name: self.config.get(name) for name in (
                    "sorting_mode", "destination_base", "downloads_folder", "smart_filename_cleanup",
                    "filename_min_length", "filename_max_length", "enable_origin_detection",
                    "enable_deep_content_extraction", "use_desktop_folders")}, sort_keys=True),
                json.dumps([rule.to_dict() for rule in self.organizer.rule_manager.rules], sort_keys=True),
                routes.signature)

    def _invalidate_tester_result(self):
        if not hasattr(self, "lbl_test_match"):
            return
        self._tester_request_id += 1
        self._tester_result_key = None
        self.lbl_test_match.setText("Test again to preview the current inputs")
        self.lbl_test_priority.setText("N/A")
        self.lbl_test_dest.setText("N/A")
        self.lbl_test_confidence.setText("N/A")
        self.lbl_test_scope.setText("")
        self.txt_test_evidence.clear()

    def _show_sorting_test(self, result, key):
        proposal = result.proposal
        self._tester_result_key = key
        self.lbl_test_match.setText(proposal.rule_name if proposal.is_rule_override else
                                    "Content intelligence: " + proposal.domain)
        self.set_label_tone(self.lbl_test_match, "success" if proposal.is_rule_override else "info")
        self.lbl_test_priority.setText(f"P{result.rule_priority}" if result.rule_priority is not None else "N/A")
        self.lbl_test_dest.setText(proposal.target_path)
        if proposal.confidence_level.value == "UNKNOWN" and proposal.domain != "Others":
            self.lbl_test_confidence.setText("File type recognized; content confidence UNKNOWN")
        else:
            self.lbl_test_confidence.setText(f"{proposal.confidence_level.value} ({proposal.confidence_score:.0%})")
        self.lbl_test_scope.setText("Existing file: saved sorting settings; no files moved or removed."
            if result.source_kind == "file" else "Filename/size/type preview only; file content was not inspected.")
        reasons = [item.description for item in proposal.evidence[:64]]
        if len(proposal.evidence) > 64:
            reasons.append(f"{len(proposal.evidence) - 64} additional reasons omitted.")
        self.txt_test_evidence.setPlainText("\n".join(reasons) or "No additional evidence.")

    def run_rule_test(self):
        if self._tester_worker is not None:
            return
        self._invalidate_tester_result()
        key = self._tester_key()
        settings = copy.deepcopy(self.config.config)
        rules = copy.deepcopy(self.organizer.rule_manager.rules)
        if self.cmb_test_source.currentData() == "file":
            path = self.txt_test_path.text().strip()
            if not path:
                QMessageBox.warning(self, "Choose a file", "Select an existing file to analyze.")
                return
            worker = SortingTestWorker(self._tester_request_id, key, settings, rules, os.path.expanduser(path))
            self._tester_worker = worker
            worker.signals.finished.connect(self._sorting_test_finished)
            worker.signals.error.connect(self._sorting_test_error)
            self.btn_test_sorting.setEnabled(False)
            self.btn_test_sorting.setText("Analyzing…")
            self.lbl_test_match.setText("Analyzing existing file…")
            self.threadpool.start(worker)
            return
        filename = self.txt_test_filename.text().strip()
        size = self.txt_test_size.text().strip()
        extension = self.txt_test_ext.text().strip()
        try:
            from src.rules.conditions import parse_size_to_bytes
            from src.core.sorting_tester import preview_sorting
            if not filename:
                raise ValueError("Filename cannot be empty")
            if extension and not os.path.splitext(filename)[1]:
                filename += extension if extension.startswith(".") else "." + extension
            result = preview_sorting(settings, rules, filename=filename,
                                     size_bytes=parse_size_to_bytes(size) if size else 0)
            self._show_sorting_test(result, key)
        except Exception as error:
            QMessageBox.critical(self, "Test failed", str(error))

    def _finish_test_worker(self, request_id):
        worker = self._tester_worker
        if worker is None or worker.request_id != request_id:
            return False
        self._tester_worker = None
        self.btn_test_sorting.setEnabled(True)
        self.btn_test_sorting.setText("Test sorting")
        return True

    def _sorting_test_finished(self, event):
        request_id, key, result = event
        if not self._finish_test_worker(request_id):
            return
        if request_id == self._tester_request_id and key == self._tester_key():
            self._show_sorting_test(result, key)
        else:
            self._invalidate_tester_result()

    def _sorting_test_error(self, event):
        request_id, key, error = event
        if not self._finish_test_worker(request_id):
            return
        if request_id == self._tester_request_id and key == self._tester_key():
            self.lbl_test_match.setText("Unable to analyze this file")
            self.txt_test_evidence.setPlainText(error)
        else:
            self._invalidate_tester_result()

    def refresh_logs(self):
        self.table_logs.setRowCount(0)
        log_dir = self.logger.log_dir
        if not os.path.exists(log_dir):
            return
            
        # Get the latest log file
        log_files = sorted([f for f in os.listdir(log_dir) if f.startswith("smartsort_") and f.endswith(".log")], reverse=True)
        if not log_files:
            return
            
        log_path = os.path.join(log_dir, log_files[0])
        
        try:
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            
            self.table_logs.setRowCount(0)
            for line in lines:
                if " - INFO - File: " in line:
                    parts = line.split(" - INFO - ", 1)
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
        self.log_display.appendPlainText(f"Detected: {os.path.basename(file_path)}")
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
            self.log_display.appendPlainText(f"Moved {filename} to: {info}")
            if self.config.get("enable_notifications"):
                self.show_notification("File Organized", f"{filename} moved to {info}")
            self.refresh_logs()
            if self.tray_available:
                self.tray_manager.set_success(self.stats.get("processed", 0), active_rules)
        elif result == "DUPLICATE":
            self.update_stats("duplicates")
            self.log_display.appendPlainText(f"Removed duplicate source {filename}; SHA-256 matched existing file: {info}")
            if self.tray_available:
                self.tray_manager.set_success(self.stats.get("processed", 0), active_rules)
        elif result == "SKIPPED":
            self.log_display.appendPlainText(f"Skipped: {filename} ({info})")
            if self.tray_available:
                self.tray_manager.set_success(self.stats.get("processed", 0), active_rules)
        elif result == "ERROR":
            self.update_stats("errors")
            self.log_display.appendPlainText(f"Error processing {filename}: {info}")
            if self.config.get("enable_notifications"):
                self.show_notification("SmartSort Error", f"Failed to organize {filename}: {info}")
            if hasattr(self, 'monitor_thread'):
                self.monitor_thread.get_handler().mark_as_unprocessed(file_path)
            if self.tray_available:
                self.tray_manager.set_error(info)

    def on_worker_error(self, file_path, error_msg):
        self.log_display.appendPlainText(f"Critical error processing {os.path.basename(file_path)}: {error_msg}")
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
        except Exception:
            try:
                if hasattr(self, "tray_manager") and self.tray_manager and self.tray_manager.tray_icon:
                    self.tray_manager.tray_icon.showMessage(title, message)
            except Exception:
                pass

class RuleDialog(QDialog):
    def __init__(self, parent=None, rule=None, existing_priorities=None):
        super().__init__(parent)
        self.resize(660, 550)
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
        self.chk_intelligence_rule = QCheckBox("Use this rule in Content intelligence")
        self.chk_intelligence_rule.setChecked(True)
        self.chk_intelligence_rule.setToolTip("Your explicit choice takes priority over automatic content hints. Project folders remain protected.")

        self.txt_dest = QLineEdit()
        self.txt_dest.textChanged.connect(self.update_preview)
        
        self.lbl_preview = QLabel("Preview: (Enter a destination template)")
        self.lbl_preview.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_preview.setWordWrap(True)
        
        form.addRow("Rule Name:", self.txt_name)
        form.addRow("Priority:", self.spin_priority)
        form.addRow("Enabled:", self.chk_enabled)
        form.addRow("Manual override:", self.chk_intelligence_rule)
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
        self.chk_intelligence_rule.setChecked(self.rule.apply_in_intelligence)
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
            "apply_in_intelligence": self.chk_intelligence_rule.isChecked(),
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
