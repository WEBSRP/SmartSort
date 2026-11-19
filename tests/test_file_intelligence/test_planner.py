"""Phase 12: rule semantics, safe proposals and read-only filesystem checks."""

import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from src.core.file_intelligence import (
    ConfidenceLevel, EvidenceItem, FileContext, MultiSignalClassifier,
    OrganizationPlanner, OrganizationProposal, SignalType,
)
from src.rules.manager import RuleManager
from src.rules.rule import Rule


def context(name="notes.pdf", domain="College", categories=None, score=.9, level=ConfidenceLevel.CONFIRMED):
    stem, extension = os.path.splitext(name)
    ctx = FileContext("/incoming/" + name, name, stem, extension, "", 2048, 0, 0, 0, 0)
    ctx.classification_domain = domain
    ctx.subcategories = ["DBMS", "Lectures"] if categories is None else categories
    ctx.confidence_score = score; ctx.confidence = level
    ctx.evidence_list = [EvidenceItem(SignalType.DOCUMENT_TITLE, "Title supports College", .9, "metadata.title")]
    return ctx


def rule(destination="Custom/{extension}", priority=1, name="My rule", enabled=True, conditions=None):
    return Rule.from_dict(dict(id=str(priority), name=name, priority=priority, enabled=enabled,
                               destination=destination, conditions=[] if conditions is None else conditions))


def planner(*rules):
    return OrganizationPlanner(SimpleNamespace(rules=list(rules)), None)


def test_intelligent_hierarchy_and_context_update_only_on_success(tmp_path):
    ctx = context(); before = copy.deepcopy(ctx.to_dict())
    result = planner().plan_file(ctx, tmp_path)
    expected = str(tmp_path / "College/DBMS/Lectures/notes.pdf")
    assert isinstance(result, OrganizationProposal) and result.target_path == expected
    assert result.relative_target == "College/DBMS/Lectures/notes.pdf"
    assert result.hierarchy_segments == ["College", "DBMS", "Lectures"]
    assert result.domain == "College" and not result.is_rule_override and result.rule_name == ""
    assert result.source_path == ctx.path and result.confidence_score == .9
    assert result.confidence_level is ConfidenceLevel.CONFIRMED
    assert result.evidence == ctx.evidence_list and result.evidence is not ctx.evidence_list
    before["proposed_destination"] = expected
    assert ctx.to_dict() == before and not list(tmp_path.iterdir())


def test_rule_priority_enabled_state_and_actual_hierarchy(tmp_path):
    ctx = context()
    result = planner(rule("Ignored", 0, enabled=False), rule("Low", 8),
                     rule("Chosen/{extension}", 2, name="User label")).plan_file(ctx, tmp_path)
    assert result.relative_target == "Chosen/PDF/notes.pdf"
    assert result.is_rule_override and result.confidence_score == 1
    assert result.confidence_level is ConfidenceLevel.CONFIRMED
    assert result.domain == result.rule_name == "User label"
    assert result.hierarchy_segments == ["Chosen", "PDF"]
    assert len(result.evidence) == 1 and "Priority 2" in result.evidence[0].description


@pytest.mark.parametrize("destination,expected", [
    ("Custom/{filename}", "Custom/notes.pdf"),
    ("Custom/prefix_{filename}", "Custom/prefix_notes.pdf"),
    ("{extension}/{filename}/copy_{filename}", "PDF/notes.pdf/copy_notes.pdf"),
    (".", "notes.pdf"), ("Custom/./Nested//", "Custom/Nested/notes.pdf"),
])
def test_rule_expansion_preserves_existing_filename_semantics(tmp_path, destination, expected):
    result = planner(rule(destination)).plan_file(context(), tmp_path)
    assert result.relative_target == expected and result.target_path == str(tmp_path / expected)


def test_rule_can_override_unknown_or_invalid_classification(tmp_path):
    ctx = context(domain="../../bad", categories=["../../bad"], score=float("nan"))
    result = planner(rule("User/Route")).plan_file(ctx, tmp_path)
    assert result.relative_target == "User/Route/notes.pdf" and result.confidence_score == 1


def test_live_rule_changes_are_honored(tmp_path):
    instance = planner(rule("First")); ctx = context()
    assert instance.plan_file(ctx, tmp_path).relative_target == "First/notes.pdf"
    instance.rule_manager.rules = [rule("Replacement")]
    assert instance.plan_file(ctx, tmp_path).relative_target == "Replacement/notes.pdf"
    instance.rule_manager.rules[0].enabled = False
    assert instance.plan_file(ctx, tmp_path).relative_target.startswith("College/")


