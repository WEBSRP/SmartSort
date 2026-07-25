# Packaging Capability Matrix Report

## Executive Summary
This report outlines the implementation of the Packaging Capability Layer for SmartSort. Each distribution format (Source, Debian, AppImage, Flatpak) now exposes the feature set it natively supports. This prevents crashes, unhandled subprocess errors, or invalid file system access attempts when running in restricted environments (such as sandboxed Flatpaks).

---

## 1. Package Identification
We implemented environment-level package identification within [packaging.py](file:///home/websrp/SmartSort/src/utils/packaging.py) to resolve the execution format at runtime:

```python
class PackageType(Enum):
    SOURCE = "SOURCE"
    DEBIAN = "DEBIAN"
    APPIMAGE = "APPIMAGE"
    FLATPAK = "FLATPAK"
```

*   **FLATPAK**: Detected by checking if `/.flatpak-info` exists on the root file system.
*   **APPIMAGE**: Detected via `APPIMAGE` or `APPDIR` environment variables.
*   **DEBIAN**: Detected by verifying if the active module script path starts with `/usr/share/smartsort` or `/usr/lib/smartsort`.
*   **SOURCE**: Default fallback when no packaging environment attributes are matched.

---

## 2. Feature Capability Matrix
Rather than using ad-hoc checks, the application queries features through a centralized capability layer:

| Capability | Source | Debian | AppImage | Flatpak | Role |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **GUI** | Yes | Yes | Yes | Yes | Graphical window operations |
| **Tray** | Yes | Yes | Yes | Yes | System Tray minimization & options |
| **Notifications** | Yes | Yes | Yes | Yes | D-Bus desktop alert notifications |
| **Downloads Monitor** | Yes | Yes | Yes | Yes | Real-time file system monitoring (`watchdog`) |
| **Background Monitor** | Yes | Yes | Yes | **No** | Running watchers in background without GUI open |
| **Systemd Integration** | Yes | Yes | Yes | **No** | Registering user services via `systemctl --user` |
| **Autostart** | Yes | Yes | Yes | Yes | Auto launch during desktop environment session start |

---

## 3. Package Specific Handling

### 3.1. Debian & Source Checkouts
*   **systemd user services** are fully supported.
*   Users can dynamically `[Install]`, `[Start]`, `[Stop]`, and `[Restart]` the `smartsort.service` using standard `systemctl --user` commands via the GUI.

### 3.2. AppImage (Portable Background Services)
*   **Installation**: AppImage supports background service generation. Installing the service creates a user unit pointing directly to the current absolute AppImage file path:
    ```ini
    ExecStart=/path/to/current/SmartSort.AppImage --daemon
    ```
*   **Location Migration Detection**: If a user moves the AppImage to a different directory after registering the service, SmartSort will detect this on startup by parsing the `ExecStart` line in `smartsort.service` and comparing it to `os.environ["APPIMAGE"]`.
*   **Interactive Update Prompt**: If a discrepancy is found, the user is prompted:
    ```
    "The AppImage has moved. Update background service?"
    ```
    Confirming automatically regenerates the unit file and restarts the service using the new absolute path.

### 3.3. Flatpak Sandboxing Compliance
*   **The Problem**: Flatpak applications execute inside a secure sandbox container. Writing to host path `~/.config/systemd/user` or invoking `systemctl --user` on the host fails since the host's systemd daemon is outside the container.
*   **Resolution**: 
    1.  `get_service_status` returns `"Unavailable"`.
    2.  The settings UI hides all systemd interaction buttons (`Install`, `Start`, `Stop`, `Restart`).
    3.  A descriptive text block is displayed instead:
        *"Background services cannot be managed from inside a Flatpak sandbox."*
    4.  No subprocess calls are executed, preventing Python exceptions or console error traces.

---

## 4. Verification and Validation
*   **Testing**: All 33 unit tests pass successfully.
*   **Interface**: Verified the settings panel under flatpak runtime and verified that no systemd exception logs are printed.
*   **Release-ready builds**: Successfully compiled the `.deb` package, the `SmartSort.AppImage` bundle, and the `smartsort.flatpak` archive.
