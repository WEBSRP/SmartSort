# Changelog

All notable changes to the SmartSort project will be documented in this file.

## [1.2.12] - 2026-11-19

- Organize folder offers **Reverse moves** for ten minutes after completion. The action is available in the completion dialog and on the folder page while SmartSort is open. Reversal verifies the sorted files, restores duplicate source copies, and reports conflicts individually.

## [1.2.11] - 2026-11-19

### Added
- Lightweight, deterministic purpose hints for explicitly named wallpapers, screenshots and coding challenges, plus structured programming-problem text and validated local source cues.
- Manual rules can opt into Content intelligence and take priority over automatic hints. New rules in the editor enable this option visibly; existing broad rules remain unmarked.

### Preserved
- No AI model, model runtime, OCR engine or new dependency is introduced. Uninformative images retain a type-only fallback instead of fabricated visual understanding.
- Existing project/bundle protection applies before manual overrides and purpose hints. Default desktop folders, preview-only testing and hash-verified transfers remain in effect.

## [1.2.10] - 2026-11-19

### Fixed
- Home-based automatic sorting and tester previews now reuse Linux desktop Pictures, Videos, Music and Documents locations instead of creating parallel Images/Media/Audio category folders.
- Academic, work and code hierarchies live under Documents; archives, installers and unknown files use category subfolders of Downloads. Recognized standard-folder prefixes in saved rules also use desktop locations.
- Desktop directories on other drives are validated against their specific approved root. Settings changes during a transfer fail safely instead of redirecting an in-flight deletion.

### Added
- A saved desktop-folder preference with detected location summaries. Explicit custom destination bases and reviewed folder-batch roots retain their existing boundaries.

## [1.2.9] - 2026-11-19

### Changed
- Standalone code now receives language subfolders: filename/type-only shell scripts preview as Code/Shell, Python as Code/Python, and other recognized source types similarly.
- Real loose-source classifications in Projects/Source include their detected language; explicitly named project hierarchies and academic classifications retain precedence.
- Tester labels now distinguish recognized file types from unknown semantic confidence instead of showing a misleading zero-percent type result.

### Fixed
- Broadened project protection for common Python/build manifests and package markers. Selecting an internal project subfolder or a file in it no longer bypasses its enclosing project boundary.

## [1.2.8] - 2026-11-19

### Added
- Rule Tester now previews the saved sorting mode, including Content intelligence, type fallbacks, rule priority, destination, confidence and evidence.
- Existing-file input performs bounded content/metadata analysis in a background worker; filename/size input previews available filename/type evidence without pretending to read content.
- Tester previews never run transfers or duplicate source removal. Queued results are discarded when routing settings, rules or inputs change.
- The optional extension field no longer overrides an existing filename suffix, preventing MP4 names from being tested as JPG.

## [1.2.7] - 2026-11-19

### Fixed
- Recursive sorting now keeps recognizable application bundles and project folders intact instead of moving their logos, resources, libraries or source files separately.
- Shared protection applies to folder scans, manual plans, queued download events and execution revalidation, including bundles detected while files are arriving.
- Added `.smartsort-ignore`: place this empty marker inside any custom bundle/folder that should never be recursively sorted.

## [1.2.6] - 2026-11-19

### Added
- Content intelligence includes subfolders by default in folder previews and automatic Downloads monitoring, with separate saved controls for each workflow.
- Populated directories moved into the watched Downloads tree are discovered recursively. Hidden, temporary and symlinked paths remain excluded.

### Fixed
- Recursive monitoring suppresses unchanged outputs written by either organizer, preventing immediate repeated sorting and preserving batch hierarchy. Subsequent edits are eligible for sorting again.
- Saving a changed monitoring scope restarts the GUI watcher; switching sorting modes restores the appropriate folder recursion preference.

## [1.2.5] - 2026-11-19

### Changed
- With duplicate detection enabled, incoming copies whose SHA-256 matches the existing destination are now removed in automatic downloads and folder organization. The existing destination is retained.
- Both files are hashed and rechecked before source removal; read errors, detected changes and removal failures preserve the source and report errors. Same-name files with different contents retain the configured collision policy.
- Dashboard counts, activity messages, settings and arrangement reports now describe duplicate source removal.

## [1.2.4] - 2026-11-19

### Fixed
- Content intelligence now uses known file types when semantic evidence is insufficient, rather than sending recognized formats to Others.
- Videos and audio receive useful fallback destinations; installers including DEB, AppImage, APK and XAPK fall back to Applications, and ordinary text files fall back to Documents.
- Folder previews and automatic downloads share these destinations, including when extraction is unavailable. Fallbacks remain explicitly low confidence; custom rules and meaningful content classifications retain precedence.

## [1.2.3] - 2026-11-18

### Fixed
- Compound archive extensions such as `.tar.gz` now match configured extension rules.
- Legacy video rules retain the correct size unit when migrated from normalized byte settings; the exact previously generated double-conversion error is repaired with a backup, preserving custom rules.
- Download watching now distinguishes changed files and rapid inode reuse at the same path, so a subsequent download is not silently ignored. Stability checks also detect writes that keep the file size unchanged.
- An older stability worker no longer removes a replacement file's pending state.

## [1.2.2] - 2026-11-18

### Added
- A small, static light/dark “Starting SmartSort…” panel before the dashboard loads, with no artificial delay.

### Fixed
- Repeated application launches now restore the existing dashboard instead of starting another GUI or download monitor.
- Instance ownership survives rapid launch races and recovers after crashes. Restart releases ownership before launching its replacement.
- Tray and minimized startup preferences remain supported; duplicate service launches stay quiet.

