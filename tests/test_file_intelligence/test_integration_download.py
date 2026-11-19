"""Phase 14: completed downloads, bounded extraction and preserved transfers."""

from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from src.organizer import FileOrganizer
from src.core.file_intelligence import (
    ConfidenceLevel, ExtractedMetadata, FileContextBuilder, OriginInfo, OrganizationPlanner,
)
from src.core.file_intelligence.extractors import ExtractorRegistry
from src.core.file_intelligence.extractors import isolated
from src.core.file_intelligence.metadata import FileMetadataExtractor
from src.utils.file_utils import FileUtils


class Config:
    def __init__(self, root, **changes):
        self.data = {"rules": [], "destination_base": str(root / "dest"),
                     "enable_origin_detection": False, "enable_notifications": False,
                     "smart_filename_cleanup": False, "enable_duplicate_detection": True,
                     "conflict_resolution": "rename", "large_file_threshold_gb": 2.5}
        self.data.update(changes)

    def get(self, key, default=None):
        return self.data.get(key, default)


class Logger:
    def info(self, *args): pass
    def warning(self, *args): pass
    def error(self, *args): pass
    def log_action(self, *args): pass
    def debug(self, *args): pass


def organizer(root, **changes):
    instance = FileOrganizer(Config(root, **changes), Logger())
    instance.notification_manager.send_success_notification = lambda path: False
    return instance


def rule(destination="Pinned/{extension}", **changes):
    value = {"name": "Pinned", "priority": 1, "enabled": True,
             "conditions": [], "destination": destination}
    value.update(changes)
    return value


def academic_pdf(title="DBMS Assignment"):
    stream = b'BT /F1 12 Tf 30 100 Td (DBMS assignment course notes) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
        b'<< /Title (' + title.encode() + b') >>']
    data = b'%PDF-1.4\n'; offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data)); data += str(index).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(data); data += b'xref\n0 7\n0000000000 65535 f \n'
    for offset in offsets[1:]:data += f'{offset:010} 00000 n \n'.encode()
    return data + b'trailer\n<< /Size 7 /Root 1 0 R /Info 6 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n'


def test_real_pdf_canvas_origin_and_read_only_proposal(tmp_path, monkeypatch):
    path = tmp_path / "Assignment_3_DBMS.pdf";path.write_bytes(academic_pdf())
    instance = organizer(tmp_path, enable_origin_detection=True); calls = []
    def detect(source, size):
        calls.append((source, size));return OriginInfo(domain="canvas.example.edu", url="https://canvas.example.edu/course?secret=private")
    monkeypatch.setattr(instance.origin_detector, "detect_origin", detect)
    config_before = copy.deepcopy(instance.config.data)
    result = instance.analyze_download(str(path))
    assert result.domain == "College" and result.relative_target == "College/DBMS/Assignments/Assignment_3_DBMS.pdf"
    assert result.confidence_level is ConfidenceLevel.CONFIRMED and result.evidence
    assert calls == [(str(path), path.stat().st_size)]
    assert path.read_bytes() == academic_pdf() and not (tmp_path / "dest").exists()
    assert "private" not in json.dumps(result.to_dict()) and instance.config.data == config_before


def test_real_github_archive_uses_project_hierarchy(tmp_path, monkeypatch):
    path = tmp_path / "SmartSort_Source.zip"
    with zipfile.ZipFile(path, "w") as archive:archive.writestr("project/main.py", "def main(): pass")
    instance = organizer(tmp_path, enable_origin_detection=True)
    monkeypatch.setattr(instance.origin_detector, "detect_origin", lambda *args: OriginInfo(domain="github.com"))
    result = instance.analyze_download(str(path))
    assert result.domain == "Projects" and result.relative_target == "Projects/SmartSort/Source/SmartSort_Source.zip"


