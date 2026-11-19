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


def test_duplicate_identical_content_removes_source_copy(tmp_path):
    dest_dir = tmp_path / "Documents" / "PDF"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "test.pdf"
    dest_file.write_bytes(b"identical content")

    src_file = tmp_path / "test.pdf"
    src_file.write_bytes(b"identical content")

    organizer = create_organizer(tmp_path)
    result = organize_dir(organizer, tmp_path, generate_report=False)

    # Remove only the verified matching source copy.
    assert not src_file.exists()
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



# Phase 16: execution audit metadata and offline arrangement index.
@pytest.mark.parametrize('outcome', ['moved', 'collision', 'duplicate', 'skipped', 'missing', 'copy_error', 'mkdir_error', 'delete_error'])
def test_execution_preserves_reviewed_audit_metadata(tmp_path, monkeypatch, outcome):
    organizer = create_organizer(tmp_path, {'conflict_resolution': 'skip' if outcome == 'skipped' else 'rename'})
    source = tmp_path / 'lecture.pdf'
    source.write_bytes(b'lecture')
    target = tmp_path / 'College' / 'DBMS' / 'lecture.pdf'
    item = OrganizePlanItem(str(source), str(target), 'College/DBMS', 'Intelligence',
                           'REVIEW', ['Title: DBMS'], .72, 'course-1', 'DBMS Course')
    plan = OrganizePlan([item], str(tmp_path), 1, {'College/DBMS': 1}, 1, ['Partial metadata'])
    if outcome in {'collision', 'duplicate', 'skipped'}:
        target.parent.mkdir(parents=True)
        target.write_bytes(b'lecture' if outcome == 'duplicate' else b'other')
    if outcome == 'missing':
        source.unlink()
    def fail(*args, **kwargs):
        raise OSError('injected failure')
    if outcome == 'copy_error':
        monkeypatch.setattr(shutil, 'copy2', fail)
    if outcome == 'mkdir_error':
        monkeypatch.setattr(os, 'makedirs', fail)
    if outcome == 'delete_error':
        monkeypatch.setattr(os, 'remove', fail)
    result = organizer.execute(plan, progress_callback=lambda *args: item.evidence.append('late mutation'))
    record, = result.records
    expected = {'moved': OperationStatus.VERIFIED_AND_MOVED, 'collision': OperationStatus.COLLISION_RESOLVED,
                'duplicate': OperationStatus.DUPLICATE, 'skipped': OperationStatus.SKIPPED}
    assert record.status == expected.get(outcome, OperationStatus.FAILED)
    assert (record.confidence, record.confidence_score, record.cluster_id, record.cluster_name) == ('REVIEW', .72, 'course-1', 'DBMS Course')
    assert record.evidence == ['Title: DBMS']
    assert result.warnings == ['Partial metadata']
    record.evidence.append('record only')
    assert 'record only' not in item.evidence
    if outcome == 'collision':
        assert record.target != str(target)


def audit_record(tmp_path, name='lecture.pdf', **kwargs):
    values = dict(source=str(tmp_path / name), target=str(tmp_path / 'College' / 'DBMS' / 'Lectures' / name),
                  category='College', rule_name='Intelligence', status=OperationStatus.VERIFIED_AND_MOVED,
                  size=2048, hash='a' * 64, confidence='CONFIRMED', confidence_score=.92,
                  evidence=['Document Title: Normalization', 'Origin Domain: canvas.example.edu'],
                  cluster_name='DBMS Course', cluster_id='course-1')
    values.update(kwargs)
    return FileOperationRecord(**values)


def test_enhanced_report_hierarchy_clusters_and_audit(tmp_path):
    organizer = create_organizer(tmp_path)
    records = [audit_record(tmp_path), audit_record(tmp_path, 'lecture2.pdf', status=OperationStatus.COLLISION_RESOLVED)]
    result = OrganizeResult(records, success_count=1, collision_count=1, cancelled=True, warnings=['One file unavailable'])
    report = Path(organizer.generate_report(str(tmp_path), result)).read_text()
    assert '## College/DBMS/Lectures' in report
    assert 'CONFIRMED (92%)' in report
    assert '**Evidence:**' in report and 'Document Title: Normalization' in report
    assert 'Origin Domain: canvas' in report
    assert '## Clusters' in report and 'DBMS Course (2 files)' in report
    assert '(#file-1)' in report and '<a id="file-1"></a>' in report
    assert '**Cluster ID:** ` course-1 `' in report
    assert '**Rule:** Intelligence' in report
    assert 'a' * 64 in report and '2.00 KB' in report
    assert '**Cancelled:** Yes' in report and 'One file unavailable' in report
    assert report.count('### lecture') == 2
    assert 'http://' not in report and 'https://' not in report


