"""Phase 3 tests for the text/Markdown extractor and extractor infrastructure.

All tests are pure Python — no Qt, no network, no real user data,
no timing dependencies, fully deterministic. Uses pytest tmp_path
fixtures for filesystem operations.
"""

import os
import json

import pytest

from src.core.file_intelligence.context import ExtractedMetadata
from src.core.file_intelligence.extractors.base import BaseExtractor, ExtractorRegistry
from src.core.file_intelligence.extractors.text import TextExtractor


# ===================================================================
# Helpers
# ===================================================================

def _write(path, content, mode="w", encoding="utf-8"):
    """Write content to *path* and return the path string."""
    if mode == "wb":
        path.write_bytes(content)
    else:
        path.write_text(content, encoding=encoding)
    return str(path)


# ===================================================================
# BaseExtractor Tests
# ===================================================================

class TestBaseExtractor:
    """Tests for the BaseExtractor abstract interface."""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseExtractor()  # type: ignore[abstract]

    def test_class_constants(self):
        assert BaseExtractor.MAX_TEXT_BYTES == 64 * 1024
        assert BaseExtractor.TIMEOUT_SECONDS == 3.0

    def test_subclass_must_implement(self):
        class IncompleteExtractor(BaseExtractor):
            pass

        with pytest.raises(TypeError):
            IncompleteExtractor()


# ===================================================================
# ExtractorRegistry Tests
# ===================================================================

class TestExtractorRegistry:
    """Tests for the ExtractorRegistry dispatcher."""

    def test_default_extractors_registered(self):
        registry = ExtractorRegistry()
        assert len(registry._extractors) >= 1

    def test_get_extractor_for_txt(self, tmp_path):
        registry = ExtractorRegistry()
        fpath = _write(tmp_path / "test.txt", "hello")
        ext = registry.get_extractor(fpath)
        assert ext is not None
        assert isinstance(ext, TextExtractor)

    def test_get_extractor_for_md(self, tmp_path):
        registry = ExtractorRegistry()
        fpath = _write(tmp_path / "README.md", "# Title")
        ext = registry.get_extractor(fpath)
        assert isinstance(ext, TextExtractor)

    def test_get_extractor_for_unsupported(self, tmp_path):
        registry = ExtractorRegistry()
        (tmp_path / "unknown.unsupported").write_bytes(b"opaque unrecognized format")
        ext = registry.get_extractor(str(tmp_path / "unknown.unsupported"))
        assert ext is None

    def test_extract_metadata_txt(self, tmp_path):
        registry = ExtractorRegistry()
        fpath = _write(tmp_path / "note.txt", "Important note content.")
        meta = registry.extract_metadata(fpath)
        assert isinstance(meta, ExtractedMetadata)
        assert meta.extraction_status == "SUCCESS"

    def test_extract_metadata_unsupported(self, tmp_path):
        (tmp_path / "unknown.unsupported").write_bytes(b"opaque unrecognized format")
        meta = ExtractorRegistry().extract_metadata(str(tmp_path / "unknown.unsupported"))
        assert meta.extraction_status == "UNSUPPORTED"
        assert meta.extractor_name == "none"

    def test_custom_extractor_registered(self, tmp_path):
        """Custom extractors can be appended to the registry."""

        class DummyExtractor(BaseExtractor):
            def can_extract(self, extension, mime_type):
                return extension == ".xyz"

            def extract(self, file_path, max_bytes=None):
                return ExtractedMetadata(
                    extractor_name="DummyExtractor",
                    extraction_status="SUCCESS",
                )

        registry = ExtractorRegistry()
        registry.register(DummyExtractor())
        (tmp_path / "data.xyz").write_bytes(b"data")
        ext = registry.get_extractor(str(tmp_path / "data.xyz"))
        assert isinstance(ext, DummyExtractor)

    def test_extract_metadata_failure_captured(self, tmp_path):
        """Extractor exceptions are captured in ExtractedMetadata."""

        class BrokenExtractor(BaseExtractor):
            def can_extract(self, extension, mime_type):
                return extension == ".brk"

            def extract(self, file_path, max_bytes=None):
                raise RuntimeError("Simulated crash")

        registry = ExtractorRegistry()
        registry.register(BrokenExtractor())
        (tmp_path / "file.brk").write_bytes(b"data")
        meta = registry.extract_metadata(str(tmp_path / "file.brk"))
        assert meta.extraction_status == "FAILED"
        assert "Simulated crash" in meta.error_message

    def test_dispatch_failure_captured(self, monkeypatch):
        registry = ExtractorRegistry()

        def broken_dispatch(file_path):
            raise OSError("Cannot inspect file type")

        monkeypatch.setattr(registry, "get_extractor", broken_dispatch)
        meta = registry.extract_metadata("unreadable.txt")
        assert meta.extraction_status == "FAILED"
        assert "Cannot inspect file type" in meta.error_message


