# SmartSort Background Operation and Startup Report

This report outlines the implementation details for establishing true background operation and terminal-free autostart for SmartSort.

---

## 1. Overview of the Design

To make SmartSort run as a true background application with automatic launch at system login on Debian 13 GNOME, we configured two key components:
1. **Autostart Launch (`.desktop` entry)**: Running PyQt6 in tray-minimized mode (`--service`) within the graphical session.
2. **Headless Daemon (`.service` entry)**: Running a terminal-free background watch folder worker using systemd.

---

## 2. Key Implemented Features

### A. Terminal-Free Autostart minimized to Tray
To start the GUI application in the background minimized to the system tray, we:
* Generated a desktop entry file at `~/.config/autostart/smartsort.desktop` with:
  ```ini
  [Desktop Entry]
  Type=Application
  Exec=/usr/bin/python3 /home/websrp/project/smartsort/main.py --service
  Path=/home/websrp/project/smartsort
  Hidden=false
  NoDisplay=false
  X-GNOME-Autostart-enabled=true
  Name=SmartSort
  Comment=SmartSort File Organizer Background Service
  ```
* **Resolved Startup Race Condition**: During GNOME login, the system tray extension (AppIndicator) can take a few seconds to load. Previously, the app checked `QSystemTrayIcon.isSystemTrayAvailable()` immediately on launch. If checked before GNOME initialized the tray interface, it returned `False`, falling back to displaying the full dashboard window. We modified [src/gui/main_window.py](file:///home/websrp/project/smartsort/src/gui/main_window.py) to initialize the tray icon unconditionally. Qt automatically attaches the tray icon to the panel as soon as the status notifier interface becomes active, ensuring the application starts hidden.

### B. Background Window Behavior (Minimizing to Tray)
* **Closing the Window**: Clicking the "Close" button on the dashboard window (`X` button) triggers the `closeEvent` where we intercept the event, ignore the exit signal, and call `self.hide()`. A desktop notification informs the user that the program is still running in the tray.
* **Exiting the Application**: Selecting **"Exit SmartSort"** from the system tray context menu calls `exit_application()`, which sets `self.really_exit = True` and calls `QApplication.quit()`, fully terminating the background processes.
* **Opening Dashboard**: Left-clicking the system tray icon triggers `on_tray_icon_activated` which calls `showNormal()` to display the dashboard.

### C. OS-Level Service Monitoring
The Settings panel and dashboard update their states dynamically using systemd query tools to display:
* `Running` (active and monitoring)
* `Stopped` (installed and enabled, but inactive)
* `Disabled` (installed but disabled)
* `Not Installed` (no systemd service unit file found)

---

## 3. Verification Instructions

To verify that background operation and autostart are working properly on your system:

### Step 1: Simulate Autostart Launch
Run the autostart command in your terminal to see if the window starts hidden and the tray icon appears:
```bash
python3 main.py --service
```
* **Expected Result**: No graphical window opens, the process runs silently, and a blue tray icon appears in the GNOME top bar. Clicking the blue circle displays the dashboard, and closing the dashboard hides it back to the tray. Selecting "Exit SmartSort" from the tray menu terminates the process.

### Step 2: Verification after Logout or System Reboot
1. Reboot your system or log out of your session.
2. Log back into GNOME.
3. Observe the GNOME top panel system tray.
   - The blue SmartSort circular tray icon should be visible immediately after login.
   - No terminal window or dashboard window should have opened.
4. Copy a small image file into your `Downloads/` directory:
   ```bash
   touch ~/Downloads/test_autostart_verify.png
   ```
5. Check if the file is instantly processed and sorted into your destination folders (e.g. `~/Pictures/Low_Quality/PNG/test_autostart_verify.png`), and inspect `logs/smartsort_20260621.log` to confirm background monitoring started automatically.