def test_one_profile_per_process_file_and_no_stale_cache_for_path_reuse(tmp_path, monkeypatch):
    path = tmp_path / "invoice.md";path.write_text("# Invoice\nFinance invoice")
    instance = organizer(tmp_path);original = instance.analyze_download; calls = []
    def analyze(*args, **kwargs):
        calls.append(args[0]);return original(*args, **kwargs)
    monkeypatch.setattr(instance, "analyze_download", analyze)
    assert instance.process_file(str(path))[0] == "SUCCESS"
    assert calls == [str(path)] and getattr(instance._local, "request", None) is None
    path.write_text("# Lecture DBMS\nCollege course lecture")
    status, target = instance.process_file(str(path))
    assert status == "SUCCESS" and "College/DBMS/Lectures" in target and len(calls) == 2


def test_rules_bypass_all_profiling_and_preserve_full_target_template(tmp_path, monkeypatch):
    path = tmp_path / "opaque.pdf";path.write_bytes(b"corrupt")
    instance = organizer(tmp_path, rules=[rule("Pinned/{filename}")])
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", lambda *a, **k: pytest.fail("content probe"))
    monkeypatch.setattr(instance.origin_detector, "detect_origin", lambda *a: pytest.fail("history probe"))
    monkeypatch.setattr(FileContextBuilder, "build_initial_context", lambda *a, **k: pytest.fail("metadata probe"))
    proposal = instance.analyze_download(str(path))
    assert proposal.is_rule_override and proposal.confidence_score == 1
    assert proposal.relative_target == "Pinned/opaque.pdf" and proposal.domain == "Pinned"


def test_filename_override_is_target_only_and_preserves_original_origin_lookup(tmp_path, monkeypatch):
    path = tmp_path / "download.md";path.write_text("# DBMS Assignment\nCollege course assignment")
    instance = organizer(tmp_path, enable_origin_detection=True); calls = []
    monkeypatch.setattr(instance.origin_detector, "detect_origin", lambda p, s: calls.append(p) or OriginInfo(domain="canvas.example.edu"))
    proposal = instance.analyze_download(str(path), "Clean Assignment.md")
    assert proposal.source_path == str(path) and proposal.target_path.endswith("/Clean Assignment.md")
    assert proposal.domain == "College" and calls == [str(path)] and path.exists()


def test_cleanup_is_used_once_without_renaming_source_before_transfer(tmp_path, monkeypatch):
    path = tmp_path / "download.md";path.write_text("# Invoice\nFinance invoice")
    instance = organizer(tmp_path, smart_filename_cleanup=True); calls = []
    def clean(source):
        calls.append(source);assert path.exists();return "Clean Invoice.md"
    monkeypatch.setattr(instance.filename_cleanup, "generate_clean_name", clean)
    status, target = instance.process_file(str(path))
    assert status == "SUCCESS" and target.endswith("/Work/Invoices/Clean Invoice.md")
    assert calls == [str(path)] and not path.exists()


def test_rule_override_replaces_placeholders_not_matching_literal_path_names(tmp_path):
    path = tmp_path / "download.pdf";path.write_bytes(b"opaque")
    instance = organizer(tmp_path, rules=[rule("download.pdf/{filename}/copy_{filename}")])
    result = instance.analyze_download(str(path), "Clean.pdf")
    assert result.relative_target == "download.pdf/Clean.pdf/copy_Clean.pdf"


@pytest.mark.parametrize("name", ["../escape.md", "/escape.md", "x\\y.md", "", "x\0.md", "x\n.md", ".", ".."])
def test_unsafe_filename_overrides_are_rejected(tmp_path, name):
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    with pytest.raises(ValueError):organizer(tmp_path).analyze_download(str(path), name)
    assert path.exists() and not (tmp_path / "dest").exists()


@pytest.mark.parametrize("status", ["TIMEOUT", "FAILED", "CORRUPTED", "ENCRYPTED", "PERMISSION_DENIED"])
def test_failed_profiling_falls_back_without_false_certainty(tmp_path, monkeypatch, status):
    path = tmp_path / "Lecture_DBMS.pdf";path.write_bytes(b"opaque")
    instance = organizer(tmp_path)
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", lambda *a, **k: ExtractedMetadata(extraction_status=status))
    result = instance.analyze_download(str(path))
    assert result.relative_target == "Documents/Lecture_DBMS.pdf" and result.domain == "Documents"
    assert result.confidence_level is ConfidenceLevel.UNKNOWN and result.confidence_score == 0
    assert "fallback" in result.evidence[0].description