# ===================================================================
# TextExtractor — can_extract Tests
# ===================================================================

class TestTextExtractorCanExtract:
    """Tests for TextExtractor.can_extract()."""

    @pytest.mark.parametrize("ext", [
        ".txt", ".md", ".markdown", ".rst", ".log", ".csv",
        ".tsv", ".json", ".yaml", ".yml", ".xml", ".html", ".htm",
    ])
    def test_supported_extensions(self, ext):
        extractor = TextExtractor()
        assert extractor.can_extract(ext, "text/plain") is True

    def test_case_insensitive(self):
        extractor = TextExtractor()
        assert extractor.can_extract(".TXT", "text/plain") is True
        assert extractor.can_extract(".Md", "text/markdown") is True

    @pytest.mark.parametrize("ext", [
        ".pdf", ".docx", ".pptx", ".xlsx", ".png", ".mp3", ".zip",
        ".py", ".java", ".c",
    ])
    def test_unsupported_extensions(self, ext):
        extractor = TextExtractor()
        assert extractor.can_extract(ext, "application/octet-stream") is False

    def test_supported_count(self):
        assert len(TextExtractor.SUPPORTED_EXTENSIONS) == 13


# ===================================================================
# TextExtractor — Plaintext Tests
# ===================================================================

class TestTextExtractorPlaintext:
    """Tests for plaintext (.txt) extraction."""

    def test_basic_txt(self, tmp_path):
        content = "Hello, World!\nThis is a test document.\nIt has multiple lines."
        fpath = _write(tmp_path / "note.txt", content)
        meta = TextExtractor().extract(fpath)

        assert meta.extraction_status == "SUCCESS"
        assert meta.extractor_name == "TextExtractor"
        assert meta.title == "Hello, World!"
        assert meta.text_preview == content
        assert isinstance(meta.keywords, list)

    def test_empty_file(self, tmp_path):
        fpath = _write(tmp_path / "empty.txt", "")
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        assert meta.title is None
        assert meta.text_preview == ""
        assert meta.keywords == []

    def test_whitespace_only(self, tmp_path):
        fpath = _write(tmp_path / "blank.txt", "   \n\n  \n")
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        # No non-empty line → no title
        assert meta.title is None

    def test_title_from_first_line(self, tmp_path):
        content = "Database Management Systems\n\nChapter 1: Introduction"
        fpath = _write(tmp_path / "lecture.txt", content)
        meta = TextExtractor().extract(fpath)
        assert meta.title == "Database Management Systems"

    def test_headings_empty_for_plaintext(self, tmp_path):
        content = "# Not treated as markdown heading in .txt"
        fpath = _write(tmp_path / "note.txt", content)
        meta = TextExtractor().extract(fpath)
        # .txt is NOT Markdown — headings should be empty
        assert meta.headings == []

    def test_text_preview_bounded(self, tmp_path):
        """text_preview is capped at 1024 characters."""
        content = "x" * 2000
        fpath = _write(tmp_path / "long.txt", content)
        meta = TextExtractor().extract(fpath)
        assert len(meta.text_preview) == 1024

    def test_keywords_extracted(self, tmp_path):
        content = "database database normalization query optimization SQL query"
        fpath = _write(tmp_path / "db.txt", content)
        meta = TextExtractor().extract(fpath)
        assert "database" in meta.keywords
        assert "query" in meta.keywords

    def test_stopwords_filtered(self, tmp_path):
        content = "the and or but if then is are was were have has"
        fpath = _write(tmp_path / "stopwords.txt", content)
        meta = TextExtractor().extract(fpath)
        # All stop words should be filtered out
        assert meta.keywords == []

    def test_keywords_top_20(self, tmp_path):
        # Create text with >20 unique words
        words = ["token" + chr(97 + i // 26) + chr(97 + i % 26) for i in range(30)]
        content = " ".join(words * 5)
        fpath = _write(tmp_path / "many.txt", content)
        meta = TextExtractor().extract(fpath)
        assert meta.keywords == words[:20]


# ===================================================================
# TextExtractor — Markdown Tests
# ===================================================================

class TestTextExtractorMarkdown:
    """Tests for Markdown (.md / .markdown) extraction."""

    def test_md_headings(self, tmp_path):
        content = "# Main Title\n\n## Section One\n\nText.\n\n### Subsection\n"
        fpath = _write(tmp_path / "readme.md", content)
        meta = TextExtractor().extract(fpath)

        assert meta.headings == ["Main Title", "Section One", "Subsection"]
        assert meta.title == "Main Title"

    def test_md_h1_only(self, tmp_path):
        content = "# Installation Guide\n\nInstall via pip."
        fpath = _write(tmp_path / "install.md", content)
        meta = TextExtractor().extract(fpath)
        assert meta.title == "Installation Guide"
        assert meta.headings == ["Installation Guide"]

    def test_md_no_h1(self, tmp_path):
        """If no headings, fall back to first non-empty line."""
        content = "Just some plain text in a .md file.\nSecond line."
        fpath = _write(tmp_path / "plain.md", content)
        meta = TextExtractor().extract(fpath)
        assert meta.title == "Just some plain text in a .md file."
        assert meta.headings == []

    def test_md_multiple_h1(self, tmp_path):
        content = "# First Title\n\nContent.\n\n# Second Title\n"
        fpath = _write(tmp_path / "multi.md", content)
        meta = TextExtractor().extract(fpath)
        assert meta.title == "First Title"
        assert len(meta.headings) == 2

    def test_h1_preferred_over_earlier_subheading(self, tmp_path):
        fpath = _write(tmp_path / "title.md", "## Preface\n# Document Title\n")
        meta = TextExtractor().extract(fpath)
        assert meta.title == "Document Title"
        assert meta.headings == ["Preface", "Document Title"]

    def test_no_h1_uses_first_nonempty_line(self, tmp_path):
        fpath = _write(tmp_path / "title.md", "\nIntroduction\n## Details\n")
        assert TextExtractor().extract(fpath).title == "Introduction"

    def test_markdown_title_bounded(self, tmp_path):
        fpath = _write(tmp_path / "title.md", "# " + "x" * 1000)
        assert TextExtractor().extract(fpath).title == "x" * 256

    def test_md_heading_levels(self, tmp_path):
        lines = [f"{'#' * i} Level {i}" for i in range(1, 7)]
        content = "\n\n".join(lines)
        fpath = _write(tmp_path / "levels.md", content)
        meta = TextExtractor().extract(fpath)
        assert len(meta.headings) == 6
        assert meta.headings[0] == "Level 1"
        assert meta.headings[5] == "Level 6"

    def test_md_heading_not_without_space(self, tmp_path):
        """'#word' without a space after '#' is NOT a heading."""
        content = "#NoSpace\n\n## Valid Heading\n"
        fpath = _write(tmp_path / "nospace.md", content)
        meta = TextExtractor().extract(fpath)
        assert meta.headings == ["Valid Heading"]

    def test_markdown_extension(self, tmp_path):
        """'.markdown' extension also triggers Markdown parsing."""
        content = "# Markdown Title\n\nBody text."
        fpath = _write(tmp_path / "doc.markdown", content)
        meta = TextExtractor().extract(fpath)
        assert meta.headings == ["Markdown Title"]
        assert meta.title == "Markdown Title"

    def test_md_links_treated_as_data(self, tmp_path):
        """Links in Markdown are just data — not fetched or resolved."""
        content = "# Links\n\n[Click](https://example.com)\n![img](http://evil.com/x.png)\n"
        fpath = _write(tmp_path / "links.md", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        assert "https://example.com" in meta.text_preview
        # No network access should have been attempted

    def test_md_code_blocks_as_data(self, tmp_path):
        """Code blocks are treated as text data, not executed."""
        content = "# Code\n\n```python\nimport os\nos.system('echo hacked')\n```\n"
        fpath = _write(tmp_path / "code.md", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        assert "os.system" in meta.text_preview

    def test_md_with_frontmatter(self, tmp_path):
        content = "---\ntitle: YAML Front Matter\nauthor: Test\n---\n# Actual Title\n\nBody."
        fpath = _write(tmp_path / "front.md", content)
        meta = TextExtractor().extract(fpath)
        # The heading extraction should find "Actual Title"
        assert "Actual Title" in meta.headings


# ===================================================================
# TextExtractor — Encoding Tests
# ===================================================================

class TestTextExtractorEncoding:
    """Tests for encoding detection and fallback chain."""

    def test_utf8(self, tmp_path):
        content = "Ünïcödé content with spëcïäl characters"
        fpath = _write(tmp_path / "utf8.txt", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        assert "Ünïcödé" in meta.text_preview

    def test_utf8_bom(self, tmp_path):
        """UTF-8 BOM should be stripped transparently."""
        raw = b"\xef\xbb\xbfBOM content here"
        fpath = str(tmp_path / "bom.txt")
        (tmp_path / "bom.txt").write_bytes(raw)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        assert meta.text_preview.startswith("BOM content here")

    def test_latin1_fallback(self, tmp_path):
        """Latin-1 content that's not valid UTF-8 should fall back."""
        raw = "Résumé für München".encode("latin-1")
        fpath = str(tmp_path / "latin1.txt")
        (tmp_path / "latin1.txt").write_bytes(raw)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "PARTIAL"
        assert len(meta.text_preview) > 0

    def test_corrupted_bytes(self, tmp_path):
        """Random bytes should not crash the extractor."""
        raw = bytes(range(256)) + b"\xff\xfe\xfd\xfc"
        fpath = str(tmp_path / "binary.txt")
        (tmp_path / "binary.txt").write_bytes(raw)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "PARTIAL"
        assert meta.extractor_name == "TextExtractor"

    def test_mixed_encoding(self, tmp_path):
        """UTF-8 text with some invalid bytes should not crash."""
        raw = b"Valid text \x80\x81\x82 more text"
        fpath = str(tmp_path / "mixed.txt")
        (tmp_path / "mixed.txt").write_bytes(raw)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "PARTIAL"

    def test_chinese_utf8(self, tmp_path):
        content = "数据库管理系统\n第一章：关系模型"
        fpath = _write(tmp_path / "chinese.txt", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        assert "数据库" in meta.text_preview

    def test_japanese_utf8(self, tmp_path):
        content = "こんにちは世界\nテストドキュメント"
        fpath = _write(tmp_path / "japanese.txt", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        assert "こんにちは" in meta.text_preview


# ===================================================================
# TextExtractor — Bounded Reading / Truncation Tests
# ===================================================================

class TestTextExtractorBounded:
    """Tests for memory-bounded reading of large files."""

    def test_large_file_truncated(self, tmp_path):
        """Files >64KB should only read the first 64KB."""
        # Write a 200KB file
        content = "line of text\n" * 20000  # ~260KB
        fpath = _write(tmp_path / "huge.log", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        # text_preview should be at most 1024 chars
        assert len(meta.text_preview) <= 1024

    def test_exactly_64kb(self, tmp_path):
        content = "a" * (64 * 1024)
        fpath = _write(tmp_path / "exact.txt", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"

    def test_custom_max_bytes(self, tmp_path):
        """max_bytes parameter limits reading."""
        content = "abcdefghij" * 100  # 1000 chars
        fpath = _write(tmp_path / "custom.txt", content)
        meta = TextExtractor().extract(fpath, max_bytes=50)
        # text_preview from only first 50 bytes
        assert len(meta.text_preview) <= 50

    @pytest.mark.parametrize("limit", [None, 64 * 1024, 10**12])
    def test_read_never_exceeds_hard_cap(self, tmp_path, monkeypatch, limit):
        fpath = _write(tmp_path / "bounded.log", "prefix " * 10000 + "outsidecap")
        requested = []
        original = TextExtractor._read_bounded

        def record_read(path, max_bytes):
            assert 0 <= max_bytes <= 64 * 1024
            requested.append(max_bytes)
            return original(path, max_bytes)

        monkeypatch.setattr(TextExtractor, "_read_bounded", staticmethod(record_read))
        meta = TextExtractor().extract(fpath, max_bytes=limit)
        assert meta.extraction_status == "SUCCESS"
        assert requested == [64 * 1024]
        assert "outsidecap" not in meta.keywords

    @pytest.mark.parametrize("limit", [-1, -100, 1.5, "64", True])
    def test_invalid_limits_fail_before_read(self, monkeypatch, limit):
        def unexpected_read(*args):
            pytest.fail("Invalid limit reached file I/O")

        monkeypatch.setattr(TextExtractor, "_read_bounded", staticmethod(unexpected_read))
        meta = TextExtractor().extract("unused.txt", max_bytes=limit)
        assert meta.extraction_status == "FAILED"
        assert "max_bytes" in meta.error_message

    def test_zero_limit(self, tmp_path):
        fpath = _write(tmp_path / "zero.txt", "Content")
        meta = TextExtractor().extract(fpath, max_bytes=0)
        assert meta.extraction_status == "SUCCESS"
        assert meta.title is None
        assert meta.text_preview == ""
        assert meta.keywords == []

    def test_10mb_file_safe(self, tmp_path):
        """10MB+ file should be handled without OOM (only 64KB read)."""
        chunk = b"x" * 1024
        fpath = str(tmp_path / "large.log")
        with open(fpath, "wb") as f:
            for _ in range(11 * 1024):  # More than 10 MiB
                f.write(chunk)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        assert meta.extractor_name == "TextExtractor"

    def test_source_file_unchanged(self, tmp_path):
        """Extraction must NOT modify the source file."""
        content = b"original content here"
        fpath = str(tmp_path / "readonly.txt")
        (tmp_path / "readonly.txt").write_bytes(content)
        stat_before = os.stat(fpath)

        TextExtractor().extract(fpath)

        assert (tmp_path / "readonly.txt").read_bytes() == content
        stat_after = os.stat(fpath)
        assert stat_before.st_size == stat_after.st_size


# ===================================================================
# TextExtractor — Error Handling Tests
# ===================================================================

class TestTextExtractorErrors:
    """Tests for error handling in TextExtractor."""

    def test_missing_file(self, tmp_path):
        fpath = str(tmp_path / "nonexistent.txt")
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "FAILED"
        assert meta.extractor_name == "TextExtractor"
        assert len(meta.error_message) > 0

    def test_permission_denied(self, tmp_path, monkeypatch):
        fpath = tmp_path / "secret.txt"
        fpath.write_text("secret")

        def denied(*args, **kwargs):
            raise PermissionError("Permission denied")

        monkeypatch.setattr(
            "src.core.file_intelligence.extractors.text.open", denied, raising=False
        )
        meta = TextExtractor().extract(str(fpath))
        assert meta.extraction_status == "FAILED"
        assert "Permission denied" in meta.error_message

    def test_directory_path(self, tmp_path):
        meta = TextExtractor().extract(str(tmp_path))
        assert meta.extraction_status == "FAILED"

    def test_invalid_path(self):
        meta = TextExtractor().extract("invalid\0.txt")
        assert meta.extraction_status == "FAILED"


# ===================================================================
# TextExtractor — Supported File Types
# ===================================================================

class TestTextExtractorFileTypes:
    """Tests for each supported file extension."""

    def test_rst_file(self, tmp_path):
        content = "Title\n=====\n\nReStructuredText body."
        fpath = _write(tmp_path / "doc.rst", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        assert meta.title == "Title"

    def test_csv_file(self, tmp_path):
        content = "name,age,city\nAlice,30,NYC\nBob,25,LA"
        fpath = _write(tmp_path / "data.csv", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"
        assert meta.title == "name,age,city"

    def test_tsv_file(self, tmp_path):
        content = "col1\tcol2\tcol3\nval1\tval2\tval3"
        fpath = _write(tmp_path / "data.tsv", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"

    def test_log_file(self, tmp_path):
        content = "[2024-01-01 10:00:00] INFO: Server started\n[2024-01-01 10:01:00] ERROR: Connection failed"
        fpath = _write(tmp_path / "app.log", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"

    def test_json_file(self, tmp_path):
        content = json.dumps({"key": "value", "list": [1, 2, 3]})
        fpath = _write(tmp_path / "config.json", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"

    def test_yaml_file(self, tmp_path):
        content = "name: SmartSort\nversion: 1.0\ndependencies:\n  - PyQt6\n  - watchdog"
        fpath = _write(tmp_path / "config.yaml", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"

    def test_yml_file(self, tmp_path):
        content = "key: value"
        fpath = _write(tmp_path / "data.yml", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"

    def test_xml_file(self, tmp_path):
        content = '<?xml version="1.0"?>\n<root><item>Test</item></root>'
        fpath = _write(tmp_path / "data.xml", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"

    def test_html_file(self, tmp_path):
        content = "<html><head><title>Test Page</title></head><body><h1>Hello</h1></body></html>"
        fpath = _write(tmp_path / "page.html", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"

    def test_htm_file(self, tmp_path):
        content = "<html><body>Content</body></html>"
        fpath = _write(tmp_path / "page.htm", content)
        meta = TextExtractor().extract(fpath)
        assert meta.extraction_status == "SUCCESS"


# ===================================================================
# TextExtractor — Determinism Tests
# ===================================================================

class TestTextExtractorDeterminism:
    """Tests for deterministic repeated extraction."""

    def test_repeated_extraction_identical(self, tmp_path):
        content = "# Title\n\n## Section\n\nSome content with keywords keywords keywords."
        fpath = _write(tmp_path / "stable.md", content)

        meta1 = TextExtractor().extract(fpath)
        meta2 = TextExtractor().extract(fpath)

        assert meta1.title == meta2.title
        assert meta1.headings == meta2.headings
        assert meta1.text_preview == meta2.text_preview
        assert meta1.keywords == meta2.keywords
        assert meta1.extraction_status == meta2.extraction_status

    def test_no_side_effects(self, tmp_path):
        """Directory contents must not change during extraction."""
        content = "Test content."
        fpath = _write(tmp_path / "test.txt", content)
        entries_before = set(os.listdir(str(tmp_path)))

        TextExtractor().extract(fpath)

        entries_after = set(os.listdir(str(tmp_path)))
        assert entries_before == entries_after


# ===================================================================
# Module Isolation Tests
# ===================================================================

class TestPhase3ModuleIsolation:
    """Verify Phase 3 modules have zero Qt imports and no forbidden deps."""

    @pytest.mark.parametrize("module_path", [
        "src/core/file_intelligence/extractors/__init__.py",
        "src/core/file_intelligence/extractors/base.py",
        "src/core/file_intelligence/extractors/text.py",
    ])
    def test_no_qt_imports(self, module_path):
        with open(module_path, "r") as f:
            source = f.read()
        assert "PyQt" not in source
        assert "QApplication" not in source
        assert "QThread" not in source
        assert "QWidget" not in source
        assert "subprocess" not in source

    def test_extractors_package_exports(self):
        from src.core.file_intelligence.extractors import (
            BaseExtractor,
            ExtractorRegistry,
            TextExtractor,
        )
        assert BaseExtractor is not None
        assert ExtractorRegistry is not None
        assert TextExtractor is not None

    def test_phase1_phase2_exports_preserved(self):
        """All prior phase exports must still work."""
        import src.core.file_intelligence as fi
        assert hasattr(fi, "FileContext")
        assert hasattr(fi, "ExtractedMetadata")
        assert hasattr(fi, "FileContextBuilder")
        assert hasattr(fi, "DeterministicMime")
