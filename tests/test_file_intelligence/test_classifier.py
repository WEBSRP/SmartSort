"""Phase 11 classification contracts, adversarial evidence and phase boundaries."""

import copy
import itertools
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from src.core.file_intelligence import (
    ConfidenceLevel, EvidenceItem, FileContext, MultiSignalClassifier, OriginInfo,
    RelationshipEngine, Signal, SignalExtractor, SignalSet, SignalType,
)
from src.core.file_intelligence.signals import BASE_WEIGHTS


def file(name="random.bin", title=None, content="", origin="", toc=()):
    stem, ext = os.path.splitext(name)
    ctx = FileContext("/data/" + name, name, stem, ext, "", 100, 1700000000, 0, 0, 0)
    ctx.metadata.title = title
    ctx.metadata.text_preview = content
    ctx.metadata.toc_entries = list(toc)
    ctx.origin = OriginInfo(domain=origin)
    return ctx


def record(token, kind, weight=None, source="test"):
    return Signal(token, kind, BASE_WEIGHTS.get(kind, .30) if weight is None else weight, source)


def with_signals(*records):
    ctx = file()
    ctx.signals = SignalSet({s.token for s in records}, list(records))
    return ctx


@pytest.mark.parametrize("name,title,content,origin,toc,domain,hierarchy", [
    ("Lecture_3_DBMS.zip", "DBMS Lectures", "DBMS lectures", "canvas.stanford.edu",
     ["Lecture_1_DBMS.pdf"], "College", ["DBMS", "Lectures"]),
    ("SmartSort_Source.zip", "SmartSort source code", "Python repository source", "github.com",
     ["SmartSort/main.py"], "Projects", ["SmartSort", "Source"]),
    ("nmap_scan.xml", "Nmap scan report", "Nmap vulnerability scan", "", [], "Cybersecurity", ["Reports"]),
    ("invoice_123.pdf", "Client invoice", "Billing invoice finance", "", [], "Work", ["Invoices"]),
    ("podcast.mp3", "Podcast audio", "Podcast soundtrack", "", [], "Media", ["Audio"]),
])
def test_corroborated_domains(name, title, content, origin, toc, domain, hierarchy):
    ctx = file(name, title, content, origin, toc)
    assert MultiSignalClassifier().classify(ctx) is None
    assert ctx.classification_domain == domain
    assert ctx.subcategories == hierarchy
    assert ctx.confidence is ConfidenceLevel.CONFIRMED
    assert .85 <= ctx.confidence_score <= 1
    assert ctx.evidence_list and all(isinstance(e, EvidenceItem) for e in ctx.evidence_list)


def test_empty_missing_and_opaque_signals_default_unknown():
    for signals in (None, {"old": "placeholder"}, SignalSet(), SignalSet({"invoice"}, [], {"Work": 1})):
        ctx = file(); ctx.signals = signals; ctx.metadata = None; ctx.origin = None
        MultiSignalClassifier().classify(ctx)
        assert ctx.classification_domain == "Others"
        assert ctx.confidence is ConfidenceLevel.UNKNOWN
        assert ctx.confidence_score == 0 and not ctx.subcategories and not ctx.evidence_list


def test_generic_archive_evidence_is_probable_not_confirmed():
    ctx = file("archive_bundle.zip", "Archive", "Archive")
    MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == "Archives" and ctx.subcategories == []
    assert ctx.confidence is ConfidenceLevel.PROBABLE
    assert ctx.confidence_score == pytest.approx(.7 * 1.15)


@pytest.mark.parametrize("name", ["random.zip", "untitled.pdf", "file.png", "unknown.py"])
def test_extension_only_never_becomes_semantic_certainty(name):
    ctx = file(name); MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == "Others" and ctx.confidence is ConfidenceLevel.UNKNOWN
    assert ctx.confidence_score < .35 and not ctx.subcategories


def test_exact_available_channel_weighted_scores_and_rollups():
    ctx = with_signals(record("invoice", SignalType.DOCUMENT_TITLE),
                       record("nmap", SignalType.FILENAME_TOKEN))
    scores = MultiSignalClassifier().evaluate_domain_scores(ctx)
    assert scores["Work"] == pytest.approx(.25 / .40 * .90)
    assert scores["Cybersecurity"] == pytest.approx(.15 / .40 * .95)
    assert scores["Projects"] == 0
    assert set(scores) == set(MultiSignalClassifier.DOMAINS)
    assert all(0 <= score <= 1 for score in scores.values())


def test_relative_signal_weight_scales_channel_strength():
    ctx = with_signals(record("invoice", SignalType.DOCUMENT_TITLE, .45))
    assert MultiSignalClassifier().evaluate_domain_scores(ctx)["Work"] == pytest.approx(.45)


