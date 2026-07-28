# Release Notes — SmartSort v1.0.3

**Release Date:** 2026-07-28  
**Package:** `smartsort_1.0.3_all.deb`  
**Platforms:** Debian, Ubuntu 22.04+, Linux Mint 21+, and compatible Debian-based distributions

---

## Installation

```bash
sudo dpkg -i smartsort_1.0.3_all.deb
sudo apt-get install -f   # resolve any missing dependencies
```

To uninstall: `sudo dpkg -r smartsort`

---

## What's New in v1.0.3

### 🐛 Bug Fixes

#### CI Headless Hang — Root Cause Fixed

Previous releases experienced intermittent GitHub Actions CI hangs where all 40 unit tests passed but the `pytest` process never exited. The root cause has been identified and resolved:

- `start_monitor()` called `QMessageBox.warning()` when the configured downloads folder did not exist on the CI runner. `QMessageBox.warning()` starts an internal blocking modal event loop. In headless/offscreen environments with no user interaction possible, this ran forever.
- The test only mocked `QMessageBox.question`, leaving `warning`, `information`, and `critical` unguarded.
- **Fix:** All four `QMessageBox` static methods are now mocked in every test that creates a `SmartSortGUI` instance. `start_monitor()` is no longer called in tests that don't require an active monitor thread.

#### Process Exit Guarantee

- The `conftest.py` session teardown now registers `os._exit(0)` via `atexit` as a guaranteed process-exit backstop. This terminates the process unconditionally during Python's shutdown phase, after all test output has been written — even if Qt background threads or non-daemon Python threads remain alive.

#### `PYTEST_CURRENT_TEST` Guards

- `SmartSortGUI.__init__` no longer auto-starts `MonitorThread`, `status_timer`, or single-shot startup timers during test execution. This eliminates QThread and QTimer race conditions that previously caused intermittent CI failures.

---

### 🏗 Changes

#### Debian-Only Release

SmartSort v1.0.3 is officially distributed as a **Debian package only**. The following packaging formats have been removed:

- ~~AppImage~~
- ~~Flatpak~~

Rationale: These formats were planned but never implemented. Maintaining detection code and capability maps for unshipped formats added unnecessary complexity and was a source of test fragility. The codebase is now simpler and easier to maintain.

All AppImage and Flatpak branches have been removed from:
- `src/utils/packaging.py` — `PackageType` enum, `CAPABILITIES` map, `detect_package_type()`
- `src/utils/autostart.py` — `get_command()`, `get_icon_path()`, `check_appimage_moved()`
- `src/gui/main_window.py` — service install/status/UI branches, notification system, `verify_and_repair_startup_config()`
- `main.py` — icon installation guard

#### Repository Cleanup

- Removed 20 stale files: 16 technical reports, 2 runtime logs, the old v1.0.1 `.deb` build artifact, and an Obsidian vault that was committed accidentally.
- `.gitignore` fully rewritten with clean sections for Python, virtual environments, pytest, IDEs, OS files, logs, build artifacts, Debian package files, and local configuration.

#### Documentation Refresh

- `README.md`: Updated install command to v1.0.3; removed "Future Planned Packaging" section (AppImage, Flatpak, RPM); Debian-only framing.
- `docs/packaging.md`: Full rewrite for Debian-only distribution.
- `docs/build.md`: Full rewrite; removed non-Debian build targets; added headless testing guidance.
- `docs/release.md`: Updated release workflow commands; genericized the git tag example.
- `docs/ci_headless_hang_postmortem.md`: New permanent engineering document covering the full investigation, root cause chain, resolution, and lessons learned for future contributors.

---

## Dependency Requirements

| Package | Version |
|---|---|
| `python3` | ≥ 3.8 |
| `python3-pyqt6` | ≥ 6.0.0 |
| `python3-watchdog` | ≥ 2.0.0 |
| `python3-notify2` | ≥ 0.3.0 |
| `libglib2.0-0` | (system) |
| `gir1.2-notify-0.7` | (system) |

---

## Upgrade Notes

Upgrading from v1.0.1 is a drop-in replacement. No configuration migration is required. Existing `~/.config/smartsort/config.json` settings, rules, and autostart entries are preserved.

---

## Known Limitations

- System tray availability depends on the desktop environment. GNOME Shell (without the AppIndicator extension) and fully headless sessions do not support system tray icons. SmartSort falls back to showing the main window in these environments.
- Background service integration requires `systemd --user` support (available on all supported distributions).

---

## Full Changelog

See [CHANGELOG.md](../CHANGELOG.md) for the complete history.
