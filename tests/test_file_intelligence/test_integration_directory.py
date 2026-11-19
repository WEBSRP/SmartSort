"""Phase 13 real batch workflows, isolated failures and transfer preconditions."""

import copy
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import zipfile

import pytest

from src.core.directory_organizer import (
    DirectoryOrganizer, OrganizePlan, OrganizePlanItem, DirectoryPreviewSummary,
    OperationStatus,
)
from src.core.file_intelligence import ExtractedMetadata, OriginInfo, ConfidenceLevel, FileContextBuilder
from src.core.file_intelligence.metadata import FileMetadataExtractor


class Config:
    def __init__(self, **changes):
        self.data = {"rules": [], "enable_origin_detection": False,
                     "enable_duplicate_detection": True, "conflict_resolution": "rename"}
        self.data.update(changes)

    def get(self, key, default=None):
        return self.data.get(key, default)


class Logger:
    def warning(self, *args):
        pass


def organizer(**changes):
    return DirectoryOrganizer(Config(**changes), Logger())


def rule(destination="Custom/{extension}", priority=1, **changes):
    value = {"id": str(priority), "name": "Custom", "enabled": True, "priority": priority,
             "destination": destination, "conditions": []}
    value.update(changes)
    return value


def academic(root):
    (root / "Lecture_1_DBMS.md").write_text("# DBMS Lecture\nCollege database course lecture notes")
    (root / "Lecture_2_DBMS.md").write_text("# DBMS Lecture\nCourse database lecture notes")
    (root / "Lecture_3.md").write_text("")


def tree_snapshot(root):
    return {str(path.relative_to(root)): (path.is_dir(), path.read_bytes() if path.is_file() else b"",
             path.stat().st_mtime_ns) for path in root.rglob("*")}


def test_real_academic_batch_inherits_missing_course_without_confirming_sparse_file(tmp_path):
    academic(tmp_path)
    summary = organizer().preview(str(tmp_path))
    assert summary.total_files == 3 and summary.cluster_count == 1 and not summary.warnings
    assert summary.category_counts == {"College": 3}
    assert all(Path(item.target_path).relative_to(tmp_path).parts[:3] == ("College", "DBMS", "Lectures")
               for item in summary.items)
    assert len({item.cluster_id for item in summary.items}) == 1
    sparse = next(i for i in summary.items if i.source_path.endswith("Lecture_3.md"))
    assert sparse.confidence != "CONFIRMED" and sparse.evidence and sparse.cluster_name == "DBMS_Lectures"


def test_real_archive_project_batch_and_sparse_report(tmp_path):
    (tmp_path / "SmartSort_Report.md").write_text("")
    with zipfile.ZipFile(tmp_path / "SmartSort_Source.zip", "w") as archive:
        archive.writestr("main.py", "def main(): pass")
        archive.writestr("SmartSort_Report.md", "project report")
    summary = organizer().preview(str(tmp_path))
    assert summary.cluster_count == 1 and summary.category_counts == {"Projects": 2}
    assert {str(Path(i.target_path).relative_to(tmp_path)) for i in summary.items} == {
        "Projects/SmartSort/Source/SmartSort_Source.zip",
        "Projects/SmartSort/Documentation/SmartSort_Report.md"}
    assert any("cluster" in e.lower() for i in summary.items for e in i.evidence)


@pytest.mark.parametrize("folder", ["Archives", "College", "Invoices", "Media"])
def test_parent_directory_hint_cannot_overrule_project_cluster(tmp_path, folder):
    root = tmp_path / folder;root.mkdir()
    (root / "SmartSort_Report.md").write_text("")
    with zipfile.ZipFile(root / "SmartSort_Source.zip", "w") as archive:
        archive.writestr("SmartSort_Report.md", "report")
    summary = organizer().preview(str(root))
    assert summary.cluster_count == 1 and summary.category_counts == {"Projects": 2}


