"""
Notification Manager for SmartSort.

Redesigned Native DBus Desktop Notification Engine supporting reliable
click actions and file manager selection/highlighting on GNOME and other
Linux desktop environments (org.freedesktop.Notifications & org.freedesktop.FileManager1).

Fallback Hierarchy for File Opening:
1. org.freedesktop.FileManager1 ShowItems() (Highlights file in Nautilus / Dolphin / Thunar / Nemo)
2. xdg-open on parent directory
3. gio open on parent directory
"""

import os
import sys
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger("SmartSort")

# Global DBus signal handler registry mapping notif_id -> target_file_path
_NOTIFICATION_TARGETS: Dict[int, str] = {}
_DBUS_LISTENER_REGISTERED = False


def open_file_in_manager(file_path: str) -> bool:
    """
    Opens the default desktop file manager and highlights/selects the processed file.
    
    Fallback Priority:
    1. org.freedesktop.FileManager1 DBus ShowItems() (Highlights file in Nautilus/GNOME)
    2. xdg-open on parent directory
    3. gio open on parent directory
    
    Returns True if any file manager command succeeded, False otherwise.
    Never raises an exception or interrupts execution.
    """
    if not file_path or not isinstance(file_path, str):
        logger.error("open_file_in_manager called with empty or invalid file path.")
        return False

    try:
        abs_path = os.path.abspath(file_path)
        parent_dir = os.path.dirname(abs_path)

        # If the file does not exist, fall back to opening parent directory if present
        if not os.path.exists(abs_path):
            logger.warning(f"File '{abs_path}' no longer exists; falling back to parent directory.")
            return _open_directory_fallback(parent_dir)

        file_uri = Path(abs_path).as_uri()  # e.g. file:///home/user/Documents/PDF/report.pdf

        # Priority 1: org.freedesktop.FileManager1 DBus ShowItems via dbus-python
        try:
            import dbus
            bus = dbus.SessionBus()
            fm_obj = bus.get_object('org.freedesktop.FileManager1', '/org/freedesktop/FileManager1')
            fm_iface = dbus.Interface(fm_obj, 'org.freedesktop.FileManager1')
            fm_iface.ShowItems([file_uri], '')
            logger.info(f"Successfully highlighted '{abs_path}' via FileManager1 DBus ShowItems.")
            return True
        except Exception as dbus_err:
            logger.debug(f"Native dbus-python ShowItems failed ({dbus_err}); trying dbus-send command...")

        # Priority 1 Sub-fallback: dbus-send CLI
        try:
            res = subprocess.run(
                [
                    "dbus-send",
                    "--session",
                    "--print-reply",
                    "--dest=org.freedesktop.FileManager1",
                    "/org/freedesktop/FileManager1",
                    "org.freedesktop.FileManager1.ShowItems",
                    f"array:string:{file_uri}",
                    "string:"
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3
            )
            if res.returncode == 0:
                logger.info(f"Successfully highlighted '{abs_path}' via dbus-send ShowItems.")
                return True
        except Exception as dbus_send_err:
            logger.debug(f"dbus-send ShowItems failed ({dbus_send_err}); trying gdbus...")

        # Priority 1 Sub-fallback: gdbus CLI
        try:
            res = subprocess.run(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest", "org.freedesktop.FileManager1",
                    "--object-path", "/org/freedesktop/FileManager1",
                    "--method", "org.freedesktop.FileManager1.ShowItems",
                    f"['{file_uri}']",
                    '""'
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3
            )
            if res.returncode == 0:
                logger.info(f"Successfully highlighted '{abs_path}' via gdbus ShowItems.")
                return True
        except Exception as gdbus_err:
            logger.debug(f"gdbus ShowItems failed ({gdbus_err}).")

        # Priority 2: xdg-open parent directory fallback
        logger.info(f"ShowItems unavailable or failed; falling back to opening parent directory: {parent_dir}")
        return _open_directory_fallback(parent_dir)

    except Exception as e:
        logger.error(f"Failed to open file manager for '{file_path}': {e}")
        return False


def _open_directory_fallback(parent_dir: str) -> bool:
    """Fallback method to open a directory using xdg-open or gio open."""
    if not parent_dir or not os.path.exists(parent_dir):
        logger.error(f"Cannot open non-existent directory: '{parent_dir}'")
        return False

    # Priority 2: xdg-open
    try:
        res = subprocess.run(
            ["xdg-open", parent_dir],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        if res.returncode == 0:
            logger.info(f"Opened parent directory via xdg-open: {parent_dir}")
            return True
        logger.debug(f"xdg-open returned code {res.returncode} for '{parent_dir}'")
    except Exception as e:
        logger.debug(f"xdg-open failed for '{parent_dir}': {e}")

    # Priority 3: gio open
    try:
        res = subprocess.run(
            ["gio", "open", parent_dir],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        if res.returncode == 0:
            logger.info(f"Opened parent directory via gio: {parent_dir}")
            return True
        logger.debug(f"gio open returned code {res.returncode} for '{parent_dir}'")
    except Exception as e:
        logger.debug(f"gio open failed for '{parent_dir}': {e}")

    logger.error(f"All file manager launch mechanisms failed for directory: '{parent_dir}'")
    return False


def _on_action_invoked_signal(notif_id, action_key, *args):
    """
    Global DBus signal handler called when a user clicks a notification body
    or action button in GNOME Shell / Freedesktop notification daemon.
    """
    try:
        nid = int(notif_id)
        logger.debug(f"DBus ActionInvoked signal received: notif_id={nid}, action_key='{action_key}'")
        
        target_path = _NOTIFICATION_TARGETS.get(nid)
        if target_path:
            logger.info(f"Notification clicked for file: {target_path}. Opening file manager...")
            open_file_in_manager(target_path)
        else:
            logger.debug(f"No target file path found for notification ID {nid}")
    except Exception as e:
        logger.error(f"Error handling DBus ActionInvoked signal: {e}")


def _ensure_dbus_signal_listener():
    """Ensures DBus ActionInvoked signal listener is registered."""
    global _DBUS_LISTENER_REGISTERED
    if _DBUS_LISTENER_REGISTERED:
        return True

    try:
        import dbus
        bus = dbus.SessionBus()
        bus.add_signal_receiver(
            _on_action_invoked_signal,
            signal_name='ActionInvoked',
            dbus_interface='org.freedesktop.Notifications',
            path='/org/freedesktop/Notifications'
        )
        _DBUS_LISTENER_REGISTERED = True
        logger.debug("Registered DBus ActionInvoked signal listener for org.freedesktop.Notifications.")
        return True
    except Exception as e:
        logger.debug(f"Could not register DBus ActionInvoked signal listener: {e}")
        return False


class NotificationManager:
    """
    Manages sending desktop notifications for successfully organized files.
    """

    def __init__(self, config_manager=None, logger_instance=None):
        self.config = config_manager
        self.logger = logger_instance or logger

    def is_notifications_enabled(self) -> bool:
        """Returns whether notifications are enabled in configuration."""
        if self.config:
            return bool(self.config.get("enable_notifications", True))
        return True

    def send_success_notification(self, dest_path: str) -> bool:
        """
        Sends a clickable desktop notification after a file is successfully organized.
        
        Notification Content:
        Title: SmartSort
        Body:
        Successfully organized:
        <filename>

        Destination:
        <destination_folder>

        Clicking the notification triggers open_file_in_manager(dest_path).
        
        Failure resilience: Wrap all notification calls; errors are logged and
        never interrupt file sorting operations.
        """
        # CI / Test Safety: Do not display desktop notifications during test suite runs
        if "PYTEST_CURRENT_TEST" in os.environ:
            return False

        if not self.is_notifications_enabled():
            return False

        if not dest_path:
            return False

        try:
            filename = os.path.basename(dest_path)
            parent_dir = os.path.dirname(dest_path)
            
            # Format user-friendly destination path (expand ~ if in user home)
            home_dir = os.path.expanduser("~")
            if parent_dir.startswith(home_dir):
                dest_display = parent_dir.replace(home_dir, "~", 1)
            else:
                dest_display = parent_dir

            title = "SmartSort"
            body = f"Successfully organized:\n{filename}\n\nMoved to:\n{dest_display}"

            return self._deliver_notification(title, body, dest_path)
        except Exception as e:
            self.logger.error(f"Failed to create success notification for '{dest_path}': {e}")
            return False

    def _deliver_notification(self, title: str, body: str, target_file_path: str) -> bool:
        """
        Delivers desktop notification over DBus using explicit org.freedesktop.Notifications types.
        """
        # 1. Native DBus via dbus-python
        try:
            import dbus

            _ensure_dbus_signal_listener()

            bus = dbus.SessionBus()
            notify_obj = bus.get_object('org.freedesktop.Notifications', '/org/freedesktop/Notifications')
            notify_iface = dbus.Interface(notify_obj, 'org.freedesktop.Notifications')

            # Actions format: ["default", "Open", "show", "Show in Folder"]
            actions = ['default', 'Open', 'show', 'Show in Folder']
            hints = {'desktop-entry': 'smartsort'}

            notif_id = notify_iface.Notify(
                'SmartSort',
                dbus.UInt32(0),
                'smartsort',
                title,
                body,
                actions,
                hints,
                dbus.Int32(5000)
            )

            nid = int(notif_id)
            _NOTIFICATION_TARGETS[nid] = target_file_path
            self.logger.debug(f"DBus Notification delivered (ID: {nid}) for '{target_file_path}'")
            return True
        except Exception as dbus_err:
            self.logger.debug(f"Native DBus notification failed ({dbus_err}); trying libnotify fallback...")

        # 2. Secondary Fallback: libnotify via gi.repository.Notify
        try:
            import gi
            gi.require_version('Notify', '0.7')
            from gi.repository import Notify

            Notify.init("SmartSort")
            n = Notify.Notification.new(title, body, "smartsort")

            def on_action(notification, action_key, *args):
                try:
                    open_file_in_manager(target_file_path)
                except Exception as cb_err:
                    self.logger.error(f"Error in libnotify action callback: {cb_err}")

            try:
                n.add_action("default", "Open", on_action, None)
                n.add_action("show", "Show in Folder", on_action, None)
            except Exception as act_err:
                self.logger.debug(f"Could not add action to libnotify notification: {act_err}")

            n.show()
            self.logger.debug(f"libnotify notification delivered for '{target_file_path}'")
            return True
        except Exception as gi_err:
            self.logger.debug(f"libnotify notification failed ({gi_err}); trying gdbus CLI fallback...")

        # 3. Tertiary Fallback: gdbus CLI call
        try:
            res = subprocess.run(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest", "org.freedesktop.Notifications",
                    "--object-path", "/org/freedesktop/Notifications",
                    "--method", "org.freedesktop.Notifications.Notify",
                    "SmartSort",
                    "0",
                    "smartsort",
                    title,
                    body,
                    "['default', 'Open']",
                    "{}",
                    "5000"
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3
            )
            if res.returncode == 0:
                self.logger.debug(f"gdbus CLI notification delivered for '{target_file_path}'")
                return True
        except Exception as gdbus_err:
            self.logger.debug(f"gdbus CLI notification failed ({gdbus_err})")

        self.logger.error(f"All desktop notification backends failed for file '{target_file_path}'")
        return False
