# Debian Packaging Report

## Overview
Phase 1 of packaging involved creating a production-ready Debian (`.deb`) package for SmartSort version 0.5.0. The goal was to provide a native installation experience on Debian/Ubuntu-based distributions.

## Architecture & Layout
The package uses standard `dpkg-deb` tooling with the following directory structure:
- `/usr/bin/smartsort`: The main launcher script.
- `/usr/share/smartsort/`: Contains the Python source files (`main.py`, `src/`, `config/`, `assets/`).
- `/usr/share/applications/smartsort.desktop`: The desktop entry for graphical launchers.
- `/usr/share/icons/hicolor/`: The system tray and launcher icons correctly categorized into multiple resolutions (`16x16`, `22x22`, `24x24`, `32x32`, `scalable`).
- `/usr/lib/systemd/user/smartsort.service`: Systemd service to run the daemon in the background.

## Scripts
- **postinst**: Updates the GTK icon cache and reloads the systemd user daemon so the app and its icon are immediately available.
- **prerm**: Safely stops and disables the systemd service upon uninstallation.
- **postrm**: Rebuilds the GTK icon cache to clean up any removed icons.

## Verification
- **Install/Uninstall**: Verified standard `dpkg -i` and `dpkg -r` workflows.
- **Dependencies**: Explicitly requires `python3-pyqt6`, `python3-watchdog`, `python3-notify2`, and standard GLib libraries to ensure correct functioning out-of-the-box.