def test_preview_does_not_mutate_selected_tree_or_configuration(tmp_path, monkeypatch):
    academic(tmp_path); instance = organizer(); before = tree_snapshot(tmp_path)
    config_before = copy.deepcopy(instance.config.data)
    def forbidden(*args, **kwargs):
        raise AssertionError("preview cannot transfer or write")
    monkeypatch.setattr(shutil, "copy2", forbidden)
    monkeypatch.setattr(os, "remove", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    summary = instance.preview(str(tmp_path))
    assert summary.total_files == 3 and tree_snapshot(tmp_path) == before
    assert instance.config.data == config_before


def test_all_configured_rules_precede_and_bypass_intelligence(tmp_path, monkeypatch):
    (tmp_path / "Lecture_1_DBMS.pdf").write_bytes(b"not a PDF")
    instance = organizer(rules=[rule("Pinned/{filename}")])
    def forbidden(*args, **kwargs):
        raise AssertionError("matched policies need no profiling")
    monkeypatch.setattr(instance.origin_detector, "detect_origin", forbidden)
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", forbidden)
    monkeypatch.setattr(instance.relationship_engine, "cluster_files", forbidden)
    summary = instance.preview(str(tmp_path))
    assert summary.total_files == 1 and summary.cluster_count == 0 and not summary.warnings
    item = summary.items[0]
    assert item.target_path == str(tmp_path / "Pinned/Lecture_1_DBMS.pdf")
    assert item.rule_name == "Custom" and item.confidence == "CONFIRMED" and item.confidence_score == 1


def test_priority_disabled_rules_and_no_match_preserve_semantics(tmp_path):
    academic(tmp_path)
    instance = organizer(rules=[rule("Disabled", 0, enabled=False), rule("Wrong", 2),
                                rule("Chosen/{extension}", 1)])
    result = instance.preview(str(tmp_path))
    assert all("Chosen/MD/" in item.target_path for item in result.items)
    instance.rule_manager.rules.clear()
    assert instance.preview(str(tmp_path)).category_counts == {"College": 3}


@pytest.mark.parametrize("status", ["FAILED", "TIMEOUT", "CORRUPTED", "ENCRYPTED", "PERMISSION_DENIED"])
def test_failed_extraction_uses_extension_fallback_without_losing_healthy_files(tmp_path, monkeypatch, status):
    (tmp_path / "broken.pdf").write_bytes(b"bad")
    (tmp_path / "invoice.md").write_text("# Invoice\nBilling invoice finance")
    instance = organizer(); original = instance.extractor_registry.extract_metadata
    def extract(path):
        return ExtractedMetadata(extraction_status=status) if path.endswith(".pdf") else original(path)
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", extract)
    result = instance.preview(str(tmp_path))
    assert result.total_files == 2
    broken = next(i for i in result.items if i.source_path.endswith("broken.pdf"))
    assert broken.category == "Documents" and broken.target_path == str(tmp_path / "Documents/broken.pdf")
    assert broken.confidence == "UNKNOWN" and broken.rule_name == "Fallback"
    assert result.category_counts["Work"] == 1 and result.warnings


def test_extractor_raised_exception_is_isolated(tmp_path, monkeypatch):
    (tmp_path / "opaque.txt").write_text("text")
    instance = organizer()
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", lambda path: (_ for _ in ()).throw(RuntimeError("private")))
    summary = instance.preview(str(tmp_path))
    assert summary.total_files == 1 and summary.items[0].rule_name == "Fallback"
    assert "private" not in repr(summary.warnings) and "private" not in repr(summary.items[0].evidence)


def test_origin_failure_retains_content_classification(tmp_path, monkeypatch):
    (tmp_path / "invoice.md").write_text("# Invoice\nBilling invoice finance")
    instance = organizer()
    monkeypatch.setattr(instance.origin_detector, "detect_origin", lambda *args: (_ for _ in ()).throw(RuntimeError("secret url")))
    summary = instance.preview(str(tmp_path))
    assert summary.category_counts == {"Work": 1} and "Origin unavailable" in summary.warnings[0]


def test_configured_origin_features_reach_classifier(tmp_path, monkeypatch):
    (tmp_path / "opaque.md").write_text("")
    instance = organizer(enable_origin_detection=True); calls = []
    def detect(path, size):
        calls.append((path, size));return OriginInfo(domain="github.com", confidence=ConfidenceLevel.CONFIRMED)
    monkeypatch.setattr(instance.origin_detector, "detect_origin", detect)
    summary = instance.preview(str(tmp_path))
    assert calls == [(str(tmp_path / "opaque.md"), 0)]
    assert summary.items[0].category == "Projects"


def test_disabled_origin_does_not_probe_xattrs_or_browser_profiles(tmp_path, monkeypatch):
    (tmp_path / "invoice.md").write_text("# Invoice\nFinance invoice")
    def forbidden(*args, **kwargs):
        raise AssertionError("disabled origin must not probe")
    monkeypatch.setattr(FileMetadataExtractor, "read_xattr", forbidden)
    instance = organizer(enable_origin_detection=False)
    summary = instance.preview(str(tmp_path))
    assert summary.category_counts == {"Work": 1} and not summary.warnings


def test_partial_and_unsupported_metadata_still_allow_filename_signals(tmp_path, monkeypatch):
    (tmp_path / "invoice.bin").write_bytes(b"opaque")
    instance = organizer()
    for status in ("PARTIAL", "UNSUPPORTED"):
        monkeypatch.setattr(instance.extractor_registry, "extract_metadata", lambda path: ExtractedMetadata(extraction_status=status))
        summary = instance.preview(str(tmp_path))
        assert summary.items[0].category == "Work" and summary.items[0].rule_name == "Intelligence"


def test_clustering_failure_keeps_individual_classification(tmp_path, monkeypatch):
    academic(tmp_path);instance = organizer()
    monkeypatch.setattr(instance.relationship_engine, "cluster_files", lambda values: (_ for _ in ()).throw(ValueError("bad graph")))
    result = instance.preview(str(tmp_path))
    assert result.total_files == 3 and result.cluster_count == 0
    assert any("Clustering unavailable" in warning for warning in result.warnings)
    assert sum(item.category == "College" for item in result.items) >= 2


def test_large_batch_retains_all_files_when_clustering_budget_is_exceeded(tmp_path, monkeypatch):
    academic(tmp_path);instance = organizer()
    monkeypatch.setattr(instance.relationship_engine, "MAX_FILES", 2)
    monkeypatch.setattr(instance.relationship_engine, "cluster_files", lambda values: pytest.fail("oversized graph"))
    result = instance.preview(str(tmp_path))
    assert result.total_files == 3 and result.cluster_count == 0
    assert any("exceeds relationship limit" in warning for warning in result.warnings)


def test_classification_failure_only_falls_back_affected_file(tmp_path, monkeypatch):
    academic(tmp_path);instance = organizer(); original = instance.classifier.classify
    def classify(ctx):
        if ctx.filename == "Lecture_1_DBMS.md":raise ValueError("bad classifier")
        original(ctx)
    monkeypatch.setattr(instance.classifier, "classify", classify)
    result = instance.preview(str(tmp_path))
    assert result.total_files == 3 and sum(i.rule_name == "Fallback" for i in result.items) == 1


def test_broken_rule_evaluation_does_not_trigger_an_alternative_move(tmp_path, monkeypatch):
    academic(tmp_path);instance = organizer()
    from src.rules.engine import RuleEngine
    monkeypatch.setattr(RuleEngine, "evaluate_file", lambda *args: (_ for _ in ()).throw(RuntimeError("broken policy")))
    result = instance.preview(str(tmp_path))
    assert result.total_files == 0 and len(result.warnings) == 3


def test_invalid_winning_destination_is_excluded_not_reclassified(tmp_path):
    academic(tmp_path)
    result = organizer(rules=[rule("../../outside")]).preview(str(tmp_path))
    assert result.total_files == 0 and len(result.warnings) == 3


def test_plan_revalidates_manual_sources_exclusions_duplicates_and_order(tmp_path):
    academic(tmp_path);(tmp_path / ".hidden.md").write_text("private")
    (tmp_path / "pending.part").write_text("partial")
    (tmp_path / "SmartSort_Arrangement.md").write_text("report")
    (tmp_path / "link.md").symlink_to(tmp_path / "Lecture_1_DBMS.md")
    instance = organizer();files = instance.scan(str(tmp_path))
    first = instance.plan(str(tmp_path), files)
    second = instance.plan(str(tmp_path), list(reversed(files)) + files + [str(tmp_path / ".hidden.md"),
        str(tmp_path / "pending.part"), str(tmp_path / "SmartSort_Arrangement.md"), str(tmp_path / "link.md"),
        str(tmp_path / "missing.md")])
    assert first.items == second.items and first.cluster_count == second.cluster_count
    assert len(second.warnings) == 5


def test_plan_rejects_external_source_before_content_reads(tmp_path, monkeypatch):
    root = tmp_path / "root";root.mkdir();external = tmp_path / "outside.md";external.write_text("private")
    instance = organizer()
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", lambda path: pytest.fail("external read"))
    assert instance.plan(str(root), [str(external)]).total_files == 0


def test_symlinked_protected_root_cannot_bypass_scan_or_plan(tmp_path):
    alias = tmp_path / "alias";alias.symlink_to("/etc", target_is_directory=True)
    instance = organizer()
    with pytest.raises(ValueError, match="protected"):
        instance.scan(str(alias))
    with pytest.raises(ValueError, match="protected"):
        instance.plan(str(alias), [])


def test_source_changed_during_profiling_is_not_planned(tmp_path, monkeypatch):
    path = tmp_path / "invoice.md";path.write_text("# Invoice")
    instance = organizer();original = instance.extractor_registry.extract_metadata
    def mutate(source):
        value = original(source);path.write_text("Changed contents");return value
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", mutate)
    result = instance.preview(str(tmp_path))
    assert result.total_files == 0 and any("Planning rejected" in warning for warning in result.warnings)


def test_already_organized_files_are_noops(tmp_path):
    folder = tmp_path / "Work/Invoices";folder.mkdir(parents=True)
    (folder / "invoice.md").write_text("# Invoice\nFinance invoice")
    result = organizer().preview(str(tmp_path), recursive=True)
    assert result.total_files == 0 and not result.items and not result.warnings


def test_intelligent_plan_executes_existing_safe_transfer_and_report(tmp_path):
    academic(tmp_path);instance = organizer();before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    plan = instance.plan(str(tmp_path), instance.scan(str(tmp_path)))
    result = instance.execute(plan)
    assert result.success_count == 3 and result.error_count == 0
    for filename, content in before.items():
        assert not (tmp_path / filename).exists()
        assert (tmp_path / "College/DBMS/Lectures" / filename).read_bytes() == content
    report = instance.generate_report(str(tmp_path), result)
    assert Path(report).is_file() and "file:///" in Path(report).read_text()


@pytest.mark.parametrize("change", ["content", "replacement", "symlink"])
def test_stale_source_is_preserved_and_execution_continues(tmp_path, change):
    academic(tmp_path);instance = organizer();plan = instance.plan(str(tmp_path), instance.scan(str(tmp_path)))
    source = Path(plan.items[0].source_path)
    if change == "content":source.write_text("new content")
    elif change == "replacement":
        replacement = tmp_path / "replacement";replacement.write_text("new inode");os.replace(replacement, source)
    else:
        source.unlink();source.symlink_to(tmp_path / "Lecture_2_DBMS.md")
    result = instance.execute(plan)
    assert result.error_count == 1 and result.success_count == 2
    assert source.exists() or source.is_symlink()


def test_execution_rechecks_symlink_escape_after_progress_callback(tmp_path):
    root = tmp_path / "root";root.mkdir();academic(root)
    outside = tmp_path / "outside";outside.mkdir()
    instance = organizer();plan = instance.plan(str(root), instance.scan(str(root)))
    def progress(*args):
        if not (root / "College").exists():(root / "College").symlink_to(outside, target_is_directory=True)
    result = instance.execute(plan, progress_callback=progress)
    assert result.error_count == 3 and all(Path(i.source_path).exists() for i in plan.items)
    assert not list(outside.iterdir())


def test_manually_forged_outside_target_is_not_written(tmp_path):
    root = tmp_path / "root";root.mkdir();source = root / "file.md";source.write_text("keep")
    target = tmp_path / "outside.md"
    item = OrganizePlanItem(str(source), str(target), "Others", "Manual")
    result = organizer().execute(OrganizePlan([item], str(root), 1, {"Others": 1}))
    assert result.error_count == 1 and source.read_text() == "keep" and not target.exists()


def test_mkdir_failure_is_per_file_and_does_not_abort_batch(tmp_path, monkeypatch):
    (tmp_path / "invoice.md").write_text("# Invoice\nFinance billing")
    (tmp_path / "Lecture_DBMS.md").write_text("# DBMS Lecture\nCourse lecture")
    instance = organizer();plan = instance.plan(str(tmp_path), instance.scan(str(tmp_path)))
    original = os.makedirs
    def create(path, *args, **kwargs):
        if "College" in str(path):raise PermissionError("unwritable")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, "makedirs", create)
    result = instance.execute(plan)
    assert result.error_count == 1 and result.success_count == 1
    assert (tmp_path / "Lecture_DBMS.md").exists()


