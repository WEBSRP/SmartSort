# SmartSort Tray Icon Theme Fix Report

## Executive Summary
A system tray icon regression was identified where the previous implementation replaced the user's `~/.local/share/icons/hicolor` directory with a symbolic link pointing to the project assets. This action broke the lookup of system-wide GNOME icons, causing them to disappear or render with incorrect fallbacks. 

This fix resolves the regression by keeping the user's hicolor theme intact, copying the individual SmartSort assets into the correct size-specific subdirectories inside `~/.local/share/icons/hicolor/`, and updating the GTK icon cache.

---

## 1. Root Cause Analysis
Previously, `main.py` performed an automatic symbolic link of `~/.local/share/icons/hicolor` to `assets/icons/hicolor`. 
* **The Bug**: Symlinking `hicolor` completely shadowed the user's local custom and application icons stored in that theme directory.
* **The Consequences**: GNOME lost access to other desktop application icons, and SmartSort itself failed to load system tray status indicators correctly on some desktops, rendering a `...` placeholder.

---

## 2. Implemented Fix

### A. Safe Installation Logic (No Directory Replacement)
We removed the symlink code entirely. The new function `ensure_user_icons_installed` in [main.py](file:///home/websrp/project/smartsort/main.py#L56):
1. Detects if `~/.local/share/icons/hicolor` is a symlink pointing to the project assets, and if so, safely unlinks it.
2. Creates `~/.local/share/icons/hicolor` as a standard directory if it does not exist (or leaves it intact if it is already a directory).
3. Creates the required subdirectories:
   * `16x16/apps/`
   * `22x22/apps/`
   * `24x24/apps/`
   * `32x32/apps/`
   * `scalable/apps/`

### B. Logo Scaling and Renaming
To conform to standard desktop expectations, the main application logo is installed as `smartsort.png`:
* For `scalable/apps/smartsort.png`, it copies the original full-resolution `logo.png` from `assets/icons/logo.png`.
* For `16x16`, `22x22`, `24x24`, and `32x32`, the installer uses PyQt6's `QImage` to perform a smooth, high-quality scale of the logo and saves it to the target directory.

### C. Dynamic State Icons Installation
The status colors are copied and renamed from the project assets to the user's theme directory:
* `tray_yellow.png` &rarr; `smartsort-yellow.png` (Startup/Scan)
* `tray_green.png` &rarr; `smartsort-green.png` (Monitoring/Idle)
* `tray_blue.png` &rarr; `smartsort-blue.png` (Processing Small File)
* `tray_orange.png` &rarr; `smartsort-orange.png` (Processing Large File)
* `tray_red.png` &rarr; `smartsort-red.png` (Error)
* `tray_grey.png` &rarr; `smartsort-grey.png` (Paused)

### D. Icon Cache Refresh
After copying the assets, the installer triggers:
```bash
gtk-update-icon-cache -t ~/.local/share/icons/hicolor
```
This forces GNOME/GTK to rebuild its theme index and load the new icons immediately without requiring a user logout or reboot.

---

## 3. Configuration & Tray Integration
In [src/gui/tray_manager.py](file:///home/websrp/project/smartsort/src/gui/tray_manager.py#L55):
* We updated the tray status icons mapping to use the standard theme names:
  ```python
  state_mapping = {
      TrayState.STARTUP: "smartsort-yellow",
      TrayState.IDLE: "smartsort-green",
      TrayState.PROCESSING_SMALL: "smartsort-blue",
      TrayState.PROCESSING_LARGE: "smartsort-orange",
      TrayState.ERROR: "smartsort-red",
      TrayState.PAUSED: "smartsort-grey"
  }
  ```
* Fallback logic maps the new names back to `tray_*.png` locally in case theme loading fails on non-standard desktops.
* Main window theme lookup uses `smartsort` instead of `logo`.
* Diagnostic checks were updated to query and print resolutions of the installed icons in the user's local theme directory.

---

## 4. Verification and Testing

### A. Directory Structure Check
We verified that the files were installed under `~/.local/share/icons/hicolor` in all target directories:
* `~/.local/share/icons/hicolor` is a standard directory (`drwxrwxr-x`).
* All icons are correctly populated with sizes matched to their parent folder names.

### B. GTK/PyQt6 Theme Resolution Test
We ran a test to verify if the theme-based icon queries are resolved correctly by GTK:
```python
from PyQt6.QtGui import QIcon
for name in ["smartsort", "smartsort-green", "smartsort-blue", "smartsort-orange", "smartsort-red", "smartsort-grey", "smartsort-yellow"]:
    assert not QIcon.fromTheme(name).isNull()
```
**Results**:
* `smartsort` resolved: **True**
* `smartsort-green` resolved: **True**
* `smartsort-blue` resolved: **True**
* `smartsort-orange` resolved: **True**
* `smartsort-red` resolved: **True**
* `smartsort-grey` resolved: **True**
* `smartsort-yellow` resolved: **True**

### C. Automated Unit Testing
A new unit test `test_ensure_user_icons_installed` was added to `tests/test_core.py`. The test suite runs automatically and passes successfully:
* **Total Tests**: 33 passed (100% success rate)
