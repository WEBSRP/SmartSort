# Duplicate Detection, MOVE/COPY Semantics, and Watchdog Race Condition Report

## 1. Executive Summary
SmartSort is exhibiting severe race conditions and state-tracking bugs caused by a mismatch between its file-processing semantics (MOVE) and its watchdog event-tracking implementation, compounded by a dual-process architecture (Daemon + GUI). This causes false "DUPLICATE" reports, false "File already processed or removed" logs, and silent ignorance of newly downloaded files.

## 2. Reproduction
The issues can be reproduced under two primary conditions:
**Condition 1 (Dual Process Race):** Start both the background daemon (`main.py --daemon`) and the GUI (`main.py`). Drop a single file into the Downloads folder. 
**Condition 2 (Same-Path Reuse):** Drop `test.pdf` into Downloads. Let SmartSort move it. Within 5 minutes, drop a completely new, different file named `test.pdf` into Downloads.

## 3. Expected Behaviour
- A single downloaded file should be processed exactly once, generating exactly one success log.
- A newly downloaded file (even if it shares a name with a recently moved file) should be processed immediately.
- Duplicate detection should only flag actual content duplicates that pre-exist in the destination, not falsely flag the ongoing transfer.

## 4. Actual Behaviour
- **False Duplicates / Missing Logs:** The GUI logs `"Skipped: ... (File already processed or removed)"` or logs a `"SKIP_DUPLICATE"` for the exact same file the Daemon just successfully moved.
- **Silent Ignorance:** If a user downloads `test.pdf` twice within 5 minutes, the second download is completely ignored by the monitor and never categorized.

