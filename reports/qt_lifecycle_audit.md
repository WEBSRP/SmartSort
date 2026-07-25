# Qt Lifecycle Audit Report

This report documents the audit of Qt resources, GUI widgets, background threads, and event loops created during testing.

---

## 1. Audited Qt and Background Resources

The following objects were audited for instantiation and destruction lifecycles:

| Object Type | Creation Location | Standard Destruction Location | Missing Cleanup / Leak Location |
| :--- | :--- | :--- | :--- |
| **`QApplication`** | `tests/test_core.py` (explicitly via `QApplication(sys.argv)`) | Implicit process exit | Leaked on headless CI when multiple tests instantiate QApplication without explicit release. |
| **`SmartSortGUI`** | `tests/test_core.py:1408` | `closeEvent` (only if close is accepted and `really_exit` is True) | The test instantiated `SmartSortGUI` without calling `close()`, leaking background timers and threads. |
| **`QTimer`** | `src/gui/main_window.py:114` (`status_timer`) | Garbage collection on parent deletion | Remains active if `SmartSortGUI` parent is not explicitly deleted. |
| **`MonitorThread`** | `src/gui/main_window.py:1899` (`monitor_thread`) | `closeEvent` -> `stop()` -> `quit()` | Thread continues executing its event loop indefinitely because `closeEvent` was never invoked. |
| **`watchdog.Observer`** | `src/monitor.py:120` | `FileMonitor.stop()` -> `observer.stop()` & `join()` | Thread remains alive in the background, keeping the parent process open. |
| **`QSystemTrayIcon`** | `src/gui/main_window.py:127` | Standard widget parent-child hierarchy cleanup | Remains active if not explicitly hidden or deleted. |

---

## 2. Recommendations

1.  **Reusable Application Instance**: Centralize `QApplication` instantiation into a session-scoped fixture in `tests/conftest.py`.
2.  **Explicit Cleanup Block**: Wrap `SmartSortGUI` instantiation and assertions in `test_verify_and_repair_startup_config` in a `try...finally` block. Explicitly stop background threads, timers, hide tray icons, and call `deleteLater()`.
3.  **Flush Events**: Process pending event queues using `qapp.processEvents()` before test finalization.