def test_origin_failure_retains_content_and_disabled_origin_avoids_xattrs(tmp_path, monkeypatch):
    path = tmp_path / "invoice.md";path.write_text("# Invoice\nFinance invoice")
    instance = organizer(tmp_path)
    monkeypatch.setattr(FileMetadataExtractor, "read_xattr", lambda *a: pytest.fail("origin disabled"))
    assert instance.analyze_download(str(path)).domain == "Work"
    monkeypatch.setattr(instance.origin_detector, "detect_origin", lambda *a: (_ for _ in ()).throw(OSError("secret")))
    assert instance.analyze_download(str(path)).domain == "Work"


def test_ingestion_and_classifier_errors_are_extension_fallback(tmp_path, monkeypatch):
    path = tmp_path / "invoice.md";path.write_text("# Invoice\nFinance invoice")
    instance = organizer(tmp_path)
    monkeypatch.setattr(instance.classifier, "classify", lambda *a: (_ for _ in ()).throw(RuntimeError("private")))
    assert instance.analyze_download(str(path)).domain == "Documents"
    monkeypatch.setattr(FileContextBuilder, "build_initial_context", lambda *a, **k: (_ for _ in ()).throw(OSError("private")))
    result = instance.analyze_download(str(path))
    assert result.domain == "Documents" and "private" not in repr(result)


def test_source_mutated_during_analysis_is_preserved(tmp_path, monkeypatch):
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    instance = organizer(tmp_path)
    def extract(*args, **kwargs):
        path.write_text("changed");return ExtractedMetadata(title="Invoice", extraction_status="SUCCESS")
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", extract)
    assert instance.process_file(str(path))[0] == "ERROR"
    assert path.read_text() == "changed" and not (tmp_path / "dest").exists()


@pytest.mark.parametrize("threshold", [.00001, 10000])
def test_large_video_approval_survives_intelligent_media_domain(tmp_path, threshold):
    path = tmp_path / "lecture.mp4";path.write_bytes(b"\0" * 20000)
    instance = organizer(tmp_path, large_file_threshold_gb=threshold)
    status, target = instance.process_file(str(path))
    assert status == "AWAIT_APPROVAL" and path.exists() and not Path(target).exists()
    assert instance.process_file(str(path), user_approved=True)[0] == "SUCCESS" and not path.exists()


@pytest.mark.parametrize("extension", [".mp4", ".3gp"])
def test_custom_nonvideo_category_does_not_bypass_video_approval(tmp_path, extension):
    path = tmp_path / ("lecture" + extension);path.write_bytes(b"\0" * 20000)
    instance = organizer(tmp_path, large_file_threshold_gb=10000, rules=[rule(name="College")])
    assert instance.process_file(str(path))[0] == "AWAIT_APPROVAL" and path.exists()


@pytest.mark.parametrize("policy,duplicate", [("rename", False), ("overwrite", False), ("skip", False), ("rename", True)])
def test_duplicates_collisions_and_notifications_preserve_existing_policies(tmp_path, policy, duplicate):
    path = tmp_path / "invoice.md";path.write_text("# Invoice\nFinance invoice")
    folder = tmp_path / "dest/Work/Invoices";folder.mkdir(parents=True)
    existing = folder / "invoice.md";existing.write_bytes(path.read_bytes() if duplicate else b"old")
    instance = organizer(tmp_path, conflict_resolution=policy);sent = []
    instance.notification_manager.send_success_notification = lambda p: sent.append(p)
    status, target = instance.process_file(str(path))
    if duplicate:
        assert status == "DUPLICATE" and not path.exists() and not sent
    elif policy == "skip":assert status == "SKIPPED" and path.exists() and not sent
    else:
        assert status == "SUCCESS" and not path.exists() and sent == [target]
        if policy == "rename":assert target.endswith("invoice_1.md") and existing.read_bytes() == b"old"


