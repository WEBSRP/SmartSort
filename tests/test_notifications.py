"""
Tests for Clickable Notifications and File Manager Highlighting in SmartSort.

Tests cover:
- Redesigned open_file_in_manager priority hierarchy:
  1. org.freedesktop.FileManager1 DBus ShowItems()
  2. xdg-open fallback
  3. gio open fallback
- ActionInvoked DBus signal handling & click execution
- Notification delivery filtering (SUCCESS only; SKIPPED/DUPLICATE/ERROR produce none)
- Disabled notifications config setting
- Exception isolation (notifications/DBus errors never interrupt file sorting)
- Headless CI / pytest safety check
"""

import os
import subprocess
import pytest
from unittest.mock import MagicMock, patch

from src.core.notifications import (
    NotificationManager,
    open_file_in_manager,
    _on_action_invoked_signal,
    _NOTIFICATION_TARGETS,
)
from src.organizer import FileOrganizer
from src.utils.logger import SmartSortLogger


class MockConfig:
    def __init__(self, enable_notifications=True):
        self.data = {
            "destination_base": "/tmp",
            "enable_notifications": enable_notifications,
            "enable_duplicate_detection": True,
            "conflict_resolution": "rename",
            "smart_filename_cleanup": False,
            "rules": []
        }

    def get(self, key, default=None):
        return self.data.get(key, default)


# ---------------------------------------------------------------------------
# 1. Open File Manager Priority & Fallback Hierarchy Tests
# ---------------------------------------------------------------------------

def test_open_file_in_manager_show_items_dbus_success(tmp_path, monkeypatch):
    """Priority 1: Native DBus org.freedesktop.FileManager1.ShowItems succeeds."""
    test_file = tmp_path / "report.pdf"
    test_file.write_text("pdf data")

    show_items_called = []

    class MockFMInterface:
        def ShowItems(self, uris, startup_id):
            show_items_called.append((uris, startup_id))

    class MockBus:
        def get_object(self, service, path):
            return "mock_obj"

    def mock_interface(obj, iface_name):
        return MockFMInterface()

    import sys
    mock_dbus = MagicMock()
    mock_dbus.SessionBus = lambda: MockBus()
    mock_dbus.Interface = mock_interface

    monkeypatch.setitem(sys.modules, "dbus", mock_dbus)

    assert open_file_in_manager(str(test_file)) is True
    assert len(show_items_called) == 1
    assert show_items_called[0][0] == [test_file.as_uri()]


def test_open_file_in_manager_dbus_send_fallback(tmp_path, monkeypatch):
    """Priority 1 Sub-fallback: dbus-python fails, dbus-send CLI succeeds."""
    test_file = tmp_path / "document.docx"
    test_file.write_text("doc data")

    # Fail native dbus-python
    import sys
    monkeypatch.setitem(sys.modules, "dbus", None)

    calls = []

    def mock_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == "dbus-send":
            return subprocess.CompletedProcess(cmd, 0)
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(subprocess, "run", mock_run)

    assert open_file_in_manager(str(test_file)) is True
    assert "dbus-send" in calls


def test_open_file_in_manager_gdbus_fallback(tmp_path, monkeypatch):
    """Priority 1 Sub-fallback: dbus-send fails, gdbus CLI succeeds."""
    test_file = tmp_path / "image.png"
    test_file.write_text("png data")

    import sys
    monkeypatch.setitem(sys.modules, "dbus", None)

    calls = []

    def mock_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == "gdbus":
            return subprocess.CompletedProcess(cmd, 0)
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(subprocess, "run", mock_run)

    assert open_file_in_manager(str(test_file)) is True
    assert "dbus-send" in calls
    assert "gdbus" in calls


def test_open_file_in_manager_xdg_open_fallback(tmp_path, monkeypatch):
    """Priority 2: All ShowItems attempts fail; xdg-open on parent directory succeeds."""
    test_file = tmp_path / "data.zip"
    test_file.write_text("zip data")

    import sys
    monkeypatch.setitem(sys.modules, "dbus", None)

    calls = []

    def mock_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == "xdg-open":
            return subprocess.CompletedProcess(cmd, 0)
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(subprocess, "run", mock_run)

    assert open_file_in_manager(str(test_file)) is True
    assert "xdg-open" in calls


def test_open_file_in_manager_gio_fallback(tmp_path, monkeypatch):
    """Priority 3: ShowItems and xdg-open fail; gio open on parent directory succeeds."""
    test_file = tmp_path / "audio.mp3"
    test_file.write_text("mp3 data")

    import sys
    monkeypatch.setitem(sys.modules, "dbus", None)

    calls = []

    def mock_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == "gio":
            return subprocess.CompletedProcess(cmd, 0)
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(subprocess, "run", mock_run)

    assert open_file_in_manager(str(test_file)) is True
    assert "gio" in calls