@pytest.mark.parametrize("score,count,level", [
    (.85, 2, ConfidenceLevel.CONFIRMED), (.849999, 2, ConfidenceLevel.PROBABLE),
    (.60, 2, ConfidenceLevel.PROBABLE), (.599999, 2, ConfidenceLevel.UNCERTAIN),
    (.35, 2, ConfidenceLevel.UNCERTAIN), (.349999, 2, ConfidenceLevel.UNKNOWN),
    (1, 1, ConfidenceLevel.PROBABLE), (.9, 3, ConfidenceLevel.CONFIRMED),
])
def test_confidence_thresholds_use_unrounded_scores(score, count, level):
    result, adjusted = MultiSignalClassifier._confidence(score, count)
    assert result is level
    assert 0 <= adjusted <= 1


def test_one_channel_cap_and_duplicate_evidence_invariance():
    ctx = with_signals(record("invoice", SignalType.FILENAME_TOKEN))
    classifier = MultiSignalClassifier(); classifier.classify(ctx)
    assert ctx.confidence is ConfidenceLevel.PROBABLE and ctx.confidence_score == .60
    before = ctx.to_dict()
    ctx.signals.weighted_signals *= 30
    classifier.classify(ctx)
    assert ctx.evidence_list == [EvidenceItem(SignalType.FILENAME_TOKEN,
        "Filename token 'invoice' supports Work", .9, "stem")]
    assert ctx.confidence_score == before["confidence_score"]


def test_heading_code_media_and_body_are_one_content_channel():
    ctx = with_signals(*(record("invoice", kind) for kind in (
        SignalType.CONTENT_KEYWORD, SignalType.DOCUMENT_HEADING,
        SignalType.CODE_SYNTAX, SignalType.MEDIA_METADATA)))
    MultiSignalClassifier().classify(ctx)
    assert ctx.confidence is ConfidenceLevel.PROBABLE
    assert ctx.confidence_score == .6 and len(ctx.evidence_list) == 1


def test_losing_channels_do_not_boost_winner():
    ctx = with_signals(record("invoice", SignalType.DOCUMENT_TITLE),
                       record("nmap", SignalType.CONTENT_KEYWORD),
                       record("nmap", SignalType.FILENAME_TOKEN))
    MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == "Cybersecurity"
    assert ctx.confidence is ConfidenceLevel.UNCERTAIN
    assert ctx.confidence_score < .60
    assert any("Work" in item.description for item in ctx.evidence_list)


def test_conflicting_near_tie_never_confirmed():
    ctx = with_signals(record("invoice", SignalType.DOCUMENT_TITLE),
                       record("nmap", SignalType.DOCUMENT_TITLE))
    MultiSignalClassifier().classify(ctx)
    assert ctx.confidence is ConfidenceLevel.UNCERTAIN
    assert ctx.confidence_score < .60


def test_weak_hints_do_not_dilute_or_explain_semantic_score():
    ctx = with_signals(record("invoice", SignalType.FILENAME_TOKEN),
                       record("archive", SignalType.EXTENSION_HINT),
                       record("security", SignalType.DIRECTORY_CONTEXT))
    MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == "Work"
    assert {e.signal_type for e in ctx.evidence_list} == {SignalType.FILENAME_TOKEN}


def test_many_weak_hints_stay_below_point_two():
    ctx = with_signals(*(record(t, SignalType.DIRECTORY_CONTEXT) for t in
        ("invoice", "finance", "legal", "receipt", "contract", "timesheet")))
    scores = MultiSignalClassifier().evaluate_domain_scores(ctx)
    assert max(scores.values()) <= .20


def test_origin_must_match_validated_context_not_token_or_url_path():
    ctx = with_signals(record("lms", SignalType.ORIGIN_DOMAIN))
    assert not any(MultiSignalClassifier().evaluate_domain_scores(ctx).values())
    ctx.origin.url = "https://example.com/lms?token=private"
    assert not any(MultiSignalClassifier().evaluate_domain_scores(ctx).values())
    ctx.origin.url = "https://canvas.example.edu/?secret=private"
    assert MultiSignalClassifier().evaluate_domain_scores(ctx)["College"] == pytest.approx(.95)


def test_cluster_is_not_independent_corroboration():
    ctx = with_signals(record("invoice", SignalType.FILENAME_TOKEN),
                       record("invoice", SignalType.CLUSTER_CONTEXT))
    ctx.cluster_id = "cluster-safe"
    MultiSignalClassifier().classify(ctx)
    assert ctx.confidence is ConfidenceLevel.PROBABLE and ctx.confidence_score == .6
    assert any(e.signal_type is SignalType.CLUSTER_CONTEXT for e in ctx.evidence_list)