def test_notification_failure_does_not_undo_success(tmp_path):
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    instance = organizer(tmp_path)
    instance.notification_manager.send_success_notification = lambda *a: (_ for _ in ()).throw(RuntimeError("notification"))
    assert instance.process_file(str(path))[0] == "SUCCESS" and not path.exists()


def test_copy_failure_and_source_change_after_copy_preserve_original(tmp_path, monkeypatch):
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    instance = organizer(tmp_path)
    monkeypatch.setattr(FileUtils, "safe_copy", lambda *a: (False, "copy failed"))
    assert instance.process_file(str(path))[0] == "ERROR" and path.exists()
    def copy_and_mutate(src, dst):
        Path(dst).parent.mkdir(parents=True, exist_ok=True);Path(dst).write_bytes(Path(src).read_bytes())
        Path(src).write_text("updated source");return True, "hash"
    monkeypatch.setattr(FileUtils, "safe_copy", copy_and_mutate)
    assert instance.process_file(str(path))[0] == "ERROR" and path.read_text() == "updated source"


def test_unsafe_rule_and_symlink_escape_never_write(tmp_path):
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    assert organizer(tmp_path, rules=[rule("../outside")]).process_file(str(path))[0] == "ERROR"
    root = tmp_path / "dest";root.mkdir();outside = tmp_path / "outside";outside.mkdir()
    (root / "Work").symlink_to(outside, target_is_directory=True)
    assert organizer(tmp_path).process_file(str(path))[0] == "ERROR" and not list(outside.iterdir())
    assert path.exists()


def test_destination_changed_after_analysis_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    instance = organizer(tmp_path);original = instance.get_destination_path
    outside = tmp_path / "outside";outside.mkdir()
    def target(*args, **kwargs):
        value = original(*args, **kwargs)
        (tmp_path / "dest").mkdir();(tmp_path / "dest/Work").symlink_to(outside, target_is_directory=True)
        return value
    monkeypatch.setattr(instance, "get_destination_path", target)
    assert instance.process_file(str(path))[0] == "ERROR" and path.exists() and not list(outside.iterdir())


def test_invalid_source_types_and_missing_file_are_not_processed(tmp_path):
    instance = organizer(tmp_path)
    assert instance.process_file(str(tmp_path / "missing.md"))[0] == "SKIPPED"
    assert instance.process_file(str(tmp_path))[0] == "ERROR"
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    link = tmp_path / "link.md";link.symlink_to(path)
    assert instance.process_file(str(link))[0] == "ERROR" and path.exists()
    os.mkfifo(tmp_path / "pipe")
    assert instance.process_file(str(tmp_path / "pipe"))[0] == "ERROR"


def test_same_source_destination_is_noop_even_without_duplicate_detection(tmp_path):
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    instance = organizer(tmp_path, destination_base=str(tmp_path), enable_duplicate_detection=False, rules=[rule(".")])
    assert instance.process_file(str(path))[0] == "SKIPPED" and path.exists()


def test_concurrent_same_physical_download_is_not_processed_twice(tmp_path, monkeypatch):
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    instance = organizer(tmp_path);entered = threading.Event();release = threading.Event()
    def extract(*args, **kwargs):
        entered.set();assert release.wait(5)
        return ExtractedMetadata(title="Invoice", extraction_status="SUCCESS")
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", extract)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(instance.process_file, str(path));assert entered.wait(5)
        try:assert instance.process_file(str(path))[0] == "SKIPPED"
        finally:release.set()
        assert first.result(timeout=5)[0] == "SUCCESS"
    assert not instance._inflight


