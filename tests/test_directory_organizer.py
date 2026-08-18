import os
import shutil
import threading
from pathlib import Path

import pytest

from src.core.directory_organizer import (
    DirectoryOrganizer, OperationStatus, OrganizePlan,
    OrganizePlanItem, FileOperationRecord, OrganizeResult,
    DirectoryPreviewSummary
)
from src.utils.file_utils import FileUtils
from src.utils.logger import SmartSortLogger


class MockConfig:
    def __init__(self, overrides=None):
        self._data = {
            'enable_duplicate_detection': True,
            'conflict_resolution': 'rename',
            'rules': [
                {
                    'id': 'docs', 'name': 'Documents', 'enabled': True, 'priority': 1,
                    'conditions': [{'type': 'extension', 'value': ['.pdf', '.docx', '.pptx', '.xlsx']}],
                    'destination': 'Documents/{extension}'
                },
                {
                    'id': 'imgs', 'name': 'Images', 'enabled': True, 'priority': 2,
                    'conditions': [{'type': 'extension', 'value': ['.jpg', '.jpeg', '.png', '.gif']}],
                    'destination': 'Images/{extension}'
                },
                {
                    'id': 'code', 'name': 'Code', 'enabled': True, 'priority': 3,
                    'conditions': [{'type': 'extension', 'value': ['.py', '.cpp', '.java', '.js']}],
                    'destination': 'Code/{extension}'
                },
                {
                    'id': 'archives', 'name': 'Archives', 'enabled': True, 'priority': 4,
                    'conditions': [{'type': 'extension', 'value': ['.zip', '.rar', '.7z']}],
                    'destination': 'Archives/{extension}'
                },
            ],
            'smart_filename_cleanup': False,
            'filename_min_length': 4,
            'filename_max_length': 80,
        }
        if overrides:
            self._data.update(overrides)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def save_config(self, config=None):
        pass

    def load_config(self):
        return self._data

    @property
    def config(self):
        return self._data


def create_organizer(tmp_path, overrides=None):
    config = MockConfig(overrides)
    log_dir = Path(tmp_path) / '.smartsort_test_logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = SmartSortLogger(log_dir=str(log_dir))
    return DirectoryOrganizer(config, logger)


def organize_dir(organizer, root_dir, recursive=False, generate_report=True,
                 progress_callback=None, cancel_check=None):
    """Helper: scan -> plan -> execute -> optionally generate report."""
    files = organizer.scan(str(root_dir), recursive=recursive)
    plan = organizer.plan(str(root_dir), files)
    result = organizer.execute(plan, progress_callback=progress_callback,
                               cancel_check=cancel_check)
    if generate_report and any(r.status in (OperationStatus.VERIFIED_AND_MOVED,
                                             OperationStatus.COLLISION_RESOLVED,
                                             OperationStatus.DUPLICATE)
                               for r in result.records):
        organizer.generate_report(str(root_dir), result)
    return result


# --- Basic Functionality ---

def test_scan_empty_directory(tmp_path):
    organizer = create_organizer(tmp_path)
    files = organizer.scan(str(tmp_path))
    assert len(files) == 0


def test_scan_single_file(tmp_path):
    (tmp_path / "test.pdf").write_bytes(b"pdf content")
    organizer = create_organizer(tmp_path)
    files = organizer.scan(str(tmp_path))
    assert len(files) == 1
    assert "test.pdf" in files[0]


def test_scan_mixed_extensions(tmp_path):
    file_names = ["doc.pdf", "img.jpg", "vid.mp4", "script.py", "arch.zip"]
    for f in file_names:
        (tmp_path / f).write_bytes(b"content")

    organizer = create_organizer(tmp_path)
    files = organizer.scan(str(tmp_path))
    assert len(files) == 5


def test_unicode_and_spaces_in_filenames(tmp_path):
    files = ["DBMS Normalization (Final) © 2026.pdf", "日本語 テスト.docx"]
    for f in files:
        (tmp_path / f).write_bytes(b"content")

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)
    assert result.success_count == 2
    for f in files:
        assert not (tmp_path / f).exists()


