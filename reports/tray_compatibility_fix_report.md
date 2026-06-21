# SmartSort System Tray Compatibility Bugfix Report

## 1. Executive Summary

This report documents the analysis and resolution of a critical startup hang in **SmartSort** caused by D-Bus and system tray incompatibility. In environments lacking a traditional StatusNotifierHost/Watcher (such as GNOME without tray extensions, or headless testing environments), `QSystemTrayIcon` raised a D-Bus error which led to subsequent system-status command blockages, hanging the user interface.

Tray support has been refactored to be completely **optional** and **fault-tolerant**, allowing SmartSort to run smoothly on any Linux desktop or headless environment without freezing.

---

## 2. Root Cause Analysis

### Why the error occurred
1. **D-Bus Error (`ServiceUnknown`)**:
   Under the hood in Qt6/PyQt6, `QSystemTrayIcon` on Linux attempts to register with the D-Bus service `org.kde.StatusNotifierWatcher`. If this service is not registered on the D-Bus session bus, Qt triggers a D-Bus error:
   ```
   QDBusError("org.freedesktop.DBus.Error.ServiceUnknown", "The name org.kde.StatusNotifierWatcher was not provided by any .service files")
   ```
2. **Event Loop Hang / Dashboard Freeze**:
   When this initialization error occurred, it disrupted the Qt event loop, but the application continued to start in a semi-broken state. Shortly after, the dashboard status timer fired `update_dashboard_stats()`, which invoked `get_service_status()`.
   `get_service_status()` executes `subprocess.run(["systemctl", "--user", "is-active", ...])`. Since the system's D-Bus connection was deadlocked/malfunctioning, `systemctl` blocked indefinitely trying to connect to the bus. Because `subprocess.run` blocks the main UI thread, the entire GUI interface froze, forcing the user to terminate it with `Ctrl+C`.
3. **Invisible Background State**:
   Because the system tray icon initialization crashed, the tray icon was never shown. If the user tried to minimize or close the application, the app intercepted the events, called `self.hide()`, and was left running invisibly in the background with no tray icon to restore it or exit it.

### Affected systems
* **GNOME Desktop**: (Often lacks a default system tray or `StatusNotifierWatcher` service unless third-party appindicator extensions are installed).
* **Headless Systems / Virtual Framebuffers (Xvfb)**: (No D-Bus StatusNotifierHost present).
* **CI and Automated Test Pipelines**.

---

## 3. Fix Applied

1. **Pre-Flight Availability Check**:
   Before attempting to instantiate `QSystemTrayIcon`, we verify its availability using the static method:
   ```python
   QSystemTrayIcon.isSystemTrayAvailable()
   ```
2. **Graceful Degradation and Exception Wrapping**:
   Tray icon initialization inside `setup_system_tray()` is wrapped in a robust `try/except` block. If tray support is missing or fails:
   * A warning is logged: `"System tray unavailable. Running without tray support."`
   * `self.tray_available` is set to `False`.
   * Startup continues normally.
3. **D-Bus Timeout Protections**:
   Added a `timeout=2.0` parameter to all `subprocess.run()` calls (for `systemctl` service status/control, `gsettings` dark mode checks, and `xdg-open` handlers). If D-Bus is unresponsive, these subprocesses will terminate after 2 seconds, avoiding a GUI hang.
4. **Behavior Adjustment Without Tray**:
   If `self.tray_available` is `False`:
   * Minimizing the window keeps it on the taskbar instead of calling `self.hide()`.
   * Closing the window exits the application gracefully rather than hiding it.
   * "Start Minimized" configuration options are ignored to prevent the application from running in a completely inaccessible hidden state.

---

## 4. Files Modified

| File Path | Modification Summary |
| :--- | :--- |
| [main.py](file:///home/websrp/project/smartsort/main.py) | Checks `window.tray_available` before honoring `--service` or `start_minimized` settings. |
| [src/gui/main_window.py](file:///home/websrp/project/smartsort/src/gui/main_window.py) | Wraps tray setup in `try/except` with `isSystemTrayAvailable()`, adds timeouts to subprocess calls, updates `changeEvent`/`closeEvent` handling. |
| [tests/test_core.py](file:///home/websrp/project/smartsort/tests/test_core.py) | Mock-tests tray available, unavailable, initialization failures, GNOME/headless environments, and startup behaviors. |

---

## 5. Verification & Test Results

All **29 automated tests** are passing successfully:

```bash
$ PYTHONPATH=. ./smartsort/bin/pytest
============================== 29 passed in 0.28s ==============================
```

### Added Test Cases
* `test_tray_available`: Verifies setup behavior when system tray is active.
* `test_tray_unavailable`: Verifies graceful warning logging when tray is disabled.
* `test_tray_initialization_failure`: Verifies that tray exceptions do not crash startup.
* `test_gnome_environment_tray_disabled`: Simulates GNOME shell without status notifier host.
* `test_headless_environment_tray_disabled`: Simulates virtual headless containers.
* `test_dashboard_startup_components`: Validates dashboard UI settings integration.
* `test_app_startup_without_tray_shows_window`: Verifies window displays instead of hiding when started minimized on tray-less systems.

---

## 6. Remaining Limitations

* Desktop notifications via `notify2` still require a running DBus daemon and notification server; if absent, they fail gracefully and log warnings silently.
