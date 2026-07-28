# Packaging

SmartSort v1.0.3 is distributed exclusively as a **Debian package (`.deb`)**.

Supported distributions:
- Debian 11 (Bullseye) and newer
- Ubuntu 22.04 LTS and newer
- Linux Mint 21 and newer
- Any Debian-based distribution with `python3-pyqt6` available

---

## Package Contents

The `.deb` package installs the following:

| Path | Description |
|---|---|
| `/usr/bin/smartsort` | Wrapper launch script |
| `/usr/share/smartsort/` | Application source (Python) |
| `/usr/share/smartsort/config/config.default.json` | Default configuration |
| `/usr/share/applications/smartsort.desktop` | Desktop launcher |
| `/usr/lib/systemd/user/smartsort.service` | User systemd service |
| `/usr/share/icons/hicolor/*/apps/smartsort*.png` | Application icons |

---

## Installing

```bash
sudo dpkg -i smartsort_1.0.3_all.deb
sudo apt-get install -f   # resolve any missing dependencies
```

## Uninstalling

```bash
sudo dpkg -r smartsort
```

---

## Building the .deb from Source

Prerequisites: `dpkg-deb`, `python3-pyqt6`, `python3-watchdog`, `python3-notify2`

```bash
bash packaging/debian/build_deb.sh
```

Output: `build/deb/smartsort_1.0.3_all.deb`

See [build.md](build.md) for detailed instructions.
