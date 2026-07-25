# CI Headless PyQt6 Fix Report

This report documents the resolution of the PyQt6 headless test execution failures in the Continuous Integration workflow.

---

## 1. Resolution Summary

To enable SmartSort PyQt6 components to execute safely inside headless environments, two targeted, minimal corrections were implemented:

1.  **Headless Platform Variable**: Configured the GitHub Actions test runner inside [.github/workflows/ci.yml](file:///home/websrp/SmartSort/.github/workflows/ci.yml) to execute `pytest` with `QT_QPA_PLATFORM: offscreen` environments.
2.  **Code Correction**: Fixed a missing `Path` import at the top of [src/gui/main_window.py](file:///home/websrp/SmartSort/src/gui/main_window.py) that caused a `NameError` crash when fallback icon resolution code was executed.

---

## 2. Technical Explanation

### Why Qt Crashed
Qt applications running on Linux attempt to load native display integration drivers (like X11's `xcb`). Since GitHub Actions virtual machines run headlessly without a graphical server, the platform driver fails to load, causing Qt to trigger a native `abort()` signal (exit code 134).

### Why the Fix Works
Setting `QT_QPA_PLATFORM=offscreen` instructs Qt to load the offscreen rendering platform plugin. This allows `QApplication` and GUI widget constructors to complete successfully without a display backend, permitting unit tests to validate application logic.

### Why Application Behaviour is Unchanged
No application functionality or end-user behavior was modified:
- The environment variable is defined exclusively inside the GitHub Actions workflow runner context.
- The `Path` import fix resolves a hidden coding issue, making icon fallback path checks robust for all package runtimes (Source, Debian, AppImage, Flatpak).
