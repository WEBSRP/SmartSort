"""Phase 1 tests for the FileContext data model.

All tests are pure Python — no Qt, no network, no real user data,
no timing dependencies, fully deterministic.
"""

import json
import pytest

from src.core.file_intelligence.context import (
    ConfidenceLevel,
    OriginSource,
    SignalType,
    EvidenceItem,
    OriginInfo,
    ExtractedMetadata,
    FileContext,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file_context(**overrides):
    """Create a FileContext with sensible defaults; override any field."""
    defaults = {
        "path": "/home/user/Downloads/report.pdf",
        "filename": "report.pdf",
        "stem": "report",
        "extension": ".pdf",
        "mime_type": "application/pdf",
        "size_bytes": 102400,
        "created_timestamp": 1700000000.0,
        "modified_timestamp": 1700000001.0,
        "inode": 123456,
        "device": 2049,
    }
    defaults.update(overrides)
    return FileContext(**defaults)


# ===================================================================
# Enum Tests
# ===================================================================

class TestConfidenceLevel:
    """Tests for the ConfidenceLevel enum."""

    def test_values(self):
        assert ConfidenceLevel.CONFIRMED.value == "CONFIRMED"
        assert ConfidenceLevel.PROBABLE.value == "PROBABLE"
        assert ConfidenceLevel.UNCERTAIN.value == "UNCERTAIN"
        assert ConfidenceLevel.UNKNOWN.value == "UNKNOWN"
        assert ConfidenceLevel.NOT_AVAILABLE.value == "NOT_AVAILABLE"

    def test_member_count(self):
        assert len(ConfidenceLevel) == 5

    def test_equality(self):
        assert ConfidenceLevel.CONFIRMED == ConfidenceLevel.CONFIRMED
        assert ConfidenceLevel.CONFIRMED != ConfidenceLevel.UNKNOWN

    def test_identity(self):
        assert ConfidenceLevel.CONFIRMED is ConfidenceLevel.CONFIRMED

    def test_membership(self):
        assert ConfidenceLevel("CONFIRMED") is ConfidenceLevel.CONFIRMED

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            ConfidenceLevel("INVALID")


class TestOriginSource:
    """Tests for the OriginSource enum."""

    def test_values(self):
        assert OriginSource.BROWSER_SQLITE.value == "BROWSER_SQLITE"
        assert OriginSource.EXTENDED_ATTRIBUTE.value == "EXTENDED_ATTRIBUTE"
        assert OriginSource.METADATA_HEADER.value == "METADATA_HEADER"
        assert OriginSource.PARENT_DIRECTORY.value == "PARENT_DIRECTORY"
        assert OriginSource.UNKNOWN.value == "UNKNOWN"

    def test_member_count(self):
        assert len(OriginSource) == 5

    def test_equality(self):
        assert OriginSource.UNKNOWN == OriginSource.UNKNOWN
        assert OriginSource.UNKNOWN != OriginSource.BROWSER_SQLITE


class TestSignalType:
    """Tests for the SignalType enum."""

    def test_values(self):
        expected = {
            "FILENAME_TOKEN", "DOCUMENT_TITLE", "DOCUMENT_HEADING",
            "CONTENT_KEYWORD", "ORIGIN_DOMAIN", "ARCHIVE_CONTENT",
            "CODE_SYNTAX", "MEDIA_METADATA", "EXIF_CAMERA",
            "DIRECTORY_CONTEXT", "CLUSTER_CONTEXT", "EXTENSION_HINT",
        }
        actual = {member.value for member in SignalType}
        assert actual == expected

    def test_member_count(self):
        assert len(SignalType) == 12

    def test_construction_from_value(self):
        assert SignalType("FILENAME_TOKEN") is SignalType.FILENAME_TOKEN


# ===================================================================
# EvidenceItem Tests
# ===================================================================

class TestEvidenceItem:
    """Tests for the EvidenceItem frozen dataclass."""

    def test_creation(self):
        item = EvidenceItem(
            signal_type=SignalType.FILENAME_TOKEN,
            description="Contains 'report' token",
            weight=0.8,
            source_field="filename",
        )
        assert item.signal_type is SignalType.FILENAME_TOKEN
        assert item.description == "Contains 'report' token"
        assert item.weight == 0.8
        assert item.source_field == "filename"

    def test_immutability(self):
        item = EvidenceItem(
            signal_type=SignalType.FILENAME_TOKEN,
            description="test",
            weight=0.5,
            source_field="filename",
        )
        with pytest.raises(AttributeError):
            item.weight = 0.9  # type: ignore[misc]
        with pytest.raises(AttributeError):
            item.description = "changed"  # type: ignore[misc]

    def test_equality(self):
        a = EvidenceItem(SignalType.CODE_SYNTAX, "py", 0.7, "extension")
        b = EvidenceItem(SignalType.CODE_SYNTAX, "py", 0.7, "extension")
        assert a == b

    def test_to_dict(self):
        item = EvidenceItem(
            signal_type=SignalType.DOCUMENT_TITLE,
            description="Title match",
            weight=0.9,
            source_field="metadata.title",
        )
        d = item.to_dict()
        assert d == {
            "signal_type": "DOCUMENT_TITLE",
            "description": "Title match",
            "weight": 0.9,
            "source_field": "metadata.title",
        }

    def test_from_dict(self):
        d = {
            "signal_type": "ORIGIN_DOMAIN",
            "description": "Domain match",
            "weight": 0.6,
            "source_field": "origin.domain",
        }
        item = EvidenceItem.from_dict(d)
        assert item.signal_type is SignalType.ORIGIN_DOMAIN
        assert item.weight == 0.6

    def test_round_trip(self):
        original = EvidenceItem(
            signal_type=SignalType.MEDIA_METADATA,
            description="Camera info",
            weight=0.3,
            source_field="metadata.exif_tags",
        )
        restored = EvidenceItem.from_dict(original.to_dict())
        assert restored == original


# ===================================================================
# OriginInfo Tests
# ===================================================================

class TestOriginInfo:
    """Tests for the OriginInfo dataclass."""

    def test_defaults(self):
        origin = OriginInfo()
        assert origin.url == ""
        assert origin.domain == ""
        assert origin.site_name == ""
        assert origin.source is OriginSource.UNKNOWN
        assert origin.confidence is ConfidenceLevel.UNKNOWN
        assert origin.evidence_detail == ""

    def test_custom_values(self):
        origin = OriginInfo(
            url="https://example.com/file.pdf",
            domain="example.com",
            site_name="Example",
            source=OriginSource.BROWSER_SQLITE,
            confidence=ConfidenceLevel.CONFIRMED,
            evidence_detail="Matched browser history entry",
        )
        assert origin.url == "https://example.com/file.pdf"
        assert origin.source is OriginSource.BROWSER_SQLITE

    def test_to_dict(self):
        origin = OriginInfo()
        d = origin.to_dict()
        assert d["source"] == "UNKNOWN"
        assert d["confidence"] == "UNKNOWN"
        assert d["url"] == ""

    def test_from_dict(self):
        d = {
            "url": "https://test.org",
            "domain": "test.org",
            "site_name": "Test",
            "source": "EXTENDED_ATTRIBUTE",
            "confidence": "PROBABLE",
            "evidence_detail": "xattr match",
        }
        origin = OriginInfo.from_dict(d)
        assert origin.source is OriginSource.EXTENDED_ATTRIBUTE
        assert origin.confidence is ConfidenceLevel.PROBABLE

    def test_from_dict_missing_keys(self):
        """Missing keys should fall back to safe defaults."""
        origin = OriginInfo.from_dict({})
        assert origin.url == ""
        assert origin.source is OriginSource.UNKNOWN

    def test_round_trip(self):
        original = OriginInfo(
            url="https://arxiv.org/paper.pdf",
            domain="arxiv.org",
            source=OriginSource.METADATA_HEADER,
            confidence=ConfidenceLevel.UNCERTAIN,
        )
        restored = OriginInfo.from_dict(original.to_dict())
        assert restored == original


# ===================================================================
# ExtractedMetadata Tests
# ===================================================================

class TestExtractedMetadata:
    """Tests for the ExtractedMetadata dataclass."""

    def test_defaults(self):
        meta = ExtractedMetadata()
        assert meta.title is None
        assert meta.author is None
        assert meta.subject is None
        assert meta.created_date is None
        assert meta.modified_date is None
        assert meta.keywords == []
        assert meta.headings == []
        assert meta.text_preview == ""
        assert meta.toc_entries == []
        assert meta.dimensions is None
        assert meta.duration_seconds is None
        assert meta.exif_tags == {}
        assert meta.code_language is None
        assert meta.code_symbols == []
        assert meta.extractor_name == "none"
        assert meta.extraction_status == "PENDING"
        assert meta.error_message == ""

    def test_optional_fields_none(self):
        """Optional fields should be None by default, not fabricated."""
        meta = ExtractedMetadata()
        assert meta.title is None
        assert meta.author is None
        assert meta.subject is None
        assert meta.dimensions is None
        assert meta.duration_seconds is None
        assert meta.code_language is None

    def test_custom_values(self):
        meta = ExtractedMetadata(
            title="Database Systems Lecture 3",
            author="Prof. Smith",
            subject="DBMS",
            keywords=["database", "normalization"],
            dimensions=(1920, 1080),
            extractor_name="pdf",
            extraction_status="COMPLETE",
        )
        assert meta.title == "Database Systems Lecture 3"
        assert meta.keywords == ["database", "normalization"]
        assert meta.dimensions == (1920, 1080)

    def test_dimensions_tuple_preserved(self):
        meta = ExtractedMetadata(dimensions=(800, 600))
        d = meta.to_dict()
        assert d["dimensions"] == [800, 600]  # JSON-safe list
        restored = ExtractedMetadata.from_dict(d)
        assert restored.dimensions == (800, 600)  # Tuple restored

    def test_empty_lists_independent(self):
        """Each instance must have independent list instances."""
        a = ExtractedMetadata()
        b = ExtractedMetadata()
        a.keywords.append("test")
        assert b.keywords == []  # Must not share the list

    def test_to_dict(self):
        meta = ExtractedMetadata(title="Test", exif_tags={"Make": "Canon"})
        d = meta.to_dict()
        assert d["title"] == "Test"
        assert d["exif_tags"] == {"Make": "Canon"}
        assert d["author"] is None

    def test_from_dict_missing_keys(self):
        meta = ExtractedMetadata.from_dict({})
        assert meta.title is None
        assert meta.keywords == []
        assert meta.extractor_name == "none"
        assert meta.extraction_status == "PENDING"

    def test_round_trip(self):
        original = ExtractedMetadata(
            title="Report",
            author="Alice",
            keywords=["finance", "Q3"],
            headings=["Summary", "Details"],
            text_preview="This is the first paragraph...",
            dimensions=(1024, 768),
            duration_seconds=120.5,
            exif_tags={"Make": "Nikon", "Model": "D3500"},
            code_language="python",
            code_symbols=["main", "parse_args"],
            toc_entries=["Chapter 1", "Chapter 2"],
            extractor_name="pdf",
            extraction_status="COMPLETE",
        )
        restored = ExtractedMetadata.from_dict(original.to_dict())
        assert restored == original


# ===================================================================
# FileContext Tests
# ===================================================================

class TestFileContextCreation:
    """Tests for FileContext construction and defaults."""

    def test_minimal_creation(self):
        ctx = _make_file_context()
        assert ctx.path == "/home/user/Downloads/report.pdf"
        assert ctx.filename == "report.pdf"
        assert ctx.stem == "report"
        assert ctx.extension == ".pdf"
        assert ctx.mime_type == "application/pdf"
        assert ctx.size_bytes == 102400

    def test_default_optional_fields(self):
        ctx = _make_file_context()
        assert ctx.sha256_hash is None
        assert ctx.signals is None
        assert ctx.cluster_id is None
        assert ctx.related_file_paths == []
        assert ctx.classification_domain == "Others"
        assert ctx.subcategories == []
        assert ctx.confidence is ConfidenceLevel.UNKNOWN
        assert ctx.confidence_score == 0.0
        assert ctx.evidence_list == []
        assert ctx.proposed_destination == ""

    def test_default_nested_metadata(self):
        ctx = _make_file_context()
        assert isinstance(ctx.metadata, ExtractedMetadata)
        assert ctx.metadata.title is None
        assert ctx.metadata.extractor_name == "none"

    def test_default_nested_origin(self):
        ctx = _make_file_context()
        assert isinstance(ctx.origin, OriginInfo)
        assert ctx.origin.url == ""
        assert ctx.origin.source is OriginSource.UNKNOWN

    def test_nested_instances_independent(self):
        """Each FileContext must have independent nested instances."""
        a = _make_file_context()
        b = _make_file_context()
        a.related_file_paths.append("/tmp/other.txt")
        assert b.related_file_paths == []
        a.metadata.keywords.append("test")
        assert b.metadata.keywords == []


class TestFileContextPathHandling:
    """Tests for path, filename, and extension edge cases."""

    def test_unicode_filename(self):
        ctx = _make_file_context(
            path="/home/user/文件夹/报告.pdf",
            filename="报告.pdf",
            stem="报告",
            extension=".pdf",
        )
        assert ctx.filename == "报告.pdf"
        assert ctx.stem == "报告"

    def test_spaces_in_path(self):
        ctx = _make_file_context(
            path="/home/user/My Documents/Final Report (v2).docx",
            filename="Final Report (v2).docx",
            stem="Final Report (v2)",
            extension=".docx",
        )
        assert ctx.filename == "Final Report (v2).docx"
        assert " " in ctx.path

    def test_multiple_extensions(self):
        ctx = _make_file_context(
            path="/data/archive.tar.gz",
            filename="archive.tar.gz",
            stem="archive.tar",
            extension=".gz",
        )
        assert ctx.extension == ".gz"
        assert ctx.stem == "archive.tar"

    def test_extension_with_leading_dot(self):
        ctx = _make_file_context(extension=".PDF")
        assert ctx.extension == ".PDF"

    def test_extension_lowercase(self):
        ctx = _make_file_context(extension=".pdf")
        assert ctx.extension == ".pdf"

    def test_empty_extension(self):
        ctx = _make_file_context(
            path="/home/user/Makefile",
            filename="Makefile",
            stem="Makefile",
            extension="",
            mime_type="application/octet-stream",
        )
        assert ctx.extension == ""
        assert ctx.stem == "Makefile"

    def test_dotfile(self):
        ctx = _make_file_context(
            path="/home/user/.bashrc",
            filename=".bashrc",
            stem=".bashrc",
            extension="",
        )
        assert ctx.filename == ".bashrc"

    def test_very_long_filename(self):
        long_name = "a" * 255 + ".txt"
        ctx = _make_file_context(filename=long_name, stem="a" * 255, extension=".txt")
        assert len(ctx.filename) == 259

    def test_special_characters_in_path(self):
        ctx = _make_file_context(
            path="/home/user/café & résumé #1.pdf",
            filename="café & résumé #1.pdf",
            stem="café & résumé #1",
        )
        assert "café" in ctx.filename


class TestFileContextEdgeCases:
    """Tests for size, timestamp, and MIME edge cases."""

    def test_unknown_mime(self):
        ctx = _make_file_context(mime_type="application/octet-stream")
        assert ctx.mime_type == "application/octet-stream"

    def test_empty_mime(self):
        ctx = _make_file_context(mime_type="")
        assert ctx.mime_type == ""

    def test_large_file_size(self):
        size = 10 * 1024 * 1024 * 1024  # 10 GB
        ctx = _make_file_context(size_bytes=size)
        assert ctx.size_bytes == 10737418240

    def test_zero_file_size(self):
        ctx = _make_file_context(size_bytes=0)
        assert ctx.size_bytes == 0

    def test_timestamps(self):
        ctx = _make_file_context(
            created_timestamp=1700000000.123,
            modified_timestamp=1700000001.456,
        )
        assert ctx.created_timestamp == 1700000000.123
        assert ctx.modified_timestamp == 1700000001.456

    def test_zero_timestamps(self):
        ctx = _make_file_context(created_timestamp=0.0, modified_timestamp=0.0)
        assert ctx.created_timestamp == 0.0

    def test_inode_and_device(self):
        ctx = _make_file_context(inode=999999, device=65025)
        assert ctx.inode == 999999
        assert ctx.device == 65025


class TestFileContextSerialization:
    """Tests for to_dict / from_dict serialization."""

    def test_to_dict_basic(self):
        ctx = _make_file_context()
        d = ctx.to_dict()
        assert d["path"] == "/home/user/Downloads/report.pdf"
        assert d["filename"] == "report.pdf"
        assert d["size_bytes"] == 102400
        assert d["confidence"] == "UNKNOWN"
        assert d["classification_domain"] == "Others"
        assert isinstance(d["metadata"], dict)
        assert isinstance(d["origin"], dict)

    def test_from_dict_basic(self):
        ctx = _make_file_context()
        d = ctx.to_dict()
        restored = FileContext.from_dict(d)
        assert restored.path == ctx.path
        assert restored.filename == ctx.filename
        assert restored.size_bytes == ctx.size_bytes
        assert restored.confidence is ConfidenceLevel.UNKNOWN

    def test_round_trip_minimal(self):
        original = _make_file_context()
        restored = FileContext.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_with_evidence(self):
        evidence = [
            EvidenceItem(SignalType.FILENAME_TOKEN, "report token", 0.8, "filename"),
            EvidenceItem(SignalType.DOCUMENT_TITLE, "title match", 0.9, "metadata.title"),
        ]
        original = _make_file_context(
            confidence=ConfidenceLevel.PROBABLE,
            confidence_score=0.75,
            evidence_list=evidence,
            classification_domain="College",
            subcategories=["DBMS", "Lectures"],
        )
        restored = FileContext.from_dict(original.to_dict())
        assert restored == original
        assert len(restored.evidence_list) == 2
        assert restored.evidence_list[0].signal_type is SignalType.FILENAME_TOKEN
        assert restored.classification_domain == "College"

    def test_round_trip_with_metadata(self):
        meta = ExtractedMetadata(
            title="Annual Report",
            author="Finance Team",
            keywords=["Q3", "revenue"],
            dimensions=(1920, 1080),
        )
        origin = OriginInfo(
            url="https://corp.example.com/report.pdf",
            domain="corp.example.com",
            source=OriginSource.BROWSER_SQLITE,
            confidence=ConfidenceLevel.CONFIRMED,
        )
        original = _make_file_context(metadata=meta, origin=origin)
        restored = FileContext.from_dict(original.to_dict())
        assert restored == original
        assert restored.metadata.title == "Annual Report"
        assert restored.metadata.dimensions == (1920, 1080)
        assert restored.origin.domain == "corp.example.com"

    def test_round_trip_unicode(self):
        original = _make_file_context(
            path="/home/user/文件夹/数据库_讲义.pdf",
            filename="数据库_讲义.pdf",
            stem="数据库_讲义",
        )
        restored = FileContext.from_dict(original.to_dict())
        assert restored == original

    def test_json_serializable(self):
        """to_dict output must be JSON-serializable."""
        ctx = _make_file_context(
            metadata=ExtractedMetadata(
                title="Test", dimensions=(100, 200),
                exif_tags={"Make": "Canon"},
            ),
            evidence_list=[
                EvidenceItem(SignalType.CODE_SYNTAX, "py", 0.5, "ext"),
            ],
        )
        json_str = json.dumps(ctx.to_dict())
        data = json.loads(json_str)
        restored = FileContext.from_dict(data)
        assert restored == ctx

    def test_from_dict_missing_optional_keys(self):
        """from_dict with only required keys should use safe defaults."""
        minimal = {
            "path": "/tmp/test.txt",
            "filename": "test.txt",
            "stem": "test",
            "extension": ".txt",
            "mime_type": "text/plain",
            "size_bytes": 42,
            "created_timestamp": 1000.0,
            "modified_timestamp": 1001.0,
            "inode": 1,
            "device": 1,
        }
        ctx = FileContext.from_dict(minimal)
        assert ctx.sha256_hash is None
        assert ctx.classification_domain == "Others"
        assert ctx.confidence is ConfidenceLevel.UNKNOWN
        assert ctx.evidence_list == []
        assert isinstance(ctx.metadata, ExtractedMetadata)
        assert isinstance(ctx.origin, OriginInfo)

    def test_from_dict_with_sha256(self):
        d = _make_file_context(
            sha256_hash="a" * 64
        ).to_dict()
        restored = FileContext.from_dict(d)
        assert restored.sha256_hash == "a" * 64

    def test_round_trip_large_file(self):
        original = _make_file_context(size_bytes=10 * 1024**3)
        restored = FileContext.from_dict(original.to_dict())
        assert restored.size_bytes == original.size_bytes


class TestFileContextEquality:
    """Tests for dataclass equality semantics."""

    def test_equal_instances(self):
        a = _make_file_context()
        b = _make_file_context()
        assert a == b

    def test_different_path(self):
        a = _make_file_context(path="/a/report.pdf")
        b = _make_file_context(path="/b/report.pdf")
        assert a != b

    def test_different_confidence(self):
        a = _make_file_context(confidence=ConfidenceLevel.UNKNOWN)
        b = _make_file_context(confidence=ConfidenceLevel.CONFIRMED)
        assert a != b

    def test_different_metadata(self):
        a = _make_file_context(metadata=ExtractedMetadata(title="A"))
        b = _make_file_context(metadata=ExtractedMetadata(title="B"))
        assert a != b


class TestFileContextMutation:
    """Tests for incremental population (mutable dataclass)."""

    def test_update_classification(self):
        ctx = _make_file_context()
        ctx.classification_domain = "College"
        ctx.subcategories = ["DBMS", "Lectures"]
        ctx.confidence = ConfidenceLevel.PROBABLE
        ctx.confidence_score = 0.72
        assert ctx.classification_domain == "College"
        assert ctx.confidence is ConfidenceLevel.PROBABLE

    def test_update_metadata(self):
        ctx = _make_file_context()
        ctx.metadata.title = "Lecture Notes"
        ctx.metadata.extraction_status = "COMPLETE"
        assert ctx.metadata.title == "Lecture Notes"

    def test_append_evidence(self):
        ctx = _make_file_context()
        item = EvidenceItem(SignalType.FILENAME_TOKEN, "token", 0.5, "stem")
        ctx.evidence_list.append(item)
        assert len(ctx.evidence_list) == 1

    def test_update_origin(self):
        ctx = _make_file_context()
        ctx.origin.url = "https://example.com/doc.pdf"
        ctx.origin.source = OriginSource.BROWSER_SQLITE
        ctx.origin.confidence = ConfidenceLevel.CONFIRMED
        assert ctx.origin.url == "https://example.com/doc.pdf"


# ===================================================================
# Import / Isolation Tests
# ===================================================================

class TestModuleIsolation:
    """Verify the module has zero Qt and no forbidden dependencies."""

    def test_no_qt_imports(self):
        """context.py must not import any Qt modules."""
        import src.core.file_intelligence.context as ctx_module
        import sys
        module_source = ctx_module.__file__
        with open(module_source, "r") as f:
            source = f.read()
        assert "PyQt" not in source
        assert "QApplication" not in source
        assert "QThread" not in source
        assert "QWidget" not in source

    def test_package_exports(self):
        """__init__.py must export all key classes."""
        import src.core.file_intelligence as fi
        assert hasattr(fi, "ConfidenceLevel")
        assert hasattr(fi, "OriginSource")
        assert hasattr(fi, "SignalType")
        assert hasattr(fi, "EvidenceItem")
        assert hasattr(fi, "OriginInfo")
        assert hasattr(fi, "ExtractedMetadata")
        assert hasattr(fi, "FileContext")