def test_concurrent_same_destination_preserves_both_downloads_and_thread_local_profiles(tmp_path, monkeypatch):
    paths = []
    for folder, text in (("first", "first invoice"), ("second", "second invoice")):
        root = tmp_path / folder;root.mkdir();path = root / "invoice.md";path.write_text(text);paths.append(path)
    instance = organizer(tmp_path);barrier = threading.Barrier(2)
    def extract(*args, **kwargs):
        barrier.wait(timeout=5);return ExtractedMetadata(title="Invoice", extraction_status="SUCCESS")
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", extract)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(instance.process_file, map(str, paths)))
    assert all(status == "SUCCESS" for status, _ in results)
    assert {Path(target).read_text() for _, target in results} == {"first invoice", "second invoice"}
    assert not any(p.exists() for p in paths) and not instance._inflight


def test_isolated_registry_real_text_json_and_default_dispatch_compatibility(tmp_path):
    path = tmp_path / "invoice.md";path.write_text("# Invoice\nFinance invoice")
    registry = ExtractorRegistry()
    direct = registry.extract_metadata(str(path));bounded = registry.extract_metadata(str(path), timeout_seconds=2)
    assert bounded.to_dict() == direct.to_dict() and bounded.extraction_status == "SUCCESS"


def test_actual_worker_timeout_kills_and_reaps_child(tmp_path, monkeypatch):
    pid_file = tmp_path / "pid"
    code = "import os,time;open(" + repr(str(pid_file)) + ",'w').write(str(os.getpid()));time.sleep(30)"
    monkeypatch.setattr(isolated, "_WORKER_CODE", code)
    started = time.monotonic();result = isolated.extract_metadata(str(tmp_path / "file"), .3)
    assert result.extraction_status == "TIMEOUT" and time.monotonic() - started < 1.5
    assert pid_file.exists()
    with pytest.raises(ProcessLookupError):os.kill(int(pid_file.read_text()), 0)


@pytest.mark.parametrize("code", ["print('not json')", "raise SystemExit(2)", "print('x'*2000000)"])
def test_worker_invalid_crashed_or_oversized_outputs_fall_back(tmp_path, monkeypatch, code):
    monkeypatch.setattr(isolated, "_WORKER_CODE", code)
    assert isolated.extract_metadata(str(tmp_path / "file"), 1).extraction_status == "FAILED"


def test_worker_slot_saturation_and_invalid_time_budgets_are_bounded(tmp_path, monkeypatch):
    slots = threading.BoundedSemaphore(1);slots.acquire();monkeypatch.setattr(isolated, "_SLOTS", slots)
    assert isolated.extract_metadata("unused", .01).extraction_status == "TIMEOUT"
    slots.release()
    for value in (0, -1, True, float("nan"), float("inf")):
        assert isolated.extract_metadata("unused", value).extraction_status == "TIMEOUT"


def test_clean_planner_override_keeps_source_basename_validation(tmp_path):
    source = tmp_path / "invoice.md";source.write_text("# Invoice")
    ctx = FileContextBuilder.build_initial_context(str(source), read_origin_xattrs=False)
    from types import SimpleNamespace
    planner = OrganizationPlanner(SimpleNamespace(rules=[]), None)
    result = planner.plan_file(ctx, tmp_path / "dest", override_filename="Clean.md")
    assert ctx.filename == "invoice.md" and result.target_path.endswith("/Clean.md")
    ctx.filename = "forged.md"
    with pytest.raises(ValueError):planner.plan_file(ctx, tmp_path / "dest", override_filename="Clean.md")


def test_import_is_qt_free_in_fresh_interpreter():
    code = "import sys;from src.organizer import FileOrganizer;assert not any(k.startswith(('PyQt','PySide')) for k in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_routing_policy_is_snapshotted_for_each_processing_request(tmp_path, monkeypatch):
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    instance = organizer(tmp_path)
    from src.rules.rule import Rule
    def extract(*args, **kwargs):
        instance.rule_manager.rules = [Rule.from_dict(rule("Later"))]
        return ExtractedMetadata(title="Invoice", extraction_status="SUCCESS")
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", extract)
    status, target = instance.process_file(str(path))
    assert status == "SUCCESS" and "Work/Invoices" in target
    path.write_text("# Invoice")
    status, target = instance.process_file(str(path))
    assert status == "SUCCESS" and target == str(tmp_path / "dest/Later/invoice.md")
