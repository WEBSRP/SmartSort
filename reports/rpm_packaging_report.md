# RPM Packaging Report

## Overview
Phase 2 involved drafting the RPM SPEC file to package SmartSort for Fedora, RHEL, and other RPM-based Linux distributions. 

## SPEC Configuration
The `smartsort.spec` file defines the build instructions, requirements, and metadata for `smartsort-0.5.0-1.noarch.rpm`.

- **Dependencies**: Resolves Python 3 dependencies specific to Fedora (`python3-pyqt6`, `python3-watchdog`).
- **Build Arch**: Architecture independent (`noarch`) to align with Python scripts.

## Installation Directives (`%install`)
The specification explicitly maps paths into `$RPM_BUILD_ROOT`:
- Python source copies into `/usr/share/smartsort/`.
- A bash launcher script into `/usr/bin/smartsort`.
- Icons correctly pushed into `/usr/share/icons/hicolor/scalable/apps/`.
- The desktop file for GNOME/KDE integration.
- The systemd unit file under `/usr/lib/systemd/user/`.

## Scriptlets
Contains `%post`, `%preun`, and `%postun` routines to:
1. Re-index `/usr/share/icons/hicolor` using `gtk-update-icon-cache`.
2. Reload `systemd` user daemons.
3. Automatically disable the service on removal.