@pytest.mark.parametrize('status', list(OperationStatus))
def test_report_all_statuses_and_action_semantics(tmp_path, status):
    record = audit_record(tmp_path, status=status, error='failure reason' if status == OperationStatus.FAILED else '')
    report = Path(create_organizer(tmp_path).generate_report(str(tmp_path), OrganizeResult([record]))).read_text()
    assert status.value in report
    assert record.source in report and record.target in report
    assert 'CONFIRMED (92%)' in report
    assert 'file:///' in report
    if status in {OperationStatus.FAILED, OperationStatus.SKIPPED}:
        assert 'Intended Destination' in report and '[Open Source]' in report
        assert '[Open File]' not in report
    elif status == OperationStatus.DUPLICATE:
        assert '[Open Existing Destination]' in report
    else:
        assert '**Final Location:**' in report and '[Open File]' in report


def test_report_legacy_records_and_empty_result(tmp_path):
    organizer = create_organizer(tmp_path)
    record = FileOperationRecord(str(tmp_path / 'a'), str(tmp_path / 'Dest' / 'a'), 'Legacy', 'Rule', OperationStatus.SKIPPED)
    assert record.evidence == [] and record.confidence_score is None
    report_path = Path(organizer.generate_report(str(tmp_path), OrganizeResult([record])))
    report = report_path.read_text()
    assert '` CONFIRMED `' in report and 'No evidence recorded.' in report
    assert '## Clusters' not in report
    organizer.generate_report(str(tmp_path), OrganizeResult([]))
    assert '**Total Files Processed:** 0' in report_path.read_text()
    assert 'Legacy' not in report_path.read_text()


def test_report_escapes_untrusted_markdown_and_links(tmp_path):
    name = 'Résumé [x](y) #%.pdf'
    record = audit_record(tmp_path, name, evidence=['![remote](https://bad.example/x)\n# forged', '<script>alert(1)</script>', '`code`'],
                          cluster_name='<img src="https://bad.example">', category='A[B]')
    report = Path(create_organizer(tmp_path).generate_report(str(tmp_path), OrganizeResult([record]))).read_text()
    assert '![remote]' not in report and '\n# forged' not in report
    assert '<script>' not in report
    assert '` <img src="https://bad.example"> `' in report
    assert '&lt;script&gt;' in report
    assert '\\[x\\]\\(y\\)' in report
    assert f'[Open File](<{Path(record.target).as_uri()}>)' in report
    assert '%C3%A9' in report and '%23%25.pdf' in report


def test_report_distinguishes_same_named_clusters(tmp_path):
    records = [audit_record(tmp_path), audit_record(tmp_path, 'two.pdf', cluster_id='course-2')]
    report = Path(create_organizer(tmp_path).generate_report(str(tmp_path), OrganizeResult(records))).read_text()
    assert report.count('### DBMS Course (1 files)') == 2
    assert 'course-1' in report and 'course-2' in report


@pytest.mark.parametrize('failure_point', ['fsync', 'replace'])
def test_atomic_report_failure_preserves_previous_and_cleans_temp(tmp_path, monkeypatch, failure_point):
    organizer = create_organizer(tmp_path)
    report_path = tmp_path / 'SmartSort_Arrangement.md'
    report_path.write_text('previous complete report')
    def fail(*args):
        raise OSError('disk error')
    monkeypatch.setattr(os, failure_point, fail)
    with pytest.raises(OSError, match='disk error'):
        organizer.generate_report(str(tmp_path), OrganizeResult([audit_record(tmp_path)]))
    assert report_path.read_text() == 'previous complete report'
    assert not list(tmp_path.glob('.SmartSort_Arrangement.*.tmp'))


def test_atomic_report_temp_is_sibling_and_legacy_symlink_is_ignored(tmp_path, monkeypatch):
    organizer = create_organizer(tmp_path)
    victim = tmp_path / 'unrelated.txt'
    victim.write_text('keep me')
    (tmp_path / 'SmartSort_Arrangement.md.tmp').symlink_to(victim)
    original_replace = os.replace
    seen = []
    def replace(source, destination):
        assert Path(source).parent == tmp_path
        assert os.stat(source).st_dev == os.stat(tmp_path).st_dev
        assert '**Total Files Processed:** 1' in Path(source).read_text()
        seen.append(source)
        original_replace(source, destination)
    monkeypatch.setattr(os, 'replace', replace)
    organizer.generate_report(str(tmp_path), OrganizeResult([audit_record(tmp_path)]))
    assert len(seen) == 1 and not Path(seen[0]).exists()
    assert victim.read_text() == 'keep me'
    assert organizer.scan(str(tmp_path)) == [str(victim)]


