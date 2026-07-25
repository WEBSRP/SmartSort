# CI Headless Cleanup and Event Loop Fix Report

This report documents the resolution of the GitHub Actions CI hang due to dangling Qt resource and watchdog observer threads.

---

## 1. Executive Summary

- **Root Cause**: During execution of `test_verify_and_repair_startup_config`, a real instance of `SmartSortGUI` was instantiated. This launched a background `QTimer` (updating dashboard statistics) and a background `MonitorThread` containing a watchdog `Observer` thread. Since the test never closed or destroyed the GUI instance, the background threads and timers continued running, preventing the Python process from terminating.
- **Why GitHub Hung**: GitHub Actions runner runs headlessly and checks for process termination before ending a step. Dangling non-daemon threads (such as the watchdog thread) kept the pytest process alive indefinitely, causing a timeout.
- **Why Local Execution Succeeded**: Locally, the environment terminates the interactive session quickly and/or pytest handles termination signals differently, whereas CI runners wait for all threads to terminate.

---

## 2. Changes Made

1.  **Shared Session Fixture**: Created a single session-scoped `qapp` fixture in `tests/conftest.py` to reuse `QApplication` across tests and cleanly release it at the end of the test session.
2.  **Explicit Test Cleanup**: Refactored `test_verify_and_repair_startup_config` in `tests/test_core.py` to:
    - Instantiate the GUI inside a `try...finally` block.
    - Explicitly call `.stop()` on `status_timer`.
    - Explicitly call `.stop()` and `.wait()` on `monitor_thread` to stop the thread and join the watchdog observer.
    - Hide and release the tray icon.
    - Call `.close()` and `.deleteLater()` on the main window.
    - Run `qapp.processEvents()` to clear any deferred deletion events.

---

## 3. Why the Fix is Safe

- **No Production Code Changes**: No end-user functionality or desktop environment behavior has changed.
- **Improved Test Stability**: Prevents resource leaks and cross-test pollution by ensuring a clean slate after the test finishes execution.