def test_real_rule_manager_and_size_conditions_need_no_source_stat(tmp_path, monkeypatch):
    config = SimpleNamespace(get=lambda key, default=None: [rule("Large", conditions=[
        {"type": "extension", "value": ".pdf"}, {"type": "size", "operator": ">=", "value": "1KB"}
    ]).to_dict()] if key == "rules" else default)
    manager = RuleManager(config)
    monkeypatch.setattr(os.path, "getsize", lambda *args: pytest.fail("Source size must come from context"))
    assert OrganizationPlanner(manager, config).plan_file(context(), tmp_path).relative_target == "Large/notes.pdf"


def test_rule_nonmatch_uses_intelligence_not_engine_others_fallback(tmp_path):
    instance = planner(rule("Ignored", conditions=[{"type": "extension", "value": ".png"}]))
    result = instance.plan_file(context(), tmp_path)
    assert result.domain == "College" and not result.is_rule_override


@pytest.mark.parametrize("score,level", [
    (0, ConfidenceLevel.UNKNOWN), (.349999, ConfidenceLevel.CONFIRMED),
    (.9, ConfidenceLevel.UNKNOWN), (.9, ConfidenceLevel.NOT_AVAILABLE),
])
def test_low_confidence_fallback_ignores_unusable_hierarchy(tmp_path, score, level):
    ctx = context(domain="../../bad", categories=["../bad"], score=score, level=level)
    result = planner().plan_file(ctx, tmp_path)
    assert result.relative_target == "Documents/notes.pdf" and result.domain == "Documents"
    assert result.confidence_level is ConfidenceLevel.UNKNOWN
    assert result.confidence_score == 0.0


def test_exact_uncertain_threshold_still_gets_hierarchy(tmp_path):
    ctx = context(score=.35, level=ConfidenceLevel.UNCERTAIN)
    assert planner().plan_file(ctx, tmp_path).relative_target.startswith("College/DBMS/")


@pytest.mark.parametrize("domain,categories", [
    ("Projects", ["SmartSort", "Source"]), ("Cybersecurity", ["Reports"]),
    ("Work", ["Invoices"]), ("Media", ["Audio"]), ("Archives", []), ("Others", []), ("College", []),
])
def test_supported_domain_paths(tmp_path, domain, categories):
    result = planner().plan_file(context(domain=domain, categories=categories), tmp_path)
    expected = ["Documents"] if domain == "Others" else [domain] + categories
    assert result.relative_target == "/".join(expected + ["notes.pdf"])


@pytest.mark.parametrize("component", ["..", ".", "../../outside", "/absolute", "nested/path", "x\\y", "", " ", "x\0y", "x\ny", "x\x7fy", "a" * 256])
def test_unsafe_hierarchy_rejected_before_mutation(tmp_path, component):
    ctx = context(categories=[component]); before = copy.deepcopy(ctx.to_dict())
    with pytest.raises(ValueError):
        planner().plan_file(ctx, tmp_path)
    assert ctx.to_dict() == before


@pytest.mark.parametrize("name", ["../notes.pdf", "/notes.pdf", "x\\notes.pdf", ".", "..", "", "x\0.pdf", "x\n.pdf"])
def test_unsafe_filename_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        planner().plan_file(context(name), tmp_path)


def test_filename_and_source_must_agree(tmp_path):
    ctx = context(); ctx.filename = "other.pdf"
    with pytest.raises(ValueError, match="basename"):
        planner().plan_file(ctx, tmp_path)


@pytest.mark.parametrize("destination", ["../outside", "Safe/../../outside", "Safe/../Other", "https://example.com", "C:/outside", "C:\\outside", "Custom\0bad", "Custom\nbad", "Custom/{filename}/"])
def test_unsafe_rule_destinations_rejected_without_intelligence_fallback(tmp_path, destination):
    ctx = context(); before = copy.deepcopy(ctx.to_dict())
    with pytest.raises(ValueError):
        planner(rule(destination)).plan_file(ctx, tmp_path)
    assert ctx.to_dict() == before


def test_absolute_rule_inside_root_allowed_outside_and_prefix_sibling_rejected(tmp_path):
    ctx = context()
    result = planner(rule(str(tmp_path / "User"))).plan_file(ctx, tmp_path)
    assert result.relative_target == "User/notes.pdf"
    for path in (str(tmp_path.parent / "outside"), str(tmp_path) + "_sibling"):
        with pytest.raises(ValueError, match="escapes"):
            planner(rule(path)).plan_file(ctx, tmp_path)