@pytest.mark.parametrize('score', [None, float('nan'), float('inf'), -1, 1.5])
def test_report_unknown_or_invalid_score_not_fabricated(tmp_path, score):
    record = audit_record(tmp_path, confidence_score=score)
    report = Path(create_organizer(tmp_path).generate_report(str(tmp_path), OrganizeResult([record]))).read_text()
    assert '` CONFIRMED `' in report and 'nan%' not in report


def test_report_code_spans_cannot_inject_markdown(tmp_path):
    record = audit_record(tmp_path, '` ![x](https:evil) `.pdf', cluster_id='` <b>injected</b> `')
    report = Path(create_organizer(tmp_path).generate_report(str(tmp_path), OrganizeResult([record]))).read_text()
    assert '`` ' + record.source + ' ``' in report
    assert '`` ` <b>injected</b> ` ``' in report


def test_cancelled_execution_records_only_processed_files(tmp_path):
    organizer = create_organizer(tmp_path)
    sources = [tmp_path / 'one.pdf', tmp_path / 'two.pdf']
    for source in sources:
        source.write_text('test')
    items = [OrganizePlanItem(str(source), str(tmp_path / 'Dest' / source.name), 'Dest', 'Rule', evidence=['Reviewed']) for source in sources]
    calls = iter([False, True])
    result = organizer.execute(OrganizePlan(items, str(tmp_path), 2, {'Dest': 2}), cancel_check=lambda: next(calls))
    assert result.cancelled and len(result.records) == 1
    assert result.records[0].evidence == ['Reviewed']
    assert sources[1].exists()


def test_atomic_report_partial_write_failure_keeps_previous(tmp_path, monkeypatch):
    organizer = create_organizer(tmp_path)
    report = tmp_path / 'SmartSort_Arrangement.md'
    report.write_text('previous')
    original_fdopen = os.fdopen
    class BrokenWriter:
        def __init__(self, *args, **kwargs):
            self.handle = original_fdopen(*args, **kwargs)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.handle.close()
        def write(self, content):
            self.handle.write(content[:20])
            raise OSError('partial write')
    monkeypatch.setattr(os, 'fdopen', BrokenWriter)
    with pytest.raises(OSError, match='partial write'):
        organizer.generate_report(str(tmp_path), OrganizeResult([audit_record(tmp_path)]))
    assert report.read_text() == 'previous'
    assert not list(tmp_path.glob('.SmartSort_Arrangement.*.tmp'))


@pytest.mark.parametrize("policy", ["rename", "overwrite"])
def test_reverse_nested_moves_and_duplicate_sources(tmp_path, policy):
    organizer = create_organizer(tmp_path, {"conflict_resolution": policy})
    target = tmp_path / "sorted/sample.pdf"
    target.parent.mkdir()
    target.write_bytes(b"original")
    sources = []
    for directory, content in [("one", b"original"), ("two", b"second"), ("three", b"third")]:
        source = tmp_path / directory / target.name
        source.parent.mkdir()
        source.write_bytes(content)
        sources.append(source)
    items = [OrganizePlanItem(str(src), str(target), "Docs", "Test") for src in sources]
    result = organizer.execute(OrganizePlan(items, str(tmp_path), 3, {}), capture_undo=True)
    assert result.error_count == 0 and result.duplicate_count == 1
    assert all(not src.exists() for src in sources)
    result.undo.complete()
    assert result.undo.reverse() == (3, [])
    assert [src.read_bytes() for src in sources] == [b"original", b"second", b"third"]
    assert list(target.parent.iterdir()) == [target]
    assert target.read_bytes() == b"original"


@pytest.mark.parametrize("conflict", ["occupied", "modified", "replaced", "protected", "symlink"])
def test_reverse_preserves_later_changes(tmp_path, conflict):
    organizer = create_organizer(tmp_path)
    src = tmp_path / "incoming/file.txt"
    dst = tmp_path / "sorted/file.txt"
    src.parent.mkdir()
    src.write_bytes(b"before")
    plan = OrganizePlan([OrganizePlanItem(str(src), str(dst), "Docs", "Test")], str(tmp_path), 1, {})
    result = organizer.execute(plan, capture_undo=True)
    if conflict == "occupied":
        src.write_bytes(b"new source")
    elif conflict == "modified":
        dst.write_bytes(b"edited")
    elif conflict == "replaced":
        dst.rename(dst.with_suffix(".old"))
        dst.write_bytes(b"before")
    elif conflict == "protected":
        (src.parent / ".smartsort-ignore").touch()
    else:
        src.parent.rename(tmp_path / "another")
        src.parent.symlink_to(tmp_path / "another")
    result.undo.complete()
    restored, errors = result.undo.reverse()
    assert restored == 0 and len(errors) == 1
    assert dst.read_bytes() == (b"edited" if conflict == "modified" else b"before")
    if conflict == "occupied":
        assert src.read_bytes() == b"new source"
    else:
        assert not src.exists()