@pytest.mark.parametrize("policy,duplicate", [("rename", False), ("skip", False), ("rename", True)])
def test_intelligence_targets_retain_collision_and_duplicate_policies(tmp_path, policy, duplicate):
    source = tmp_path / "invoice.md";source.write_text("# Invoice\nFinance billing")
    folder = tmp_path / "Work/Invoices";folder.mkdir(parents=True)
    existing = folder / source.name;existing.write_bytes(source.read_bytes() if duplicate else b"old")
    instance = organizer(conflict_resolution=policy);plan = instance.plan(str(tmp_path), [str(source)])
    result = instance.execute(plan)
    if duplicate:
        assert result.duplicate_count == 1 and not source.exists()
    elif policy == "skip":
        assert result.skip_count == 1 and source.exists()
    else:
        assert result.collision_count == 1 and not source.exists() and (folder / "invoice_1.md").exists()
    assert existing.read_bytes() == (b"# Invoice\nFinance billing" if duplicate else b"old")


def test_cancellation_and_copy_failure_keep_remaining_sources(tmp_path, monkeypatch):
    academic(tmp_path);instance = organizer();plan = instance.plan(str(tmp_path), instance.scan(str(tmp_path)))
    event = threading.Event();event.set()
    result = instance.execute(plan, cancel_check=event.is_set)
    assert result.cancelled and not result.records and all(Path(i.source_path).exists() for i in plan.items)
    original = shutil.copy2
    def copy_file(src, dst):
        if "Lecture_1" in src:raise OSError("copy error")
        return original(src, dst)
    monkeypatch.setattr(shutil, "copy2", copy_file)
    result = instance.execute(plan)
    assert result.error_count == 1 and result.success_count == 2
    assert (tmp_path / "Lecture_1_DBMS.md").exists()


