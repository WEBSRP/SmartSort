# Packaging Architecture

This document explains the packaging specifications, sandboxing rules, and metadata definitions utilized for distributing SmartSort.

---

## 1. Debian Packaging Specification
- **Metadata**: Control files are defined under `packaging/debian/DEBIAN/`.
- **Maintainer Scripts**: 
  - `postinst`: Updates GTK hicolor icon cache, systemd user daemons, and compiles python bytecode under `/usr/share/smartsort`.
  - `prerm` & `postrm`: Gently stops user systemd daemons and cleans up leftover files upon removal.
- **Service Integration**: Installs a user systemd service file under `/usr/lib/systemd/user/smartsort.service` pointing to `/usr/bin/smartsort`.

---

## 2. AppImage Specification
- **Runtime**: Compiles into `SmartSort.AppDir/` containing an `AppRun` binary launcher.
- **FUSE-less Sandbox**: Built using `appimagetool` with `APPIMAGE_EXTRACT_AND_RUN=1` environment variables to support building without FUSE mounting privileges.
- **Paths**: Resource folder resolves relative to the SquashFS mountpoint at runtime.

---

## 3. Flatpak Sandboxing
- **Manifest**: Located at `packaging/flatpak/com.smartsort.SmartSort.yml`.
- **Offline Wheels**: Python dependencies are vendored under `packaging/flatpak/python-wheels/` to enable fully offline, sandbox-compliant builds.
- **Privilege Rules**:
  - Wayland and X11 access allowed.
  - XDG-download directory read/write access.
  - DBus notification interfaces enabled (`org.freedesktop.Notifications`).