def test_open_file_in_manager_all_fail_never_crashes(tmp_path, monkeypatch):
    """When all launchers fail or raise exceptions, open_file_in_manager returns False gracefully."""
    test_file = tmp_path / "file.txt"
    test_file.write_text("data")

    import sys
    monkeypatch.setitem(sys.modules, "dbus", None)

    def mock_run_exception(cmd, **kwargs):
        raise FileNotFoundError(f"{cmd[0]} not found")

    monkeypatch.setattr(subprocess, "run", mock_run_exception)

    assert open_file_in_manager(str(test_file)) is False
    assert open_file_in_manager("") is False
    assert open_file_in_manager(None) is False


# ---------------------------------------------------------------------------
# 2. ActionInvoked Signal & Click Execution Tests
# ---------------------------------------------------------------------------

def test_action_invoked_signal_triggers_open_file(tmp_path, monkeypatch):
    """ActionInvoked DBus signal triggers open_file_in_manager for registered notification IDs."""
    test_file = tmp_path / "report.pdf"
    test_file.write_text("data")

    notif_id = 999
    _NOTIFICATION_TARGETS[notif_id] = str(test_file)

    opened_files = []
    monkeypatch.setattr("src.core.notifications.open_file_in_manager", lambda p: opened_files.append(p))

    # Simulate GNOME Shell emitting ActionInvoked signal
    _on_action_invoked_signal(notif_id, "default")
    assert len(opened_files) == 1
    assert opened_files[0] == str(test_file)

    # Clean up
    _NOTIFICATION_TARGETS.pop(notif_id, None)


# ---------------------------------------------------------------------------
# 3. Notification Filtering & Delivery Tests
# ---------------------------------------------------------------------------

def test_notification_sent_on_success(tmp_path, monkeypatch):
    """Successful file operations deliver notifications."""
    dest_file = tmp_path / "Documents" / "report.pdf"
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    dest_file.write_text("report")

    config = MockConfig(enable_notifications=True)
    notif_mgr = NotificationManager(config, SmartSortLogger(log_dir="test_logs"))

    sent = []
    monkeypatch.setattr(notif_mgr, "_deliver_notification", lambda t, b, p: sent.append((t, b, p)) or True)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    res = notif_mgr.send_success_notification(str(dest_file))
    assert res is True
    assert len(sent) == 1
    title, body, path = sent[0]
    assert title == "SmartSort"
    assert "report.pdf" in body
    assert path == str(dest_file)


def test_notification_disabled_config(tmp_path, monkeypatch):
    """When enable_notifications is False, send_success_notification returns False."""
    dest_file = tmp_path / "photo.jpg"
    dest_file.write_text("data")

    config = MockConfig(enable_notifications=False)
    notif_mgr = NotificationManager(config, SmartSortLogger(log_dir="test_logs"))

    sent = []
    monkeypatch.setattr(notif_mgr, "_deliver_notification", lambda t, b, p: sent.append(p))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    assert notif_mgr.send_success_notification(str(dest_file)) is False
    assert len(sent) == 0


def test_skipped_duplicate_error_produce_no_notifications(tmp_path, monkeypatch):
    """Non-SUCCESS operations (SKIPPED, DUPLICATE, ERROR) produce no notifications."""
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "dest" / "src.txt"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("hello")

    config = MockConfig(enable_notifications=True)
    organizer = FileOrganizer(config, SmartSortLogger(log_dir="test_logs"))
    organizer.get_destination_path = lambda f, c, **kwargs: str(dst)

    notif_calls = []
    monkeypatch.setattr(
        organizer.notification_manager,
        "send_success_notification",
        lambda path: notif_calls.append(path)
    )

    result, info = organizer.process_file(str(src))
    assert result == "DUPLICATE"
    assert len(notif_calls) == 0

    result2, info2 = organizer.process_file(str(tmp_path / "nonexistent.txt"))
    assert result2 == "SKIPPED"
    assert len(notif_calls) == 0


def test_notification_exception_isolation(tmp_path, monkeypatch):
    """Notification manager exceptions do not disrupt file sorting operations."""
    src = tmp_path / "file.txt"
    src.write_text("content")
    dst_dir = tmp_path / "dest"

    config = MockConfig(enable_notifications=True)
    organizer = FileOrganizer(config, SmartSortLogger(log_dir="test_logs"))
    organizer.get_destination_path = lambda f, c, **kwargs: str(dst_dir / "file.txt")

    def mock_crash(path):
        raise RuntimeError("DBus connection died unexpectedly!")

    monkeypatch.setattr(organizer.notification_manager, "send_success_notification", mock_crash)

    result, info = organizer.process_file(str(src))
    assert result == "SUCCESS"
    assert info == str(dst_dir / "file.txt")
    assert not src.exists()
    assert (dst_dir / "file.txt").exists()


def test_pytest_environment_safety(tmp_path, monkeypatch):
    """Under PYTEST_CURRENT_TEST, send_success_notification safely returns False."""
    dest_file = tmp_path / "file.txt"
    dest_file.write_text("data")

    config = MockConfig(enable_notifications=True)
    notif_mgr = NotificationManager(config, SmartSortLogger(log_dir="test_logs"))
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_pytest_environment_safety (pytest)")

    assert notif_mgr.send_success_notification(str(dest_file)) is False
