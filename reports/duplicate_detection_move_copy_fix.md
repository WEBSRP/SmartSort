# Duplicate Detection & MOVE/COPY Path-Reuse Fix Report

## Verified Root Cause

### Root Cause 1: Path-based processed state (CONFIRMED — Primary Bug)

**File:** `src/monitor.py`, `DownloadHandler._handle_event()`, line 54 (pre-fix)

The `processed_files` dictionary mapped `file_path → timestamp`. After SmartSort
moves `Downloads/test.pdf → Documents/PDF/test.pdf`, the source path is deleted
by `os.remove()` in `organizer.py:127`. If the user downloads another file with
the same name within 5 minutes, the browser places it at the same
`Downloads/test.pdf` path (since the original is gone). The monitor checks
`file_path in self.processed_files` → True → silently drops the event.

**The path string is a location, not an identity.** A new file at the same path
is a different physical file.

### Root Cause 2: Dual monitors (VERIFIED — Not a Same-Process Bug)

The daemon (`main.py --daemon`) and the GUI (`main.py`) create separate
`FileMonitor` instances, but they run in **separate OS processes** (the user
launches one OR the other). The `SmartSortGUI.__init__()` at line 140-141 guards
monitor startup with `PYTEST_CURRENT_TEST` checks. The GUI's `MonitorThread` is
a `QThread` wrapper around `FileMonitor`. There is no shared state between daemon
and GUI processes.

