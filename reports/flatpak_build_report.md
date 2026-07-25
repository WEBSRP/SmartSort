# SmartSort Flatpak Build Report

## Overview
This report details the implementation, permissions model, sandbox constraints, and verification of the SmartSort Flatpak packaging.

## Flatpak Details
*   **Application ID**: `com.smartsort.SmartSort`
*   **Runtime**: `org.kde.Platform` (branch `6.6`)
*   **SDK**: `org.kde.Sdk` (branch `6.6`)
*   **Staging Directory**: `packaging/flatpak/app_dir`
*   **Staging Manifest**: `packaging/flatpak/com.smartsort.SmartSort.yml`
*   **Output Bundle**: `smartsort.flatpak` (in project root)

## Permissions & Sandbox Settings
Following Flatpak's security principles of least privilege, we restricted permissions only to what is absolutely necessary:

*   `--socket=fallback-x11`, `--socket=wayland`: Allows GUI drawing under X11 or Wayland display servers.
*   `--share=ipc`: Required for IPC display server communication.
*   `--filesystem=xdg-download`: Access limited strictly to the user's host Downloads folder (no access to `~` or other directories).
*   `--talk-name=org.freedesktop.Notifications`: Access to host D-Bus notification service.
*   `--talk-name=org.kde.StatusNotifierWatcher`: Access to the host system tray notifier context to support dynamic tray icon status.
*   **No Network Access**: The `--share=network` permission was omitted as the application works fully offline.

## Implementation Details

### 1. Unified Staged Script (`smartsort.sh`)
*   Serves as the internal sandboxed command launcher, starting the Python engine:
    ```bash
    #!/bin/sh
    exec python3 /app/bin/main.py "$@"
    ```

### 2. Dependency Bundling
*   Dependencies listed in `requirements.txt` (`PyQt6`, `watchdog`, `notify2`, etc.) are compiled and installed into the `/app` prefix namespace using `pip3 install --prefix=/app`.

### 3. Icon Verification
*   Flatpak's validation checks require application icons under `/app/share/icons/hicolor/scalable/apps` to be perfect squares. 
*   We resized the main logo (`269x281`) to a padded, transparent square of `256x256` at `assets/icons/logo_square.png` to meet this requirement and ensure desktop launcher compliance.

### 4. Sandboxed Configuration & Logs
*   XDG directory resolution correctly points to sandboxed configurations:
    *   **Config Path**: `~/.var/app/com.smartsort.SmartSort/config/smartsort/config.json`
    *   **Log Path**: `~/.var/app/com.smartsort.SmartSort/data/smartsort/logs/`
*   This isolates files cleanly, preventing interference with other applications.

## Verification & Testing
*   The `build_flatpak.sh` script executes the complete compilation, staging, export, and bundle creation process:
    1.  `flatpak build-init` - Initializes the KDE runtime app directory.
    2.  `flatpak build --share=network` - Installs Python wheels via pip3.
    3.  `flatpak build-finish` - Confirms permissions and command entry points.
    4.  `flatpak build-bundle` - Packages the repository branch into a single `smartsort.flatpak` bundle.
*   The build completed successfully, and `smartsort.flatpak` was generated in the project root.