# --- Copy-Verify-Delete Safety ---

def test_successful_copy_verify_delete(tmp_path):
    src_file = tmp_path / "test.pdf"
    original_content = b"test content for verification"
    src_file.write_bytes(original_content)
    original_hash = FileUtils.calculate_sha256(str(src_file))

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)

    assert result.success_count == 1
    assert not src_file.exists()

    # Find the moved file
    moved = list(tmp_path.glob("Documents/PDF/test.pdf"))
    assert len(moved) == 1
    assert moved[0].read_bytes() == original_content
    assert FileUtils.calculate_sha256(str(moved[0])) == original_hash


def test_destination_missing_aborts_deletion(tmp_path, monkeypatch):
    src_file = tmp_path / "test.pdf"
    src_file.write_bytes(b"test content")

    # Make copy2 a no-op so destination never appears
    monkeypatch.setattr(shutil, "copy2", lambda src, dst: None)

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)

    assert src_file.exists()
    assert result.success_count == 0
    assert result.error_count == 1


def test_size_mismatch_aborts_deletion(tmp_path, monkeypatch):
    src_file = tmp_path / "test.pdf"
    src_file.write_bytes(b"test content")

    real_copy2 = shutil.copy2

    def truncated_copy(src, dst):
        real_copy2(src, dst)
        # Corrupt the destination by truncating it
        with open(dst, 'wb') as f:
            f.write(b"short")

    monkeypatch.setattr(shutil, "copy2", truncated_copy)

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)

    assert src_file.exists()
    assert result.error_count == 1
    # Corrupted destination should be cleaned up
    moved = list(tmp_path.glob("Documents/PDF/test.pdf"))
    assert len(moved) == 0


def test_hash_mismatch_aborts_deletion(tmp_path, monkeypatch):
    src_file = tmp_path / "test.pdf"
    src_file.write_bytes(b"test content")

    real_copy2 = shutil.copy2

    def corrupt_copy(src, dst):
        real_copy2(src, dst)
        # Corrupt destination content (same size, different content)
        with open(dst, 'wb') as f:
            f.write(b"corrupt content!")  # Intentionally different but could be diff size

    # Corrupt the destination after copy, but patch getsize to return correct size
    real_getsize = os.path.getsize
    original_src_size = real_getsize(str(src_file))

    def patched_getsize(path):
        if "Documents" in str(path) and path != str(src_file):
            return original_src_size  # Fake the size check passing
        return real_getsize(path)

    monkeypatch.setattr(shutil, "copy2", corrupt_copy)
    monkeypatch.setattr(os.path, "getsize", patched_getsize)

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)

    assert src_file.exists()
    assert result.error_count == 1


def test_copy_exception_preserves_source(tmp_path, monkeypatch):
    src_file = tmp_path / "test.pdf"
    src_file.write_bytes(b"test content")

    monkeypatch.setattr(shutil, "copy2", lambda src, dst: (_ for _ in ()).throw(OSError("Simulated copy error")))

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)

    assert src_file.exists()
    assert result.success_count == 0
    assert result.error_count == 1


def test_delete_failure_records_partial_success(tmp_path, monkeypatch):
    src_file = tmp_path / "test.pdf"
    src_file.write_bytes(b"test content")

    real_remove = os.remove

    def mock_remove(path):
        if os.path.basename(path) == "test.pdf" and "Documents" not in str(path):
            raise PermissionError("Simulated delete error")
        real_remove(path)

    monkeypatch.setattr(os, "remove", mock_remove)

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)

    # Source preserved because delete failed
    assert src_file.exists()
    # Destination exists because copy+verify succeeded
    moved = list(tmp_path.glob("Documents/PDF/test.pdf"))
    assert len(moved) == 1
    # Status should be FAILED (delete failure)
    assert result.error_count == 1
    assert any("delete" in r.error.lower() for r in result.records if r.status == OperationStatus.FAILED)


