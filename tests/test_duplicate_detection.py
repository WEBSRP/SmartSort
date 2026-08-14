"""Regression tests for duplicate detection and MOVE/COPY path-reuse bugs.

These tests verify:
1. MOVE → path reuse → new file is processed (not silently ignored)
2. Concurrent duplicate watchdog events cannot process the same file twice
3. MOVE state cleanup (processed_files correctly tracks physical file identity)
4. COPY behaviour (source persists, not treated as stale)
5. Repeated watchdog events for the same physical file are deduplicated
6. Filename collision at destination is not treated as content duplication
7. File identity tracking uses inode+device, not just path strings

All tests are deterministic — no arbitrary sleeps, no GUI, no QApplication.
"""

import os
import time
import threading
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.monitor import DownloadHandler, _get_file_identity
from src.organizer import FileOrganizer
from src.utils.file_utils import FileUtils
from src.utils.logger import SmartSortLogger


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_organizer():
    org = MagicMock()
    org.logger = MagicMock()
    org.logger.debug = MagicMock()
    return org


def _make_handler(callback=None):
    """Create a DownloadHandler with a mock organizer and optional callback."""
    organizer = _make_mock_organizer()
    cb = callback or (lambda x: None)
    return DownloadHandler(organizer, cb)


def _make_organizer(temp_dir, dest_dir, extra_config=None):
    """Build a real FileOrganizer with minimal config pointing at temp dirs."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    class TestConfig:
        def get(self, key, default=None):
            overrides = {
                "destination_base": str(dest_dir),
                "rules": [],
                "large_file_threshold_gb": 2.5,
                "enable_duplicate_detection": True,
                "conflict_resolution": "rename",
                "smart_filename_cleanup": False,
            }
            if extra_config:
                overrides.update(extra_config)
            return overrides.get(key, default)

    return FileOrganizer(TestConfig(), SmartSortLogger(log_dir=str(temp_dir / "test_logs")))


# ===================================================================
# 1. MOVE → path reuse → new file MUST be processed
# ===================================================================

def test_move_then_reuse_path_processes_new_file(temp_dir):
    """After a file is processed (moved), a new file at the same path must
    be treated as a new file, not silently ignored."""
    processed = []

    def on_file(path):
        processed.append(path)

    handler = _make_handler(on_file)

    # Create first file and obtain its identity
    file_path = str(temp_dir / "test.pdf")
    Path(file_path).write_text("first version")
    first_identity = _get_file_identity(file_path)
    assert first_identity is not None

    # Simulate: monitor processed this file (records path + identity)
    handler.processed_files[file_path] = (time.time(), first_identity[0], first_identity[1])

    # Now simulate MOVE: remove the original file, create a new one at the
    # same path (different inode on Linux).
    os.unlink(file_path)
    Path(file_path).write_text("second version — completely different file")
    second_identity = _get_file_identity(file_path)

    # The new file MUST have a different inode (Linux guarantees this for
    # a fresh create after unlink).
    assert first_identity[0] != second_identity[0], (
        "OS reused the same inode — test cannot verify identity tracking"
    )

    # _handle_event should detect the inode difference and process the new file
    handler._handle_event(file_path)

    # The file should now be in pending_files (ready for stability check)
    assert file_path in handler.pending_files


def test_move_then_reuse_path_end_to_end(temp_dir):
    """Full pipeline: process_file with MOVE, then a new file at the same
    source path is processed successfully."""
    dest_dir = temp_dir / "dest"
    organizer = _make_organizer(temp_dir, dest_dir)

    # Create source file
    src = temp_dir / "report.pdf"
    src.write_text("original content")

    # Process it (this copies to dest and deletes source = MOVE)
    organizer.get_destination_path = lambda f, c=None, **kw: str(dest_dir / "Others" / "report.pdf")
    result, info = organizer.process_file(str(src))
    assert result == "SUCCESS"
    assert not src.exists(), "Source should be deleted after MOVE"
    assert (dest_dir / "Others" / "report.pdf").exists()

    # Now create a completely new file at the same source path
    src.write_text("brand new content, not a duplicate")

    # Process it again — it must NOT be treated as duplicate or skipped
    organizer.get_destination_path = lambda f, c=None, **kw: str(dest_dir / "Others" / "report.pdf")
    result2, info2 = organizer.process_file(str(src))

    # The destination already exists with different content, so conflict_resolution="rename"
    # should kick in, producing a unique path like report_1.pdf
    assert result2 == "SUCCESS"
    assert not src.exists(), "Source should be deleted after second MOVE"
    assert info2.endswith("report_1.pdf")


# ===================================================================
# 2. Concurrent duplicate events cannot process the same file twice
# ===================================================================

def test_concurrent_events_same_file_deduplicated(temp_dir):
    """Multiple _handle_event calls for the same physical file should result
    in at most one pending entry."""
    handler = _make_handler()

    file_path = str(temp_dir / "photo.jpg")
    Path(file_path).write_text("image data")

    # Simulate rapid watchdog events (CREATE + MODIFY + MODIFY)
    handler._handle_event(file_path)
    handler._handle_event(file_path)
    handler._handle_event(file_path)

    # Only one entry in pending_files
    assert file_path in handler.pending_files
    assert len(handler.pending_files) == 1


def test_concurrent_events_threaded(temp_dir):
    """Thread-safe: multiple threads calling _handle_event for the same file
    produce exactly one pending entry."""
    handler = _make_handler()

    file_path = str(temp_dir / "concurrent.txt")
    Path(file_path).write_text("data")

    barrier = threading.Barrier(5)
    results = []

    def call_handle():
        barrier.wait()
        handler._handle_event(file_path)
        with handler.lock:
            results.append(file_path in handler.pending_files)

    threads = [threading.Thread(target=call_handle) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    # Regardless of how many threads raced, only one pending entry
    assert len(handler.pending_files) == 1


# ===================================================================
# 3. MOVE state cleanup
# ===================================================================

def test_processed_files_tracks_identity_not_just_path(temp_dir):
    """processed_files stores (timestamp, inode, device) — not just path."""
    handler = _make_handler()

    file_path = str(temp_dir / "doc.pdf")
    Path(file_path).write_text("content")

    identity = _get_file_identity(file_path)
    handler.processed_files[file_path] = (time.time(), identity[0], identity[1])

    # Same path, same inode → considered already processed
    handler._handle_event(file_path)
    assert file_path not in handler.pending_files

    # Delete and recreate (new inode) → should be treated as new
    os.unlink(file_path)
    Path(file_path).write_text("different content")
    new_identity = _get_file_identity(file_path)
    assert identity[0] != new_identity[0], "OS reused inode — cannot verify"

    handler._handle_event(file_path)
    assert file_path in handler.pending_files


def test_mark_as_unprocessed_clears_entry(temp_dir):
    """mark_as_unprocessed removes the path from processed_files so
    the same file can be reprocessed on error."""
    handler = _make_handler()

    file_path = str(temp_dir / "retry.txt")
    Path(file_path).write_text("data")

    identity = _get_file_identity(file_path)
    handler.processed_files[file_path] = (time.time(), identity[0], identity[1])
    assert file_path in handler.processed_files

    handler.mark_as_unprocessed(file_path)
    assert file_path not in handler.processed_files


# ===================================================================
# 4. COPY behaviour — source persists
# ===================================================================

def test_copy_source_persists_not_treated_as_stale(temp_dir):
    """In a hypothetical COPY mode the source file remains. The organizer's
    process_file should not skip it just because the destination exists
    (that's a collision, not a 'duplicate' unless hashes match)."""
    dest_dir = temp_dir / "dest"
    organizer = _make_organizer(temp_dir, dest_dir,
                                extra_config={"conflict_resolution": "rename"})

    src = temp_dir / "notes.txt"
    src.write_text("original notes")

    # Pre-create destination with different content (collision, not duplicate)
    (dest_dir / "Others").mkdir(parents=True, exist_ok=True)
    (dest_dir / "Others" / "notes.txt").write_text("old notes")

    organizer.get_destination_path = lambda f, c=None, **kw: str(dest_dir / "Others" / "notes.txt")
    result, info = organizer.process_file(str(src))

    assert result == "SUCCESS"
    # Renamed to avoid collision
    assert info.endswith("notes_1.txt")


# ===================================================================
# 5. Repeated watchdog events for same physical file are deduplicated
# ===================================================================

def test_repeated_events_same_inode_blocked(temp_dir):
    """Once a file is in processed_files with matching inode, subsequent
    _handle_event calls for the same path are silently dropped."""
    call_count = 0

    def on_file(path):
        nonlocal call_count
        call_count += 1

    handler = _make_handler(on_file)

    file_path = str(temp_dir / "video.mp4")
    Path(file_path).write_text("video data")

    identity = _get_file_identity(file_path)
    handler.processed_files[file_path] = (time.time(), identity[0], identity[1])

    # Simulate multiple MODIFY events — all should be blocked
    for _ in range(10):
        handler._handle_event(file_path)

    assert call_count == 0, "No callback should fire for already-processed file"
    assert file_path not in handler.pending_files


# ===================================================================
# 6. Filename collision ≠ content duplication
# ===================================================================

def test_filename_collision_not_treated_as_duplicate(temp_dir):
    """A destination filename collision (same name, different content)
    should trigger rename conflict resolution, NOT return DUPLICATE."""
    dest_dir = temp_dir / "dest"
    organizer = _make_organizer(temp_dir, dest_dir,
                                extra_config={
                                    "enable_duplicate_detection": True,
                                    "conflict_resolution": "rename",
                                })

    src = temp_dir / "file.txt"
    src.write_text("new content ABC")

    (dest_dir / "Others").mkdir(parents=True, exist_ok=True)
    existing = dest_dir / "Others" / "file.txt"
    existing.write_text("different existing content XYZ")

    organizer.get_destination_path = lambda f, c=None, **kw: str(existing)
    result, info = organizer.process_file(str(src))

    assert result == "SUCCESS"
    assert "file_1.txt" in info


def test_actual_content_duplicate_returns_duplicate(temp_dir):
    """When source and destination have identical content AND duplicate
    detection is enabled, the result must be DUPLICATE (not SUCCESS)."""
    dest_dir = temp_dir / "dest"
    organizer = _make_organizer(temp_dir, dest_dir,
                                extra_config={"enable_duplicate_detection": True})

    src = temp_dir / "file.txt"
    src.write_text("identical content")

    (dest_dir / "Others").mkdir(parents=True, exist_ok=True)
    existing = dest_dir / "Others" / "file.txt"
    existing.write_text("identical content")

    organizer.get_destination_path = lambda f, c=None, **kw: str(existing)
    result, info = organizer.process_file(str(src))

    assert result == "DUPLICATE"
    # Source must NOT be deleted for duplicates
    assert src.exists()


# ===================================================================
# 7. _get_file_identity
# ===================================================================

def test_get_file_identity_returns_inode_device(temp_dir):
    """_get_file_identity returns a valid (inode, device) for existing files."""
    f = temp_dir / "id_test.txt"
    f.write_text("hello")
    identity = _get_file_identity(str(f))
    assert identity is not None
    assert isinstance(identity, tuple)
    assert len(identity) == 2
    ino, dev = identity
    assert ino > 0
    assert dev > 0


def test_get_file_identity_returns_none_for_missing():
    """_get_file_identity returns None for non-existent files."""
    assert _get_file_identity("/nonexistent/path/xyz.txt") is None


def test_get_file_identity_changes_after_recreate(temp_dir):
    """After deleting and recreating a file at the same path, the inode
    changes (the fundamental assumption enabling the fix)."""
    f = temp_dir / "recreate.txt"
    f.write_text("first")
    id1 = _get_file_identity(str(f))

    os.unlink(str(f))
    f.write_text("second")
    id2 = _get_file_identity(str(f))

    assert id1[0] != id2[0], (
        "Expected different inode after delete+recreate. "
        "If this fails, the OS reused the inode (rare but possible)."
    )


# ===================================================================
# 8. Cleanup expiry with new tuple format
# ===================================================================

def test_cleanup_expired_with_identity_tuples():
    """_cleanup_expired works correctly with (timestamp, inode, dev) tuples."""
    handler = _make_handler()
    handler.processed_files["/old"] = (time.time() - 400, 111, 1)
    handler.processed_files["/recent"] = (time.time() - 100, 222, 1)
    handler.processed_files["/fresh"] = (time.time(), 333, 1)

    handler._cleanup_expired()

    assert "/old" not in handler.processed_files
    assert "/recent" in handler.processed_files
    assert "/fresh" in handler.processed_files


# ===================================================================
# 9. Pending files use identity, not just path
# ===================================================================

def test_pending_files_different_inode_allows_reentry(temp_dir):
    """If a file path is in pending_files but the inode has changed,
    a new _handle_event should proceed (the old pending entry is for
    a different physical file)."""
    handler = _make_handler()

    file_path = str(temp_dir / "pending_test.txt")
    Path(file_path).write_text("first")
    id1 = _get_file_identity(file_path)

    # Simulate: path is pending for the first inode
    handler.pending_files[file_path] = id1

    # Delete + recreate → different inode
    os.unlink(file_path)
    Path(file_path).write_text("second")
    id2 = _get_file_identity(file_path)
    assert id1 != id2

    # _handle_event should detect the inode mismatch and add a new pending entry
    handler._handle_event(file_path)
    assert handler.pending_files[file_path] == id2