@pytest.mark.parametrize("final_component", [False, True])
def test_symlink_escape_in_parent_or_final_filename_is_rejected(tmp_path, final_component):
    root = tmp_path / "root"; root.mkdir(); outside = tmp_path / "outside"; outside.mkdir()
    if final_component:
        (root / "College/DBMS/Lectures").mkdir(parents=True)
        (root / "College/DBMS/Lectures/notes.pdf").symlink_to(outside / "notes.pdf")
    else:
        (root / "College").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        planner().plan_file(context(), root)


def test_dangling_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    (root / "College").symlink_to(tmp_path / "absent", target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        planner().plan_file(context(), root)


def test_root_symlink_and_internal_alias_have_consistent_canonical_fields(tmp_path):
    root = tmp_path / "real"; root.mkdir()
    alias = tmp_path / "alias"; alias.symlink_to(root, target_is_directory=True)
    (root / "Actual").mkdir(); (root / "College").symlink_to(root / "Actual", target_is_directory=True)
    result = planner().plan_file(context(), alias)
    assert result.target_path == str(root / "Actual/DBMS/Lectures/notes.pdf")
    assert result.relative_target == "Actual/DBMS/Lectures/notes.pdf"
    assert result.hierarchy_segments == ["Actual", "DBMS", "Lectures"] and result.domain == "College"


def test_symlink_loop_rejected(tmp_path):
    (tmp_path / "College").symlink_to("College", target_is_directory=True)
    with pytest.raises(ValueError):
        planner().plan_file(context(), tmp_path)


def test_non_directory_parent_rejected(tmp_path):
    (tmp_path / "College").write_text("file")
    with pytest.raises(ValueError):
        planner().plan_file(context(), tmp_path)


def test_existing_directory_or_special_target_rejected(tmp_path):
    folder = tmp_path / "College/DBMS/Lectures"; folder.mkdir(parents=True)
    target = folder / "notes.pdf"; target.mkdir()
    with pytest.raises(ValueError):
        planner().plan_file(context(), tmp_path)
    ctx = context("special.pdf"); os.mkfifo(folder / "special.pdf")
    with pytest.raises(ValueError):
        planner().plan_file(ctx, tmp_path)


def test_existing_regular_target_is_proposed_without_overwrite_or_collision_rename(tmp_path):
    folder = tmp_path / "College/DBMS/Lectures"; folder.mkdir(parents=True)
    target = folder / "notes.pdf"; target.write_bytes(b"unchanged")
    result = planner().plan_file(context(), tmp_path)
    assert result.target_path == str(target) and target.read_bytes() == b"unchanged"


def test_absent_and_relative_roots_are_supported_without_creation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = planner().plan_file(context(), "future/root")
    assert result.target_path == str(tmp_path / "future/root/College/DBMS/Lectures/notes.pdf")
    assert not (tmp_path / "future").exists()


@pytest.mark.parametrize("root", ["", "x\0", "x\n", b"/bytes"])
def test_invalid_roots_rejected(root):
    with pytest.raises(ValueError):
        planner().plan_file(context(), root)


def test_existing_file_cannot_be_root(tmp_path):
    target = tmp_path / "file";target.write_text("x")
    with pytest.raises(ValueError):
        planner().plan_file(context(), target)


@pytest.mark.parametrize("score", [True, -.1, 1.1, float("nan"), float("inf"), "0.9"])
def test_invalid_classification_score_rejected(tmp_path, score):
    with pytest.raises(ValueError):
        planner().plan_file(context(score=score), tmp_path)


def test_invalid_domain_level_size_depth_and_evidence_rejected(tmp_path):
    cases = [context(domain="UnknownRoot"), context(level="CONFIRMED"),
             context(categories=["x"] * 17)]
    bad = context();bad.size_bytes = None;cases.append(bad)
    bad = context();bad.evidence_list = ["fake"];cases.append(bad)
    bad = context();bad.evidence_list *= OrganizationPlanner.MAX_EVIDENCE + 1;cases.append(bad)
    for ctx in cases:
        with pytest.raises(ValueError):
            planner().plan_file(ctx, tmp_path)


def test_unicode_and_spaces_preserved_but_byte_length_limit_enforced(tmp_path):
    ctx = context("résumé 你好.pdf", domain="Work", categories=["Client α"])
    assert planner().plan_file(ctx, tmp_path).relative_target == "Work/Client α/résumé 你好.pdf"
    ctx.subcategories = ["你" * 86]
    with pytest.raises(ValueError):
        planner().plan_file(ctx, tmp_path)


def test_repeated_planning_and_json_roundtrip_do_not_share_lists(tmp_path):
    ctx = context(); instance = planner()
    first = instance.plan_file(ctx, tmp_path);second = instance.plan_file(ctx, tmp_path)
    assert first.to_dict() == second.to_dict()
    restored = OrganizationProposal.from_dict(json.loads(json.dumps(first.to_dict())))
    assert restored == first
    first.evidence.clear();first.hierarchy_segments.clear()
    assert restored.evidence and second.evidence and ctx.evidence_list and ctx.subcategories


@pytest.mark.parametrize("score", [True, float("nan"), float("inf"), -1, 2])
def test_proposal_rejects_invalid_scores(tmp_path, score):
    data = planner().plan_file(context(), tmp_path).to_dict();data["confidence_score"] = score
    with pytest.raises(ValueError):
        OrganizationProposal.from_dict(data)


def test_classifier_to_planner_uses_hierarchy_without_reclassifying(tmp_path):
    ctx = context("Lecture_3_DBMS.pdf");ctx.signals = None
    ctx.metadata.title = "DBMS lecture";ctx.metadata.text_preview = "Course lecture"
    MultiSignalClassifier().classify(ctx)
    result = planner().plan_file(ctx, tmp_path)
    assert result.relative_target == "College/DBMS/Lectures/Lecture_3_DBMS.pdf"
    assert result.evidence == ctx.evidence_list


def test_planner_has_no_content_reads_writes_network_or_config_access(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected I/O")
    class Config:
        def __getattribute__(self, name):
            return forbidden()
    instance = OrganizationPlanner(SimpleNamespace(rules=[]), Config())
    for obj, name in ((Path, "open"), (Path, "mkdir"), (os, "mkdir"), (os, "rename"),
                      (os, "replace"), (os, "unlink"), (socket, "socket")):
        monkeypatch.setattr(obj, name, forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    assert instance.plan_file(context(), tmp_path).domain == "College"


def test_import_headless_in_fresh_process():
    code = "import sys;from src.core.file_intelligence import OrganizationPlanner, OrganizationProposal;assert not any(k.startswith(('PyQt', 'PySide')) for k in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_permission_and_resolution_failures_do_not_update_context(tmp_path, monkeypatch):
    ctx = context();ctx.proposed_destination = "previous"
    def denied(*args, **kwargs):
        raise PermissionError("blocked")
    monkeypatch.setattr(os.path, "realpath", denied)
    with pytest.raises(ValueError, match="resolve"):
        planner().plan_file(ctx, tmp_path)
    assert ctx.proposed_destination == "previous"


def test_rule_evaluation_errors_are_not_silently_downgraded(tmp_path, monkeypatch):
    ctx = context();ctx.proposed_destination = "previous"
    def broken(*args, **kwargs):
        raise RuntimeError("rule failure")
    monkeypatch.setattr(Rule, "evaluate", broken)
    with pytest.raises(RuntimeError, match="rule failure"):
        planner(rule()).plan_file(ctx, tmp_path)
    assert ctx.proposed_destination == "previous"


@pytest.mark.parametrize("weight", [float("nan"), float("inf"), True, -1, 2])
def test_invalid_evidence_weights_fail_without_context_update(tmp_path, weight):
    ctx = context();ctx.proposed_destination = "previous"
    ctx.evidence_list = [EvidenceItem(SignalType.DOCUMENT_TITLE, "title", weight, "metadata.title")]
    with pytest.raises(ValueError):
        planner().plan_file(ctx, tmp_path)
    assert ctx.proposed_destination == "previous"


def test_rule_display_names_cannot_inject_multiline_explanations(tmp_path):
    result = planner(rule(name="My\nrule\x00")).plan_file(context(), tmp_path)
    assert result.rule_name == "My rule "
    assert "\n" not in result.evidence[0].description and "\0" not in result.evidence[0].description


def test_root_containment_is_component_aware_for_direct_boundary_api(tmp_path):
    instance = planner()
    with pytest.raises(ValueError):
        instance._validate_boundary(tmp_path / "allowed", tmp_path / "allowed_suffix/file.pdf")


def test_total_destination_length_budget(tmp_path):
    ctx = context(categories=["a" * 255] * 16)
    with pytest.raises(ValueError):
        planner().plan_file(ctx, tmp_path)
