# SmartSort Automatic Startup (Autostart) Implementation Report

This report documents the implementation of the true automatic startup (autostart) capability for SmartSort, enabling users to register/unregister the utility to start automatically at login.

---

## 1. Context & Motivation

Previously, the **Settings** panel exposed a checkbox for *"Start SmartSort Automatically at Login"*, but toggling the option was purely visual and had no actual effect on the system startup configurations. To resolve this, we implemented a unified **Autostart Manager** that dynamically registers or removes startup desktop entries.

---

## 2. Architecture & Design

### Autostart Manager (`src/utils/autostart.py`)
We created a dedicated `AutostartManager` utility class that handles the low-level desktop file generation and package-aware path parsing. 

- **Startup Syncing**: Checks if the desktop file `~/.config/autostart/smartsort.desktop` exists and is active.
- **Immediate Application**: Registers or removes the desktop file immediately upon toggle.
- **Path Verification**: Detects if the current file execution environment has changed (e.g. AppImage relocation) and prompts updates.
- **No Hardcoded Shell Execution**: Utilizes clean ini format parameters under XDG standard startup specifications.

---

## 3. Package-Aware Command Resolution

SmartSort runs in multiple packaging and sandbox contexts. The startup configurations resolve the `Exec` line as follows:

| Environment | Detected Package Type | Autostart Exec Command | Icon Path Style |
| :--- | :--- | :--- | :--- |
| **Source** | `PackageType.SOURCE` | `"{sys.executable}" "{main_path}" --service` | Absolute project path (`assets/icons/logo.png`) |
| **Debian** | `PackageType.DEBIAN` | `/usr/bin/smartsort --service` | System theme lookup name (`smartsort`) |
| **AppImage** | `PackageType.APPIMAGE` | `"{appimage_path}" --service` | Absolute project path (`assets/icons/logo.png`) |
| **Flatpak** | `PackageType.FLATPAK` | `flatpak run com.smartsort.SmartSort --service` | System theme lookup name (`smartsort`) |

*Note: The `--service` flag is passed to all command variants to ensure that when launched at boot, SmartSort starts minimized to the system tray.*

---

## 4. AppImage Relocation Detection

Since AppImages are portable executables, a user might move the file to a different folder. 

1. On application startup, `check_appimage_path_change` parses the existing autostart desktop entry (if enabled).
2. It compares the `Exec` path in the desktop entry against `os.environ.get("APPIMAGE")`.
3. If they differ, it presents a user-friendly graphical prompt (`QMessageBox.question`):
   > *"The AppImage has moved ... Update automatic startup configuration?"*
4. If accepted, it updates the desktop entry to point to the new location.

---

## 5. UI Integration & Real-Time Persistency

The settings page checkbox in [main_window.py](file:///home/websrp/SmartSort/src/gui/main_window.py) was updated:
- **Immediate Toggle Connect**: Linked `chk_autostart.clicked` directly to a handler (`on_autostart_clicked`).
- **Visual Success/Failure Notification**: Pushes desktop notifications via `show_notification` (using DBus/notify2/tray status) indicating immediate activation/deactivation.
- **Boot/Init Synchronize**: Syncs the initial checkbox state with the physical existence of `~/.config/autostart/smartsort.desktop`, correcting any configuration drift.

---

## 6. Automated Testing & Verification

We added robust tests in [tests/test_core.py](file:///home/websrp/SmartSort/tests/test_core.py) that mock filesystem paths and check:
- Creation and deletion of the `smartsort.desktop` file with valid attributes.
- AppImage relocation triggers (verifying correct detection when paths change).
- Custom autostart command generation output across different package types.

Running `python3 -m pytest tests/` verifies full test coverage and clean passage:
```bash
$ python3 -m pytest tests/
============================== 36 passed in 0.38s ==============================
```
