# Flatpak Runtime Compatibility Audit Report

## Executive Summary
This report details the Flatpak runtime compatibility audit, addressing notifications warnings, GPU/EGL render node permissions, host icon cache bypass, and the SDK upgrade to the supported `6.9` runtime target.

## Audit Findings & Resolutions

### 1. Task 1 — Sandboxed Notifications
*   **The Issue**: Previously, the PyQt6 system tray logic loaded `notify2` which triggered a `"No module named 'dbus'"` failure because `dbus-python` is not available in the Flatpak sandbox.
*   **Resolution**: Implemented runtime environment detection (`is_flatpak = os.path.exists("/.flatpak-info")`). When running in Flatpak:
    1.  Bypasses `notify2` imports completely.
    2.  Attempts to send desktop notification alerts via the **Desktop Notifications Portal D-Bus API** (`org.freedesktop.portal.Notification`) by issuing a `gdbus call --session`.
    3.  Falls back automatically to PyQt6's native `QSystemTrayIcon::showMessage` if portal D-Bus calls time out or fail.
*   **Graceful Degredation**: Subprocess and import exceptions are caught silently, preventing stack trace outputs in headless environments.

### 2. Task 2 — GPU / EGL Rendering
*   **The Issue**: Running PyQt6 in Wayland/X11 inside the sandbox without hardware access printed warnings:
    `libEGL warning: wayland-egl: could not open /dev/dri/renderD128`
*   **Resolution**: Added `--device=dri` to the Flatpak manifest `finish-args` list. This exposes host rendering nodes (GPU acceleration) to the sandbox, completely resolving the EGL initialization warning while keeping graphics operations accelerated and smooth.

### 3. Task 3 — Host Icon Cache Pollution
*   **The Issue**: `ensure_user_icons_installed` attempted to install files under `~/.local/share/icons` and run `gtk-update-icon-cache`, which is not compliant with sandboxed application behavior.
*   **Resolution**: Added early environment detection inside the icon staging hook:
    ```python
    is_flatpak = os.path.exists("/.flatpak-info")
    if is_flatpak:
        return  # Bypasses host icon filesystem writes
    ```
    This restricts icon resolution to the Flatpak bundle assets folder (`/app/share/icons/`), allowing the desktop environment to handle icon caches natively during Flatpak installation.

### 4. Task 4 — Supported Runtime Upgrade
*   **The Issue**: The previous build targeted KDE Platform/SDK version `6.6`, which is built on the end-of-life Freedesktop SDK `23.08`.
*   **Resolution**: Upgraded both `com.smartsort.SmartSort.yml` and `build_flatpak.sh` to target KDE Software Platform version `6.9`.

## Conclusion
The Flatpak package is now fully audited, sandboxed, and upgraded. All writes to host icon themes have been disabled, GPU permissions added, and D-Bus notifications portal hooks established.
