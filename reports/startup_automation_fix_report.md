# SmartSort Startup Automation Audit and Fix Report

## 1. Audit and Findings

The audit of the startup automation for SmartSort revealed several issues preventing production-ready automatic operation:

1. **Incorrect Interpreter Path**: The original `smartsort.service` file targeted `%h/project/smartsort/smartsort/bin/python`, which assumed a Python virtual environment. However, the system is configured to run Python dependencies system-wide using `/usr/bin/python3`.
2. **Missing `WorkingDirectory`**: Neither the systemd unit file template in the project root nor the dynamic service file generator in `src/gui/main_window.py` specified a `WorkingDirectory`. Without it, systemd runs the service in the user's home root (`~`) or `/`, preventing `ConfigManager` from loading the relative configuration paths (`config/config.json`).
3. **Missing `Path` Directive in Autostart**: The GNOME Autostart desktop entry generator in `main_window.py` was missing the `Path` directive. This caused autostart launches from the desktop to run in the wrong working directory, causing the PyQt6 application to create a new, default configuration rather than using the repository's configuration.
4. **Simplistic Service Status Logic**: The "Service Status" widget on the dashboard and settings controls did not reflect the actual OS-level systemd states. It only checked file existence and basic active state, mapping them to `Active`, `Inactive`, `Failed`, or `Error`. It lacked support for detecting `Disabled` or `Stopped` states.

---

## 2. Implemented Fixes

To resolve these startup issues and make the application robust, the following fixes were implemented:

### A. Systemd Service File Correction
We modified the static template at `smartsort.service` to match the exact paths of the current development machine, use the system Python interpreter (`/usr/bin/python3`), and specify the proper `WorkingDirectory`:
```ini
[Unit]
Description=SmartSort File Organizer Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/websrp/project/smartsort
ExecStart=/usr/bin/python3 /home/websrp/project/smartsort/main.py --daemon
Restart=on-failure

[Install]
WantedBy=default.target
```
This service configuration was copied to `~/.config/systemd/user/smartsort.service` and registered via `systemctl --user daemon-reload`.

### B. GUI Systemd Service and Autostart Generation Correction
We updated `src/gui/main_window.py` to:
1. Dynamic Working Directory inclusion for systemd services:
   ```python
   WorkingDirectory={main_path.parent}
   ```
2. Dynamic execution path support in GNOME Autostart:
   ```ini
   Path={main_path.parent}
   ```

### C. Refined Service Status State Logic
We overhauled the `get_service_status` logic in `src/gui/main_window.py` to query both `is-enabled` and `is-active` states, resolving precisely into the four target states:
* **Running**: If the service is active (`active`).
* **Stopped**: If the service is enabled but not running (`inactive` or `failed`).
* **Disabled**: If the service unit exists but is not enabled.
* **Not Installed**: If the service unit file does not exist.

We also updated `update_dashboard_stats` to color-code these states on the dashboard:
* **Running** $\rightarrow$ Green (`#2ec27e`)
* **Stopped** $\rightarrow$ Yellow (`#f5c211`)
* **Disabled** / **Not Installed** $\rightarrow$ Red (`#e01b24`)

---

## 3. Auto-Launch Evaluation (Debian 13 GNOME)

For a system running **Debian 13 GNOME (Wayland)**, we evaluated both auto-launch mechanisms:

| Feature / Criteria | GNOME Autostart (`.desktop`) | Systemd User Service (`.service`) |
| :--- | :--- | :--- |
| **Primary Use Case** | Graphical User Interface & System Tray | Headless / Daemon background organizer |
| **Wayland/X11 Access** | Fully integrated; inherits visual session variables. | No display access; fails if PyQt6 graphical UI is launched. |
| **System Tray Support**| Works perfectly (initializes the app in minimized tray). | N/A (daemon mode runs without GUI/tray). |
| **Process Management**| Managed by GNOME Shell session. | Managed by systemd; supports automatic restart on failure. |
| **Resource Footprint** | Moderate (loads PyQt6 graphical framework). | Very low (runs pure python watcher script). |

### Recommended Approach
* **For Desktop/GUI Users (Recommended)**: Use **GNOME Autostart**. By toggling **"Start SmartSort Automatically at Login"** in the Settings tab, SmartSort launches at desktop login, sits cleanly in the system tray, and handles file organization while keeping the UI accessible.
* **For Headless/Server Users**: Use the **Systemd User Service** in daemon mode (`systemctl --user enable smartsort.service`). This runs the organizer efficiently in the background without needing a graphical display.
* **Note**: Avoid running both at the same time to prevent watchdog file lock races or duplicate transfer notifications.

---

## 4. Verification and Testing

1. **Systemd Enablement on Login**:
   Verified by enabling the service via terminal:
   ```bash
   $ systemctl --user enable smartsort.service
   Created symlink /home/websrp/.config/systemd/user/default.target.wants/smartsort.service → /home/websrp/.config/systemd/user/smartsort.service.
   ```
2. **Service State Transitions**:
   We tested and verified the `get_service_status()` mapping programmatically:
   * **Active service**: `Running`
   * **Inactive & Enabled service**: `Stopped`
   * **Inactive & Disabled service**: `Disabled`
   * **Missing service file**: `Not Installed`
3. **Background File Sorting**:
   Started the systemd service and created a dummy file in `~/Downloads/`:
   ```bash
   $ echo "dummy png data" > ~/Downloads/test_image.png
   ```
   **Logs verification (`logs/smartsort_20260621.log`)**:
   ```text
   2026-06-21 13:54:04,258 - INFO - Daemon mode started. Monitoring downloads folder: /home/websrp/Downloads
   2026-06-21 13:54:19,671 - INFO - Daemon detected file: /home/websrp/Downloads/test_image.png
   2026-06-21 13:54:19,673 - INFO - File: test_image.png | Source: /home/websrp/Downloads/test_image.png | Dest: /home/websrp/Pictures/Low_Quality/PNG/test_image.png | Action: TRANSFER_SUCCESS | Result: SUCCESS
   2026-06-21 13:54:19,673 - INFO - Daemon processed file /home/websrp/Downloads/test_image.png. Result: SUCCESS, Info: /home/websrp/Pictures/Low_Quality/PNG/test_image.png
   ```
   The file was immediately processed and successfully moved to `/home/websrp/Pictures/Low_Quality/PNG/test_image.png` by the daemon.