def test_failure_isolation_continues_batch(tmp_path, monkeypatch):
    for i in range(5):
        (tmp_path / f"test_{i}.pdf").write_bytes(f"content {i}".encode())

    real_copy2 = shutil.copy2

    def mock_copy2(src, dst):
        if "test_2.pdf" in str(src):
            raise OSError("Fail on test_2")
        real_copy2(src, dst)

    monkeypatch.setattr(shutil, "copy2", mock_copy2)

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)

    assert result.success_count == 4
    assert result.error_count == 1
    assert (tmp_path / "test_2.pdf").exists()


# --- Boundary and Symlink Safety ---

def test_symlinks_skipped(tmp_path):
    real_file = tmp_path / "real.pdf"
    real_file.write_bytes(b"content")
    symlink_file = tmp_path / "link.pdf"
    try:
        symlink_file.symlink_to(real_file)
    except OSError:
        pytest.skip("Symlinks not supported on this filesystem")

    organizer = create_organizer(tmp_path)
    files = organizer.scan(str(tmp_path))
    # Only the real file, not the symlink
    assert len(files) == 1
    assert "real.pdf" in files[0]


def test_hidden_files_and_directories_skipped(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_bytes(b"git config")
    (tmp_path / ".DS_Store").write_bytes(b"ds store")
    (tmp_path / "normal.pdf").write_bytes(b"normal")

    organizer = create_organizer(tmp_path)
    files = organizer.scan(str(tmp_path))
    assert len(files) == 1
    assert "normal.pdf" in files[0]


def test_existing_arrangement_md_skipped(tmp_path):
    (tmp_path / "SmartSort_Arrangement.md").write_bytes(b"report")
    (tmp_path / "test.pdf").write_bytes(b"content")

    organizer = create_organizer(tmp_path)
    files = organizer.scan(str(tmp_path))
    assert len(files) == 1
    assert "test.pdf" in files[0]


def test_relative_destination_cannot_escape_root(tmp_path):
    (tmp_path / "escape.pdf").write_bytes(b"content")

    escape_overrides = {
        'rules': [
            {
                'id': 'escape', 'name': 'Escape', 'enabled': True, 'priority': 1,
                'conditions': [{'type': 'extension', 'value': ['.pdf']}],
                'destination': '../../outside/{extension}'
            }
        ]
    }
    organizer = create_organizer(tmp_path, overrides=escape_overrides)
    # plan() should skip files that escape root boundary
    files = organizer.scan(str(tmp_path))
    plan = organizer.plan(str(tmp_path), files)
    # The item should be excluded from plan (commonpath check fails)
    assert plan.total_files == 0
    assert (tmp_path / "escape.pdf").exists()


def test_system_root_directories_rejected(tmp_path):
    organizer = create_organizer(tmp_path)
    with pytest.raises(ValueError, match="protected"):
        organizer.scan("/")
    with pytest.raises(ValueError, match="protected"):
        organizer.scan("/etc")


# --- Collision and Duplicate Handling ---

def test_collision_rename_policy(tmp_path):
    # Pre-create destination with existing file
    dest_dir = tmp_path / "Documents" / "PDF"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "test.pdf"
    dest_file.write_bytes(b"old content")

    src_file = tmp_path / "test.pdf"
    src_file.write_bytes(b"new content")

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)

    assert not src_file.exists()
    # Original destination preserved
    assert dest_file.read_bytes() == b"old content"
    # Collision resolved to _1
    renamed = dest_dir / "test_1.pdf"
    assert renamed.exists()
    assert renamed.read_bytes() == b"new content"
    assert result.collision_count == 1


def test_collision_skip_policy(tmp_path):
    dest_dir = tmp_path / "Documents" / "PDF"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "test.pdf"
    dest_file.write_bytes(b"old content")

    src_file = tmp_path / "test.pdf"
    src_file.write_bytes(b"new content")

    organizer = create_organizer(tmp_path, overrides={'conflict_resolution': 'skip'})
    result = organize_dir(organizer, tmp_path, generate_report=False)

    assert src_file.exists()
    assert dest_file.read_bytes() == b"old content"
    assert result.skip_count == 1
    assert any(r.status == OperationStatus.SKIPPED for r in result.records)