def test_orphan_cluster_signal_is_ignored():
    ctx = with_signals(record("invoice", SignalType.CLUSTER_CONTEXT))
    MultiSignalClassifier().classify(ctx)
    assert ctx.confidence is ConfidenceLevel.UNKNOWN and not ctx.evidence_list


@pytest.mark.parametrize("name,title,domain,hierarchy", [
    ("Lecture_2_OS.pdf", "OS lecture", "College", ["OS", "Lectures"]),
    ("Machine_Learning_Assignment.pdf", "Machine learning assignment", "College", ["Machine_Learning", "Assignments"]),
    ("CS101_Lab.pdf", "Course lab", "College", ["CS101", "Labs"]),
    ("SmartSort_Report.pdf", "Project documentation", "Projects", ["SmartSort", "Documentation"]),
    ("PortfolioApp_Design.pdf", "Project design", "Projects", ["PortfolioApp", "Design"]),
    ("tool_CVE_2026.py", "Security exploit", "Cybersecurity", ["Exploits"]),
    ("capture.pcap", "Network capture", "Cybersecurity", ["Captures"]),
    ("nda.pdf", "Legal contract", "Work", ["Contracts"]),
    ("receipt.pdf", "Finance receipt", "Work", ["Receipts"]),
    ("screencast.mp4", "Video screencast", "Media", ["Videos"]),
])
def test_taxonomy_subcategories(name, title, domain, hierarchy):
    ctx = file(name, title); MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == domain and ctx.subcategories == hierarchy
    assert all(0 < len(p) <= 64 and "/" not in p and "\\" not in p and p not in (".", "..") for p in ctx.subcategories)


def test_idempotent_json_and_no_unrelated_field_mutations():
    ctx = file("SmartSort_Source.zip", "SmartSort source code", "Repository source", "github.com")
    ctx.proposed_destination = "/unchanged"; ctx.related_file_paths = ["/sibling"]
    SignalExtractor().extract_signals(ctx)
    preserved = copy.deepcopy(ctx.to_dict()); MultiSignalClassifier().classify(ctx)
    first = ctx.to_dict(); MultiSignalClassifier().classify(ctx)
    assert ctx.to_dict() == first
    loaded = FileContext.from_dict(json.loads(json.dumps(first)))
    MultiSignalClassifier().classify(loaded)
    assert loaded.to_dict() == first
    for key in preserved:
        if key not in {"classification_domain", "subcategories", "confidence", "confidence_score", "evidence_list"}:
            assert ctx.to_dict()[key] == preserved[key]


def test_evaluate_scores_does_not_mutate_even_missing_signals():
    ctx = file("invoice.pdf", "Invoice")
    before = copy.deepcopy(ctx.to_dict())
    MultiSignalClassifier().evaluate_domain_scores(ctx)
    assert ctx.to_dict() == before


def test_reclassification_clears_stale_evidence_and_categories():
    ctx = file("invoice.pdf", "Invoice"); MultiSignalClassifier().classify(ctx)
    ctx.stem = "opaque";ctx.extension = ".bin";ctx.filename = "opaque.bin";ctx.metadata.title = None
    ctx.signals = None; MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == "Others" and not ctx.subcategories and not ctx.evidence_list


def test_signal_order_determinism_and_no_affinity_prior_double_count():
    records = [record("invoice", SignalType.DOCUMENT_TITLE), record("nmap", SignalType.FILENAME_TOKEN),
               record("invoice", SignalType.CONTENT_KEYWORD)]
    outputs = []
    for permutation in itertools.permutations(records):
        ctx = with_signals(*permutation);ctx.signals.domain_affinities = {"Cybersecurity": 1}
        MultiSignalClassifier().classify(ctx)
        outputs.append((ctx.confidence_score, ctx.classification_domain, [e.to_dict() for e in ctx.evidence_list]))
    assert all(o == outputs[0] for o in outputs)


@pytest.mark.parametrize("token,source", [
    ("https://x.test/?secret=invoice", "bad\nsource"), ("invoice\x00", "source"),
    ("../invoice", "source"), ("invoice" * 100, "source"),
])
def test_unsafe_tokens_do_not_become_evidence(token, source):
    ctx = with_signals(record(token, SignalType.CONTENT_KEYWORD, source=source))
    MultiSignalClassifier().classify(ctx)
    assert ctx.confidence is ConfidenceLevel.UNKNOWN and not ctx.evidence_list


def test_untrusted_source_is_replaced_with_known_field_name():
    ctx = with_signals(record("invoice", SignalType.CONTENT_KEYWORD, source="/private/secret\n"))
    MultiSignalClassifier().classify(ctx)
    assert {e.source_field for e in ctx.evidence_list} == {"metadata.text_preview"}


