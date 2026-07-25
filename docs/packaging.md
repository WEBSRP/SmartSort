# Packaging Architecture

This document explains the official Debian packaging specification for SmartSort v1.0.1.

---

## 1. Supported Release Package

SmartSort v1.0.1 officially ships as a Debian package for:

- Debian
- Ubuntu
- Linux Mint
- Other Debian-based distributions

Future planned packaging formats:

- AppImage
- Flatpak
- RPM

## 2. Debian Packaging Specification
- **Metadata**: Control files are defined under `packaging/debian/DEBIAN/`.
- **Maintainer Scripts**: 
  - `postinst`: Updates GTK hicolor icon cache, systemd user daemons, and compiles python bytecode under `/usr/share/smartsort`.
  - `prerm` & `postrm`: Gently stops user systemd daemons and cleans up leftover files upon removal.
- **Service Integration**: Installs a user systemd service file under `/usr/lib/systemd/user/smartsort.service` pointing to `/usr/bin/smartsort`.

## 3. Build Output

Run:

```bash
./packaging/debian/build_deb.sh
```

The generated package is written to `build/deb/smartsort_<version>_all.deb`.