def test_duplicate_identical_content_preserves_both_files(tmp_path):
    dest_dir = tmp_path / "Documents" / "PDF"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "test.pdf"
    dest_file.write_bytes(b"identical content")

    src_file = tmp_path / "test.pdf"
    src_file.write_bytes(b"identical content")

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)

    # CRITICAL: Both files must be preserved
    assert src_file.exists()
    assert dest_file.exists()
    assert dest_file.read_bytes() == b"identical content"
    # Status must be DUPLICATE, NOT VERIFIED_AND_MOVED
    assert result.duplicate_count == 1
    assert result.success_count == 0
    assert any(r.status == OperationStatus.DUPLICATE for r in result.records)
    assert not any(r.status == OperationStatus.VERIFIED_AND_MOVED for r in result.records)


def test_intra_batch_filename_collision(tmp_path):
    # Two files in different subdirs that map to same target
    dir1 = tmp_path / "sub1"
    dir2 = tmp_path / "sub2"
    dir1.mkdir()
    dir2.mkdir()

    (dir1 / "test.pdf").write_bytes(b"content from sub1")
    (dir2 / "test.pdf").write_bytes(b"content from sub2")

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, recursive=True, generate_report=False)

    # Both should complete: one as VERIFIED_AND_MOVED, one as COLLISION_RESOLVED
    total_success = result.success_count + result.collision_count
    assert total_success == 2

    # Both files should exist in destination
    dest_dir = tmp_path / "Documents" / "PDF"
    all_pdfs = list(dest_dir.glob("test*.pdf"))
    assert len(all_pdfs) == 2


# --- Preview / Dry-Run ---

def test_preview_does_not_modify_filesystem(tmp_path):
    src_file = tmp_path / "test.pdf"
    src_file.write_bytes(b"content")
    original_hash = FileUtils.calculate_sha256(str(src_file))
    mtime = src_file.stat().st_mtime

    organizer = create_organizer(tmp_path)
    preview = organizer.preview(str(tmp_path))

    assert preview.total_files == 1
    assert src_file.exists()
    assert src_file.stat().st_mtime == mtime
    assert FileUtils.calculate_sha256(str(src_file)) == original_hash
    assert not (tmp_path / "Documents").exists()


def test_preview_counts_accurate(tmp_path):
    (tmp_path / "1.pdf").write_bytes(b"content")
    (tmp_path / "2.docx").write_bytes(b"content")
    (tmp_path / "3.jpg").write_bytes(b"content")

    organizer = create_organizer(tmp_path)
    preview = organizer.preview(str(tmp_path))

    assert preview.total_files == 3
    assert preview.category_counts.get("Documents", 0) == 2  # .pdf and .docx
    assert preview.category_counts.get("Images", 0) == 1     # .jpg


# --- Arrangement Index Report ---

def test_arrangement_markdown_generated(tmp_path):
    (tmp_path / "test.pdf").write_bytes(b"content")

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=True)

    md_file = tmp_path / "SmartSort_Arrangement.md"
    assert md_file.exists()
    assert md_file.stat().st_size > 0


def test_arrangement_markdown_searchable_paths(tmp_path):
    (tmp_path / "searchable_test.pdf").write_bytes(b"content")

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=True)

    md_file = tmp_path / "SmartSort_Arrangement.md"
    content = md_file.read_text(encoding="utf-8")
    assert "searchable_test.pdf" in content
    assert "Documents" in content
    assert str(tmp_path) in content


def test_arrangement_markdown_file_uris(tmp_path):
    (tmp_path / "uri_test.pdf").write_bytes(b"content")

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=True)

    md_file = tmp_path / "SmartSort_Arrangement.md"
    content = md_file.read_text(encoding="utf-8")
    assert "file:///" in content


