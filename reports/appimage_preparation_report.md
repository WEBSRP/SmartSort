# AppImage Preparation Report

## Overview
Phase 4 focused on configuring the build environment for generating an AppImage. This provides users with a zero-installation, portable binary format.

## Structure
The `AppDir` blueprint was prepared inside `packaging/appimage/SmartSort.AppDir/`. It acts as the root filesystem for the bundled application.
- All Python sources are encapsulated securely in `usr/share/smartsort/`.
- `smartsort.desktop` and icons are mapped for desktop integration scripts (`appimaged` or `AppImageLauncher`).

## Execution Logic (`AppRun`)
The core executable wrapper `AppRun` dynamically determines its current mount point:
```bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PYTHONPATH="${HERE}/usr/share/smartsort"
exec python3 "${HERE}/usr/share/smartsort/main.py" "$@"
```
This guarantees that regardless of where the AppImage is executed or mounted via FUSE, it correctly locates the source modules and executes via the bundled or system Python runtime.

## Compilation Script
A simple `build_appimage.sh` script automates the structure setup so developers can run `appimagetool` directly on the `SmartSort.AppDir`.