## 5. Root Cause
**CONFIRMED:** 
1. **Dual-Monitor Race Condition:** Both `run_daemon()` and `SmartSortGUI` instantiate a `FileMonitor` watching the same directory. They race to process the same watchdog events.
2. **State Key Flaw (MOVE vs COPY):** `monitor.py` tracks processed files in `self.processed_files` using the absolute `file_path` as the key, with a 5-minute expiry. Because SmartSort uses **MOVE** semantics, the original path is deleted. Subsequent downloads reuse the same path (since the browser doesn't need to append `(1)` to the filename). The monitor sees the reused path, thinks it was processed recently, and silently ignores it.

## 6. Code Path
- `src/monitor.py : DownloadHandler._handle_event : Line 54` - Checks `file_path in self.processed_files` and drops events for reused paths.
- `src/organizer.py : FileOrganizer.process_file : Line 65` - `os.path.exists(file_path)` check fails in the slower racing thread, causing the "File already processed or removed" log.
- `src/organizer.py : FileOrganizer.process_file : Line 105` - TOCTOU race: Slower thread sees `dest_path` (created by the faster thread), hashes match, returns "DUPLICATE".

## 7. MOVE vs COPY Analysis

| Stage | MOVE (Current Implementation) | COPY (Hypothetical / Standard Browser) |
| :--- | :--- | :--- |
| Source exists before operation | Yes | Yes |
| Destination exists before operation | No | No |
| Source exists after operation | **No** (Deleted by `os.remove`) | **Yes** |
| Destination exists after operation | Yes | Yes |
| Processed state records | Absolute Path `Downloads/test.pdf` | Absolute Path `Downloads/test.pdf` |
| Subsequent browser download | Uses path `Downloads/test.pdf` (Original is gone) | Uses path `Downloads/test (1).pdf` |
| Subsequent watchdog events | Fired for `test.pdf`. **IGNORED** by monitor because path is in `processed_files` | Fired for `test (1).pdf`. Processed correctly because path is new. |
| Expected behavior | Process new file | Process new file |

*Conclusion:* The `processed_files` dictionary using `file_path` as a key is intrinsically incompatible with MOVE semantics. 

## 8. Watchdog Event Analysis
**Scenario:** File `test.pdf` downloaded while Daemon and GUI are running.
1. Watchdog emits `on_created('test.pdf')` to **both** processes.
2. Daemon Thread & GUI Thread both wait for file size stability.
3. Both stabilize simultaneously. Both check `os.path.exists` -> True.
4. Daemon copies file to `Documents/PDF/test.pdf`.
5. GUI enters `process_file`, checks `os.path.exists(dest_path)` -> True (Daemon just made it).
6. GUI hashes both -> Match. GUI logs "DUPLICATE".
7. Daemon deletes `test.pdf`.

## 9. State Machine
Current states are heavily conflated due to the race conditions. 
SmartSort currently collapses:
- `SUCCESSFULLY_MOVED` (by another process)
- `ALREADY_PROCESSED` (by the same process due to reused path)
- `SOURCE_MISSING` (deleted before processing)

SmartSort must guarantee:
> A file identity is defined by its path AND its inode (or creation time). Reusing a path for a new file must reset its processed state. Exactly one processor should act on a file.

## 10. Existing Test Coverage
Current test suite (`test_core.py`, `test_organizer.py`) mocks file operations but lacks comprehensive concurrency, race-condition, and dual-process watchdog tests. Tests do not currently cover path-reuse within the 5-minute expiry window.

## 11. Required Regression Tests
Claude should add the following tests:
1. **Path Reuse Test:** Create `test.txt`, process it (MOVE). Immediately create a new `test.txt` with different content. Verify it is processed and not ignored.
2. **Concurrency Race Test:** Call `process_file('test.txt')` from two threads simultaneously to ensure only one succeeds and the other fails gracefully without logging false duplicates.
3. **Duplicate Detection Test:** Verify genuine duplicates (existing destination, identical hashes) are skipped, but do not delete the source file.

## 12. Recommended Fix
1. **Monitor State Tracking:** Modify `self.processed_files` in `monitor.py` to store/check the file's `inode` or file creation time, not just the string path. If the path exists but the inode differs, it is a new file.
2. **Single Instance Guarantee:** Ensure `SmartSortGUI` communicates with the Daemon instead of spawning a second `FileMonitor`. If a daemon is running, the GUI should act as a dumb client. If no daemon is running, the GUI can run the monitor. Alternatively, use a robust file-based lock (e.g., `flock` or a PID file) so only one `FileMonitor` can be active system-wide.
3. **TOCTOU Mitigation:** In `process_file`, acquire a file lock on the source file before evaluating conditions and performing the safe copy, ensuring atomic processing.

## 13. Things Claude Must NOT Break
- existing CI stability and headless tests
- watchdog lifecycle and debounce stability
- MOVE behaviour (must still delete original file on success)
- Debian packaging
- filename cleanup and notifications (which depend on the file existing at the destination)

## 14. Risk Assessment
- **Correctness risk:** High (Concurrency bugs are inherently tricky to fix without deadlocks).
- **Regression risk:** Medium (Changing state keys from path to path+inode might affect cross-platform Windows/Mac support if they don't support inodes, though SmartSort is Debian-native).
- **Data-loss risk:** Low (The current safe copy verifies hashes before deleting).
- **Performance risk:** Low.

## 15. Confidence
Root Cause Confidence: 10/10
Reproduction Confidence: 10/10
Recommended Fix Confidence: 9/10
Test Coverage Confidence: 8/10
Overall Investigation Confidence: 10/10

## Claude Opus Implementation Handoff
- **Files to inspect:** `src/monitor.py` (state tracking), `src/organizer.py` (duplicate detection race), `src/gui/main_window.py` (duplicate monitor instantiation), `src/main.py`.
- **Functions involved:** `DownloadHandler._handle_event`, `DownloadHandler._wait_and_process`, `FileOrganizer.process_file`.
- **Confirmed Root Cause:** (1) `processed_files` uses paths as keys, breaking on MOVE semantics when paths are reused. (2) GUI and Daemon spawn concurrent `FileMonitor` instances, creating a TOCTOU race condition in `process_file`.
- **Required Invariants:** A path reused by the OS for a new file must be treated as unprocessed. Only one `FileMonitor` instance should be actively processing files at any time.
- **Constraints:** SmartSort is strictly Debian-native (inodes are available). MOVE semantics must be preserved.
