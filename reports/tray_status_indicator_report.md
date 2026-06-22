# SmartSort Dynamic Tray Status Indicator Report

This report outlines the implementation details for establishing dynamic status indicators and context-aware tooltips for the SmartSort system tray icon.

---

## 1. Overview of the Design

To allow users to understand SmartSort's status instantly from the Linux system tray without opening the GUI dashboard, we introduced a context-aware system tray manager. The manager updates the tray icon color and tooltip content in real-time according to the active operation of the directory watcher.

To ensure minimal resource impact, the icons are programmatically drawn and cached in memory using a lightweight manager that runs seamlessly on PyQt6's main event thread.

---

## 2. Color and Operational State Mappings

We established **six distinct visual states** for the tray icon, color-coded using a modern, accessible palette:

| Color | Operational State | Trigger Event | Tooltip Content Example |
| :--- | :--- | :--- | :--- |
| 🟡 **Yellow** | **Startup / Initial Scan** | Application launched; initializing watcher. | `SmartSort` <br> `Status: Startup / Initial Scan` |
| 🟢 **Green** | **Idle / Monitoring** | Active watcher; waiting for incoming files. | `SmartSort` <br> `Status: Monitoring` <br> `Files Processed: 15` <br> `Rules Active: 8` |
| 🔵 **Blue** | **Processing Small File** | Detected incoming file **smaller than 1 GB**. | `SmartSort` <br> `Status: Processing` <br> `File: report.pdf` <br> `Size: 4.5 MB` |
| 🟠 **Orange** | **Processing Large File** | Detected incoming file **larger/equal to 1 GB**. | `SmartSort` <br> `Status: Processing (Large File)` <br> `File: linux_distro.iso` <br> `Size: 3.2 GB` |
| 🔴 **Red** | **Error State** | Directory write/transfer error occurred. | `SmartSort` <br> `Status: Error` <br> `Last Error: Permission denied` |
| ⚫ **Gray** | **Monitoring Paused** | Watcher paused by the user. | `SmartSort` <br> `Status: Paused` <br> `Files Processed: 15` <br> `Rules Active: 8` |

---

## 3. Tooltip Specifications

Tooltips update dynamically depending on the state, using clean formatting for maximum readability:

1. **Active/Idle Tooltip**:
   ```text
   SmartSort
   Status: Monitoring
   Files Processed: 123
   Rules Active: 10
   ```
2. **Processing Tooltip**:
   ```text
   SmartSort
   Status: Processing
   File: sample.mkv
   Size: 750 MB
   ```
3. **Error Tooltip**:
   ```text
   SmartSort
   Status: Error
   Last Error: Permission denied
   ```

---

## 4. Technical Implementation Detail

The system tray status monitoring is handled by two main code sections:

### A. Reusable State Manager (`TrayStateManager`)
We created a dedicated manager class in [src/gui/tray_manager.py](file:///home/websrp/project/smartsort/src/gui/tray_manager.py) to decouple state management from the window controller:
* **Icon Caching**: Drawn icons (`QIcon` wrapping `QPixmap` circles) are cached in an internal dictionary (`self.icon_cache`). The system never redraws icons for repeating states, keeping CPU and memory overhead at absolute zero.
* **Testing Mode Support**: The manager detects if it is running within a headless test runner (where `QApplication` is not initialized) and avoids calling Qt graphic functions to prevent core dump aborts.
* **Persistent Error Tracking**: Tracks an active error state through `self.has_active_error`. The error state persists across pause/resume cycles and only clears upon the next successful file transfer.

### B. GUI Event Handlers
We integrated the `TrayStateManager` inside [src/gui/main_window.py](file:///home/websrp/project/smartsort/src/gui/main_window.py):
* **Startup Timer**: Instantiates a single-shot timer inside the window constructor to display the Yellow startup icon for 2 seconds upon boot before transitioning to Idle/Paused.
* **Watcher Handlers**: 
  * `handle_new_file` performs an `os.path.getsize` call on the newly arrived file and triggers the transition to Blue (`< 1 GB`) or Orange (`>= 1 GB`).
  * `on_worker_finished` transitions to Green on successful organization (`SUCCESS`, `DUPLICATE`, `SKIPPED`) and Red on failure (`ERROR`).
* **Control Actions**: Pause and resume updates transition state to Gray and back to Monitoring/Error respectively.
* **Periodic Updates**: The dashboard stat sync loop (running every 3 seconds) keeps rules counts and processed files counts in the tooltip updated in real-time.

---

## 5. Verification and Unit Testing

We added robust testing for all state transitions:
1. **Passing Unit Tests**:
   Verified that **all 32 tests passed successfully** (`PYTHONPATH=. ./smartsort/bin/pytest`).
2. **Dedicated Transition Verification**:
   We added `test_tray_state_transitions` in [tests/test_core.py](file:///home/websrp/project/smartsort/tests/test_core.py) that mock-checks all states:
   * Startup display.
   * Idle monitoring.
   * Pause/resume behavior.
   * Small file size check (`500 MB` translates to Blue).
   * Large file size check (`2 GB` translates to Orange).
   * Error setting and persistent error preservation after pause/resume cycles.
   * Successful operation clearing the active error.