def test_input_budget_rejected_before_mutation():
    ctx = with_signals(record("invoice", SignalType.FILENAME_TOKEN))
    ctx.signals.weighted_signals *= MultiSignalClassifier.MAX_SIGNALS + 1
    before = copy.deepcopy(ctx.to_dict())
    with pytest.raises(ValueError):
        MultiSignalClassifier().classify(ctx)
    assert ctx.to_dict() == before


def test_invalid_context_raises_clear_error():
    with pytest.raises(ValueError, match="FileContext"):
        MultiSignalClassifier().classify(None)


def test_no_files_network_or_config_access(monkeypatch):
    class Config:
        def __getattribute__(self, name):
            raise AssertionError("configuration must not be accessed")
    def forbidden(*args, **kwargs):
        raise AssertionError("I/O is not allowed")
    ctx = file("invoice.pdf", "Invoice")
    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    MultiSignalClassifier(Config()).classify(ctx)
    assert ctx.classification_domain == "Work"


def test_relationship_boost_does_not_accumulate_across_classification():
    contexts = [file(f"Lecture_{i}_DBMS.pdf", "DBMS lecture", "DBMS lecture") for i in range(2)]
    for ctx in contexts:
        SignalExtractor().extract_signals(ctx)
    engine = RelationshipEngine(); classifier = MultiSignalClassifier()
    engine.cluster_files(contexts)
    for ctx in contexts:
        classifier.classify(ctx)
    baseline = [c.to_dict() for c in contexts]
    for _ in range(3):
        engine.cluster_files(contexts)
        for ctx in contexts:
            classifier.classify(ctx)
        assert [c.to_dict() for c in contexts] == baseline


def test_fresh_process_import_has_no_qt_dependencies():
    code = "import sys; from src.core.file_intelligence import MultiSignalClassifier; assert not any(k.startswith(('PyQt', 'PySide')) for k in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("language", ["C", "C++", "Java", "Go", "Rust", "Shell", "SQL", "PHP", "TypeScript"])
def test_extracted_code_languages_have_context_specific_project_affinity(language):
    ctx = file("opaque.bin");ctx.metadata.code_language = language
    MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == "Projects" and ctx.subcategories == ["Source"]
    assert ctx.confidence is ConfidenceLevel.PROBABLE


def test_code_language_words_in_prose_do_not_become_code_votes():
    ctx = file("opaque.bin", "Go rust java shell")
    MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == "Others"


def test_raw_title_preserves_exploit_subtype_after_security_alias_fold():
    ctx = file("opaque.bin", "CVE exploit", "Security advisory")
    MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == "Cybersecurity" and ctx.subcategories == ["Exploits"]


def test_explicit_filename_subtype_precedes_incidental_title_mention():
    ctx = file("nmap_report.xml", "Security exploit scan report")
    MultiSignalClassifier().classify(ctx)
    assert ctx.subcategories == ["Reports"]


def test_weak_directory_words_do_not_determine_course_or_subtype():
    ctx = with_signals(record("course", SignalType.DOCUMENT_TITLE),
                       record("database", SignalType.DIRECTORY_CONTEXT),
                       record("lecture", SignalType.DIRECTORY_CONTEXT))
    MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == "College" and ctx.subcategories == []


def test_zero_weight_records_cannot_corroborate_or_choose_subtypes():
    ctx = with_signals(record("course", SignalType.DOCUMENT_TITLE),
                       record("database", SignalType.CONTENT_KEYWORD, 0),
                       record("lecture", SignalType.FILENAME_TOKEN, 0))
    MultiSignalClassifier().classify(ctx)
    assert ctx.confidence is ConfidenceLevel.PROBABLE and ctx.subcategories == []
    assert len(ctx.evidence_list) == 1


@pytest.mark.parametrize("name", ["../SmartSort_Source.zip", "foo/bar_Source.zip", ".._Source.zip", "☃_Source.zip"])
def test_untrusted_project_names_cannot_make_path_segments(name):
    ctx = file(name, "Project source code", "Repository source")
    MultiSignalClassifier().classify(ctx)
    assert ctx.classification_domain == "Projects" and ctx.subcategories == ["Source"]


def test_json_output_independent_of_python_hash_seed():
    code = '''
import json
from src.core.file_intelligence import *
c=FileContext('/data/invoice.pdf','invoice.pdf','invoice','.pdf','',1,0,0,0,0)
c.metadata.title='Invoice finance';c.metadata.text_preview='Legal invoice contract'
MultiSignalClassifier().classify(c)
print(json.dumps(c.to_dict(),sort_keys=True))
'''
    outputs = []
    for seed in ("1", "19"):
        result = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, PYTHONHASHSEED=seed),
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]
