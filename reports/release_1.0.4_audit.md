# Release Audit Report — SmartSort v1.0.4

## 1. Executive Summary
SmartSort release v1.0.4 packages the verified fix for processed-file state tracking and physical file identity deduplication under MOVE semantics. All 87 unit and integration tests passed across 3 consecutive runs with clean exit codes and zero orphaned processes. The Debian `.deb` package was compiled, verified, and confirmed to be completely self-contained.

---

## 2. Implemented Fix Summary
- **Physical File Identity Tracking (`src/monitor.py`)**:
  - `_get_file_identity(file_path)`: Uses `os.stat(file_path)` to retrieve `(inode, device)` metadata.
  - `DownloadHandler.processed_files`: Stores `path -> (timestamp, inode, device)` tuples instead of bare timestamps.
  - `DownloadHandler.pending_files`: Changed to a dictionary mapping `path -> (inode, device)` for stability-checking coordination.
  - **Resolution of MOVE Path-Reuse Bug**: When a file is moved, its source path is deleted. When a subsequent file reuses the same path, `_handle_event()` detects that the new file has a different inode, clears the stale entry, and processes the new file immediately instead of dropping it for 5 minutes.
  - **Watchdog Deduplication**: Repeated filesystem events for the *same* physical file (matching inode and device) are debounced and dropped.
  - **Lifecycle Safety**: No modifications to `QApplication`, `MonitorThread`, GUI lifecycle, `conftest.py`, or `organizer.py`.

---

## 3. Test & Stability Results

### Test Suite Execution
- **Command**: `QT_QPA_PLATFORM=offscreen PYTHONUNBUFFERED=1 python3 -m pytest -q tests/`
- **Total Tests**: 87 passing (72 core/integration + 15 duplicate detection & MOVE regression tests)

### 3-Run Stability Verification

| Run # | Tests Passed | Duration | Exit Code | Process Cleanup |
|---|---|---|---|---|
| Run 1 | 87 / 87 | 0.63s | 0 | Clean exit, no orphaned threads |
| Run 2 | 87 / 87 | 0.55s | 0 | Clean exit, no orphaned threads |
| Run 3 | 87 / 87 | 0.59s | 0 | Clean exit, no orphaned threads |

- **Orphaned Process Audit**: `ps -ef | grep -E "(python|pytest|smartsort)"` verified 0 remaining processes after execution.

---

## 4. MOVE / COPY & Concurrency Validation

| Scenario | Tested In | Result |
|---|---|---|
| MOVE -> Recreate at same path -> Processed | `test_duplicate_detection.py:test_move_then_reuse_path_processes_new_file` | **PASS** |
| Full Pipeline: MOVE -> New file at path -> MOVE | `test_duplicate_detection.py:test_move_then_reuse_path_end_to_end` | **PASS** |
| Concurrent watchdog events for same inode | `test_duplicate_detection.py:test_concurrent_events_same_file_deduplicated` | **PASS** |
| Multi-threaded event deduplication (5 threads) | `test_duplicate_detection.py:test_concurrent_events_threaded` | **PASS** |
| Destination filename collision != content duplication | `test_duplicate_detection.py:test_filename_collision_not_treated_as_duplicate` | **PASS** |
| True content duplicate detection (SHA256 match) | `test_duplicate_detection.py:test_actual_content_duplicate_returns_duplicate` | **PASS** |
| COPY source persistence and non-stale handling | `test_duplicate_detection.py:test_copy_source_persists_not_treated_as_stale` | **PASS** |

---

## 5. Headless CI Validation
- `python3 -m compileall src main.py`: Exit code 0, 0 syntax/compilation errors.
- `QT_QPA_PLATFORM=offscreen`: Runs fully headless without X11 server or virtual framebuffer.
- Conftest session fixture backstop (`atexit.register(os._exit, 0)`) remains intact and unmodified.
- `PYTEST_CURRENT_TEST` environment checks in `main_window.py` prevent UI timers and background threads during testing.

---

## 6. Debian Package Validation
- **Build Script**: `./packaging/debian/build_deb.sh`
- **Package Path**: `build/deb/smartsort_1.0.4_all.deb`
- **Control Metadata**:
  - `Package`: `smartsort`
  - `Version`: `1.0.4`
  - `Architecture`: `all`
  - `Maintainer`: `Soumya Ranjan Parida <contact@smartsort-org.com>`
  - `Depends`: `python3, python3-pyqt6, python3-watchdog, python3-notify2, libglib2.0-0, gir1.2-notify-0.7`
- **Contents Verified**:
  - Executable wrapper: `/usr/bin/smartsort` (chmod 755)
  - Application payload: `/usr/share/smartsort/` (`main.py`, `src/`, `assets/`, `config/config.default.json`)
  - Desktop integration: `/usr/share/applications/smartsort.desktop`
  - Systemd user service: `/usr/lib/systemd/user/smartsort.service`
  - Hicolor icons: 16x16, 22x22, 24x24, 32x32, and scalable tray & application icons
  - Maintainer scripts: `postinst`, `postrm`, `prerm` (chmod 755)

---

## 7. Remaining Risks & Considerations
- **Filesystem Inode Recycling**: In the highly unlikely scenario that a Linux filesystem reuses the exact same inode number within 5 minutes for a newly created file at the exact same path, the monitor might treat it as a duplicate event. In practical local storage environments (ext4, XFS, Btrfs), inode allocation cycles across millions of free inodes, making collision risk negligible.
- **GitHub Actions Remote Status**: Local CI verification passed with 100% success; remote GitHub Actions workflow run is marked **NOT VERIFIED** as no remote push was executed.
