# Changelog

All notable changes to the SmartSort project will be documented in this file.

## [1.0.3] - 2026-07-28

### Fixed
- **CI Headless Hang (Root Cause)**: `start_monitor()` called `QMessageBox.warning()` when
  the configured downloads folder did not exist on GitHub-hosted runners (`/home/runner/Downloads`
  is not created by default). `QMessageBox.warning()` was not mocked in the test, causing it to
  start a blocking modal event loop that never resolved in a headless environment.
- **QMessageBox Mock Coverage**: Expanded `test_verify_and_repair_startup_config` to mock all
  four `QMessageBox` static methods (`question`, `warning`, `information`, `critical`), preventing
  any unguarded dialog from blocking the headless runner.
- **Process Exit After Tests**: `conftest.py` session teardown now registers `os._exit(0)` via
  `atexit` as a guaranteed process-exit backstop, ensuring pytest terminates even if Qt background
  objects or non-daemon threads remain alive after the session.

### Changed
- **Debian-Only Release**: Removed AppImage and Flatpak `PackageType` variants, detection logic,
  capability maps, and all related autostart branches. SmartSort v1.0.3 is officially Debian-only.
- **`PYTEST_CURRENT_TEST` Guard**: `SmartSortGUI.__init__` no longer auto-starts `MonitorThread`,
  `status_timer`, or single-shot startup timers during test execution, eliminating QThread and
  QTimer race conditions in the CI test environment.
- **Repository Cleanup**: Removed 15 stale technical reports, runtime log files, the old `.deb`
  build artifact, and the Obsidian vault from the `reports/` directory.
- **Documentation Refresh**: Updated `docs/build.md`, `docs/packaging.md`, `docs/release.md`,
  and `README.md` to reflect Debian-only installation, remove references to planned packaging
  formats, and correct all version references to v1.0.3.
- **`.gitignore` Rewrite**: Replaced the previous minimal `.gitignore` with a comprehensive set
  of sections covering Python, virtual environments, pytest, IDEs, OS files, logs, build
  artifacts, Debian package files, and local configuration.

## [1.0.1] - 2026-07-25

### Fixed
- Fixed a `MonitorThread` startup/shutdown race that could leave the Qt event loop running when a stop request arrived before the thread entered `exec()`, causing CI to hang before the pytest summary.
- Blocked rule destinations that resolve outside the configured destination base directory.

### Changed
- Consolidated the v1.0.1 release as a Debian-first release for Debian, Ubuntu, Linux Mint, and other Debian-based distributions.
- Removed unsupported package implementations and CI artifact generation for future planned package formats.

## [1.0.0] - 2026-07-25

### Added
- Standardized XDG Base Directory specification compliance:
  - Configuration saved to `$XDG_CONFIG_HOME/smartsort/config.json`.
  - Logs stored inside `$XDG_STATE_HOME/smartsort/`.
- Central Path Manager class `AppPaths` for programmatic path resolutions.
- Automatic settings and log migration logic from legacy directories.
- Centralized `build/` directory for generated package binaries.
- GitHub Actions CI workflow configuration.
- Standard open-source community files: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, and issue/pull request templates.
- Developer documentation: `docs/architecture.md`, `docs/build.md`, `docs/packaging.md`, `docs/configuration.md`, `docs/release.md`, `docs/rule_engine.md`.

### Changed
- Re-routed all compile binaries output directory to `build/`.
- Updated test suite with XDG path compliance verification cases.

## [0.5.0-UI] - 2026-07-25

### Added
- Modern Adwaita CSS themes for both Light and Dark modes.
- High-visibility vector SVG checkbox checkmark indicators inline inside the stylesheet (resolving checkbox hidden/low-contrast rendering issues).
- Custom scrollbar styling in dark mode to prevent bright white unstyled background tracks.
- Dynamic transition and border glow animations on statistic panels (`QFrame.Card`).
- Clean visual separators on the rules editor controls.
- Flat cards layout for status text and testers parameters.
- Monospace font configuration on the dashboard logs display window.

### Changed
- Decoupled application startup checkbox options from systemd background services sections in Settings.
- Restructured layout spacing (`12px`) and margins (`16px`) across all tabs for a comfortable, clean look.
- Set unified `'Inter'` font families globally for clean, modern typography.
- Enabled zebra striping (`alternatingRowColors`) on logs history and rules tables.
- Styled primary dialog buttons with standard GNOME Blue (`#3584e4`).

### Fixed
- Fixed unstyled white scrollbar tracks when running in Dark theme.
- Fixed checkbox visibility issues on screen panel scaling.
- Fixed RuleDialog button box alignments and contents spacing.
