# Changelog

All notable changes to the SmartSort project will be documented in this file.

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