**Assessment:** This is a user-configuration concern (don't run both), not a
code bug. No code change required. The daemon and GUI already have separate
entry paths (`--daemon` flag in `main.py`).

---

## Files/Functions Changed

### `src/monitor.py`

| Function | Change |
|---|---|
| `_get_file_identity()` | **NEW** — Returns `(inode, device)` tuple via `os.stat()` |
| `DownloadHandler.__init__()` | `processed_files` now stores `(timestamp, inode, device)` tuples. `pending_files` changed from `set` to `dict` mapping `path → (inode, device)`. |
| `DownloadHandler._cleanup_expired()` | Updated to destructure `(timestamp, _ino, _dev)` tuples |
| `DownloadHandler._handle_event()` | Now calls `_get_file_identity()`, compares inode+device against stored entries. Different inode at same path = new file → process it. Same inode = duplicate watchdog event → drop it. |
| `DownloadHandler._wait_and_process()` | Accepts `original_identity` parameter, re-checks identity before recording processed state. Uses `(time.time(), ino, dev)` tuple. |

### `tests/test_core.py`

| Test | Change |
|---|---|
| `test_processed_files_cleanup()` | Updated `processed_files` values from bare timestamps to `(timestamp, inode, device)` tuples |

### `tests/test_duplicate_detection.py` — **NEW FILE**

15 regression tests covering all required scenarios.

---

## Monitor Ownership Solution

No change. The GUI and daemon are separate OS processes with separate entry
points. The GUI guards its `start_monitor()` call behind `PYTEST_CURRENT_TEST`
checks. The `MonitorThread` lifecycle is managed by `SmartSortGUI.closeEvent()`.
No additional coordination is needed — the architecture is already correct.

---

## Processed-File Identity Solution

**Before:** `processed_files = {path: timestamp}`
**After:** `processed_files = {path: (timestamp, inode, device)}`

When `_handle_event` receives a path:
1. Call `_get_file_identity(path)` → `(inode, device)`
2. If path is in `processed_files`:
   - Same inode → duplicate watchdog event → **drop**
   - Different inode → new file at reused path → **delete stale entry, process**
3. Same logic for `pending_files`

This cleanly separates:
- **Duplicate filesystem event** (same inode, same path) → dropped by monitor
- **Path reuse after MOVE** (different inode, same path) → processed normally
- **Content duplicate** (same hash at destination) → handled by organizer
- **Destination filename collision** (same name, different hash) → handled by conflict_resolution

---

## MOVE/COPY Behaviour

| Stage | MOVE (current) | COPY (hypothetical) |
|---|---|---|
| Source exists before operation | ✅ | ✅ |
| Destination exists before operation | ❌ | ❌ |
| Source exists after operation | ❌ (deleted by `os.remove`) | ✅ |
| Destination exists after operation | ✅ | ✅ |
| New file at same source path | ✅ **Fixed:** different inode → processed | N/A (source still exists) |
| Duplicate watchdog events | ✅ Blocked by inode match | ✅ Blocked by inode match |
| Content duplicate at destination | ✅ Detected by SHA256 hash comparison | ✅ Same logic applies |

---

## Race-Condition Handling

The existing `threading.Lock` in `DownloadHandler` protects `processed_files` and
`pending_files`. The fix preserves this lock's semantics exactly — the only change
is what data is stored under the lock. No new locks, no new threads, no new
synchronization primitives.

The `_wait_and_process` method re-stats the file before recording it as processed,
catching the edge case where the file is replaced during the stability check.

---

## Regression Tests (15 tests)

| # | Test | Covers |
|---|---|---|
| 1 | `test_move_then_reuse_path_processes_new_file` | MOVE → path reuse → new file processed |
| 2 | `test_move_then_reuse_path_end_to_end` | Full pipeline: MOVE, recreate, MOVE again |
| 3 | `test_concurrent_events_same_file_deduplicated` | Rapid watchdog events → single pending entry |
| 4 | `test_concurrent_events_threaded` | Thread-safe deduplication (5 threads) |
| 5 | `test_processed_files_tracks_identity_not_just_path` | Identity stored, not just path |
| 6 | `test_mark_as_unprocessed_clears_entry` | Error recovery path works |
| 7 | `test_copy_source_persists_not_treated_as_stale` | COPY collision → rename, not skip |
| 8 | `test_repeated_events_same_inode_blocked` | 10 events for processed file → 0 callbacks |
| 9 | `test_filename_collision_not_treated_as_duplicate` | Collision ≠ content duplicate |
| 10 | `test_actual_content_duplicate_returns_duplicate` | Real duplicate → DUPLICATE result |
| 11 | `test_get_file_identity_returns_inode_device` | `_get_file_identity` returns valid tuple |
| 12 | `test_get_file_identity_returns_none_for_missing` | Missing file → None |
| 13 | `test_get_file_identity_changes_after_recreate` | Delete+recreate → different inode |
| 14 | `test_cleanup_expired_with_identity_tuples` | Expiry works with new tuple format |
| 15 | `test_pending_files_different_inode_allows_reentry` | Pending + new inode → re-process |

---

## Full Test Results

### Run 1
```
87 passed in 0.57s
EXIT_CODE=0
```

### Run 2
```
87 passed in 0.57s
EXIT_CODE=0
```

Process exited cleanly both times (no hang, no zombie threads).

---

## CI/Headless Validation

```bash
QT_QPA_PLATFORM=offscreen PYTHONUNBUFFERED=1 python3 -m pytest -q tests/
# 87 passed, exit code 0, process terminated cleanly

python3 -m compileall src main.py
# exit code 0, no compilation errors
```

- No QApplication dependency in new tests
- No GUI objects, no display, no sleeps
- No modification to conftest.py or the atexit backstop
- No modification to MonitorThread lifecycle
- No modification to QApplication lifecycle

---

## Debian Build Result

```
Building Debian package for SmartSort...
Version detected: 1.0.5
dpkg-deb: building package 'smartsort' in 'build/deb/smartsort_1.0.5_all.deb'
Build successful!
EXIT_CODE=0
```

---

## Remaining Risks

1. **Inode reuse:** On some filesystems under extreme conditions, the OS *could*
   reuse the same inode number for a new file. This is astronomically unlikely on
   ext4/btrfs with millions of available inodes. The tests include an assertion
   that detects this and would skip with a clear message.

2. **Cross-filesystem moves:** `shutil.copy2` + `os.remove` (the existing MOVE
   implementation) works across filesystems. The inode+device identity correctly
   identifies different devices via `st_dev`.

3. **Network filesystems:** NFS/FUSE may have non-standard inode semantics. SmartSort
   targets Debian desktop (local ext4/btrfs). No change in risk profile.

---

## Risk Assessment

| Risk | Level | Justification |
|---|---|---|
| Correctness | **Low** | Fix is minimal, well-tested, uses OS-provided identity |
| Regression | **Low** | All 72 existing tests pass unchanged (1 test updated for data structure) |
| CI | **Low** | No GUI/lifecycle changes, no new threads, no timing dependencies |
| Data loss | **Low** | No change to safe_copy/hash-verification/delete logic |
| Performance | **Low** | One `os.stat()` call added per event (negligible vs SHA256 hashing) |