def test_new_dataclass_fields_preserve_existing_positional_constructors():
    item = OrganizePlanItem("source", "target", "category", "rule")
    assert item.confidence == "CONFIRMED" and item.evidence == [] and item.source_identity is None
    plan = OrganizePlan([item], "/root", 1, {"category": 1})
    summary = DirectoryPreviewSummary(1, {"category": 1}, [item])
    assert plan.cluster_count == summary.cluster_count == 0 and plan.warnings == summary.warnings == []
    assert plan.warnings is not summary.warnings


def test_import_remains_headless_in_fresh_process():
    code = "import sys;from src.core.directory_organizer import DirectoryOrganizer;assert not any(k.startswith(('PyQt','PySide')) for k in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_metadata_builder_failure_isolated_as_extension_fallback(tmp_path, monkeypatch):
    (tmp_path / "invoice.md").write_text("# Invoice")
    monkeypatch.setattr(FileContextBuilder, "build_initial_context",
                        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("metadata failure")))
    summary = organizer().preview(str(tmp_path))
    assert summary.total_files == 1 and summary.items[0].rule_name == "Fallback"


def test_ingestion_path_swap_does_not_reach_content_extractor(tmp_path, monkeypatch):
    (tmp_path / "invoice.md").write_text("# Invoice")
    original = FileContextBuilder.build_initial_context
    def swapped(*args, **kwargs):
        ctx = original(*args, **kwargs);ctx.path = "/outside/private.md";return ctx
    monkeypatch.setattr(FileContextBuilder, "build_initial_context", swapped)
    instance = organizer()
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", lambda *args: pytest.fail("swapped source read"))
    summary = instance.preview(str(tmp_path))
    assert summary.total_files == 1 and summary.items[0].rule_name == "Fallback"
    assert summary.items[0].source_path == str(tmp_path / "invoice.md")


def test_rule_changes_during_batch_apply_to_next_batch_not_current_one(tmp_path, monkeypatch):
    (tmp_path / "invoice.md").write_text("# Invoice\nFinance invoice")
    instance = organizer();original = instance.extractor_registry.extract_metadata
    from src.rules.rule import Rule
    def change_policy(path):
        instance.rule_manager.rules = [Rule.from_dict(rule("Later"))]
        return original(path)
    monkeypatch.setattr(instance.extractor_registry, "extract_metadata", change_policy)
    assert instance.preview(str(tmp_path)).items[0].category == "Work"
    assert instance.preview(str(tmp_path)).items[0].target_path == str(tmp_path / "Later/invoice.md")


def test_empty_batch_defaults_and_file_read_hash_deferral(tmp_path, monkeypatch):
    instance = organizer();empty = instance.preview(str(tmp_path))
    assert empty.total_files == empty.cluster_count == 0 and not empty.warnings
    (tmp_path / "invoice.md").write_text("# Invoice\nFinance invoice")
    from src.utils.file_utils import FileUtils
    monkeypatch.setattr(FileUtils, "calculate_sha256", lambda *args: pytest.fail("hash deferred until execution"))
    assert instance.preview(str(tmp_path)).total_files == 1
