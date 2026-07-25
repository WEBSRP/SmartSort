# CI Headless PyQt6 Root Cause Analysis

This report details the investigation and root cause identification of the GitHub Actions runner crash.

---

## 1. Root Cause

PyQt6 requires connection to a Linux display platform integration plugin (typically X11 via `xcb` or Wayland) to render graphical components. On standard headless GitHub Actions runner machines, no active X server or Wayland compositor exists.
When the test suite instantiates GUI components, the Qt platform plugin fails to connect to a display, causing Qt to abort the process immediately with **Exit Code 134**.

---

## 2. Call Chain Analysis

The crash occurs during:
`tests/test_core.py` -> `test_verify_and_repair_startup_config()`

```
  test_verify_and_repair_startup_config()
    ↓
  QApplication(sys.argv)
    ↓
  gui = SmartSortGUI()  [QMainWindow subclass]
    ↓
  [NameError: name 'Path' is not defined inside main_window.py]
    (Secondary failure caught during local offscreen testing)
```

---

## 3. Offending Code & System State

1.  **Offending Initialization**: `app = QApplication(sys.argv)` tries to configure graphical device display properties on a runner with no display attached.
2.  **NameError**: The `Path` class from `pathlib` was referenced at line 83 in `src/gui/main_window.py` but was not imported, causing secondary NameError aborts.

---

## 4. Recommendations

1.  **Platform Integration Mocking**: Configure the test runner environment with the standard Qt offscreen platform plugin:
    ```bash
    QT_QPA_PLATFORM=offscreen
    ```
    This tells Qt to run the graphical backend headlessly without attempting to contact an active X server or display device.
2.  **Import Path**: Correct the `NameError` by importing `from pathlib import Path` at the top of `src/gui/main_window.py`.