def test_arrangement_markdown_no_network_dependency(tmp_path):
    (tmp_path / "offline_test.pdf").write_bytes(b"content")

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=True)

    md_file = tmp_path / "SmartSort_Arrangement.md"
    assert md_file.exists()
    content = md_file.read_text(encoding="utf-8")
    # No http:// or https:// references
    assert "http://" not in content
    assert "https://" not in content


# --- Cancellation ---

def test_cancellation_stops_scheduling(tmp_path):
    for i in range(10):
        (tmp_path / f"test_{i:02d}.pdf").write_bytes(f"content {i}".encode())

    organizer = create_organizer(tmp_path)
    files = organizer.scan(str(tmp_path))
    plan = organizer.plan(str(tmp_path), files)

    cancel_event = threading.Event()
    call_count = 0

    def cancel_after_first():
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            cancel_event.set()
        return cancel_event.is_set()

    result = organizer.execute(plan, cancel_check=cancel_after_first)

    assert result.cancelled is True
    # At most 2 files processed (first goes through, second triggers cancel)
    total_processed = result.success_count + result.error_count + result.collision_count
    assert total_processed < 10


# --- End-to-End Acceptance Scenario (Section 17) ---

def test_end_to_end_acceptance_scenario(tmp_path):
    """
    Test End-to-End Acceptance Scenario (Section 17 of task.md):
    Setup:
      College/
      ├── a.pdf
      ├── b.docx
      ├── c.jpg
      └── nested/
          └── d.pptx
    1. Preview (recursive=True): 4 files detected, 0 modified.
    2. Non-Recursive Organize: a.pdf, b.docx, c.jpg organized; nested/d.pptx untouched; report with 3 entries.
    3. Recursive Organize: nested/d.pptx organized; report updated.
    """
    college_dir = tmp_path / "College"
    college_dir.mkdir()
    nested_dir = college_dir / "nested"
    nested_dir.mkdir()

    (college_dir / "a.pdf").write_bytes(b"content A")
    (college_dir / "b.docx").write_bytes(b"content B")
    (college_dir / "c.jpg").write_bytes(b"content C")
    (nested_dir / "d.pptx").write_bytes(b"content D")

    organizer = create_organizer(tmp_path)

    # 1. Preview Mode (Recursive)
    preview = organizer.preview(str(college_dir), recursive=True)
    assert preview.total_files == 4
    assert preview.category_counts.get("Documents", 0) == 3  # .pdf, .docx, .pptx
    assert preview.category_counts.get("Images", 0) == 1     # .jpg
    # Verify zero mutations
    assert (college_dir / "a.pdf").exists()
    assert (college_dir / "b.docx").exists()
    assert (college_dir / "c.jpg").exists()
    assert (nested_dir / "d.pptx").exists()
    assert not (college_dir / "SmartSort_Arrangement.md").exists()

    # 2. Non-Recursive Organize Mode
    non_rec_result = organize_dir(organizer, college_dir, recursive=False, generate_report=True)
    assert non_rec_result.success_count == 3
    assert not (college_dir / "a.pdf").exists()
    assert not (college_dir / "b.docx").exists()
    assert not (college_dir / "c.jpg").exists()
    # nested/d.pptx must remain untouched in nested/
    assert (nested_dir / "d.pptx").exists()

    # Verify report generated
    report_file = college_dir / "SmartSort_Arrangement.md"
    assert report_file.exists()
    report_text = report_file.read_text(encoding="utf-8")
    assert "a.pdf" in report_text
    assert "b.docx" in report_text
    assert "c.jpg" in report_text
    assert "d.pptx" not in report_text

    # 3. Recursive Organize Mode
    rec_result = organize_dir(organizer, college_dir, recursive=True, generate_report=True)
    assert rec_result.success_count == 1
    # nested/d.pptx should now be organized and removed from nested/
    assert not (nested_dir / "d.pptx").exists()

    # Updated report should include d.pptx
    updated_report = report_file.read_text(encoding="utf-8")
    assert "d.pptx" in updated_report
    assert "file:///" in updated_report