## [1.2.1] - 2026-11-18

### Added
- Explicit sorting mode: preserve existing Rules first behavior or choose Content intelligence to analyze files without applying saved routing rules.
- Dashboard and folder-preview mode summaries with a direct shortcut to the setting.

### Fixed
- Made the reason for unchanged sorting visible: broad existing rules previously bypassed content intelligence without an obvious alternative.
- Queued folder previews retain the selected mode and rules; changing the saved mode invalidates an older review.

### Compatibility
- Existing rules and the Rules first default are preserved. Content intelligence is an explicit saved choice affecting new downloads and folder previews. A separately running background service must be restarted to reload saved settings.

## [1.2.0] - 2026-11-18

### Added
- Offline file intelligence for text, PDF, Office/OpenDocument, images/media, source code and archive contents.
- Local origin detection, relationship clustering, hierarchical organization, confidence estimates and explainable evidence.
- Reviewed-plan GUI workflow with light/dark themes, extraction settings and enriched offline arrangement reports.
- Private XDG metadata/provenance caching and expanded multi-domain integration, privacy and package checks.

### Fixed
- Consistent classification between fresh and cached metadata; URL filtering before keyword derivation and cache storage.
- CI failure masking caused by forced exit-zero teardown; tests now terminate naturally and verify real exit codes.
- Debian icon ownership conflicts caused by installing shared hicolor theme files.

### Changed
- Debian dependencies now include pypdf, Pillow and mutagen, with optional Office SDK suggestions.
- Application and Debian package versions are synchronized at 1.2.0.

### Validation
- Three final local headless runs passed with 1,447 tests passed and one existing skip each.
- Hosted Ubuntu/Python 3.12 certification and documented performance targets remain pending; see `reports/file_intelligence_implementation.md`.

## [1.1.6] - 2026-08-18

### Added
- **Directory Organizer Feature**: Added a dedicated Dashboard tab and standalone core service (`src/core/directory_organizer.py`) enabling users to organize any selected folder on demand.
  - **Directory Selection & Browsing**: Easily select and configure target folders with persistent configuration defaults (`dir_organizer_last_path`, `dir_organizer_recursive`, `dir_organizer_generate_markdown`).
  - **Recursive & Non-Recursive Scanning**: Snapshot-based directory traversal supporting both shallow root-only scans and full subfolder recursion while safely ignoring hidden files/folders (`.git`, `.obsidian`, etc.), symlinks, and temporary download files.
  - **Dry-Run Preview Mode**: Inspect planned file categories and destinations without performing any filesystem modifications.
  - **Rigid 6-Stage Copy-Verify-Delete Safety Contract**: Files are transferred via `shutil.copy2`, verified for regular file attributes, size equality, and streaming 64KB SHA-256 cryptographic hash match before the original source file is removed. Incomplete or corrupted copies are immediately removed and source files preserved untouched.
  - **Content Duplicate Preservation**: If a destination file already exists with identical SHA-256 content, the destination is never overwritten, the source is never deleted, and the operation is recorded as `DUPLICATE`.
  - **Dynamic Collision Resolution**: Filename collisions with differing content are dynamically renamed (`_1`, `_2`) via `FileUtils.get_unique_path()`, verified for uniqueness, and recorded as `COLLISION_RESOLVED`.
  - **Searchable Arrangement Index (`SmartSort_Arrangement.md`)**: Automatically generates an index at the organized directory root with category breakdowns, original-to-final path mappings, isolated duplicate records, and offline clickable `file:///` local URIs.
  - **Thread-Safe Cancellation & Progress Monitoring**: Responsive background worker (`QThreadPool`/`QRunnable`) with real-time percentage progress, operation details, and safe thread cancellation.
  - **Qt-Free Core Decoupling**: Core business logic in `src/core/directory_organizer.py` has zero Qt dependencies, enabling 100% deterministic headless testing and CI stability.

## [1.0.6] - 2026-08-14

### Fixed
- **Physical File Identity Tracking on MOVE (Bug Fix)**: Fixed an issue where `monitor.py` tracked processed files by string path for up to 5 minutes. Since MOVE operations delete the source file upon successful transfer, subsequent downloads reusing the same filename/path were silently dropped by watchdog deduplication or falsely reported as already processed. `monitor.py` now identifies files by `(timestamp, inode, device)` tuples using `os.stat()`. Duplicate watchdog events for the same physical file are deduplicated, while new files reusing a previous path are correctly identified and processed immediately.
- **Event Debounce Coordination**: Updated `pending_files` and `processed_files` structures in `DownloadHandler` to coordinate on `(inode, device)` tuples, preventing duplicate processing while preserving thread-safe, non-blocking execution.

## [1.0.3] - 2026-07-28

### Added
- **Clickable Desktop Notifications**: Added interactive desktop notifications in `src/core/notifications.py`. Clicking a success notification opens the destination directory in the system file manager and automatically highlights/selects the organized file using a 4-tier Linux Freedesktop fallback hierarchy (`org.freedesktop.FileManager1` DBus `ShowItems` -> `xdg-open` -> `gio open`).
- **Smart Filename Cleanup**: Added intelligent filename cleanup feature in `src/core/filename_cleanup.py`. Automatically detects and renames generic, meaningless (`download`, `image`, `1`, `IMG_0001`), or excessively long filenames before categorizing and moving files. Features source domain extraction from extended attributes (`user.xdg.referrer.url` / `origin.url`), CDN domain mapping, intelligent word-boundary truncation, category fallback names, and complete extension preservation. Fully configurable via Settings (`smart_filename_cleanup`, `filename_min_length`, `filename_max_length`) and disabled by default.

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
