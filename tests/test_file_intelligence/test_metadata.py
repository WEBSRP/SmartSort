"""Phase 2 tests for filesystem metadata extraction and MIME detection.

All tests are pure Python — no Qt, no network, no real user data,
no timing dependencies, fully deterministic. Uses pytest tmp_path
fixtures for filesystem operations.
"""

import hashlib
import os
import stat
import json

import pytest

from src.core.file_intelligence.context import (
    ConfidenceLevel,
    FileContext,
    ExtractedMetadata,
    OriginSource,
)
from src.core.file_intelligence.metadata import FileContextBuilder, FileMetadataExtractor
from src.core.file_intelligence.mime import DeterministicMime


# ===================================================================
# Helpers
# ===================================================================

def _write_file(path, content=b"hello world"):
    """Write binary content to *path* and return the path string."""
    path.write_bytes(content)
    return str(path)


# ===================================================================
# DeterministicMime Tests
# ===================================================================

class TestDeterministicMimeGuess:
    """Tests for DeterministicMime.guess_mime()."""

    @pytest.mark.parametrize("ext,expected", [
        (".pdf", "application/pdf"),
        (".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        (".doc", "application/msword"),
        (".pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        (".ppt", "application/vnd.ms-powerpoint"),
        (".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        (".xls", "application/vnd.ms-excel"),
        (".odt", "application/vnd.oasis.opendocument.text"),
        (".rtf", "application/rtf"),
        (".txt", "text/plain"),
        (".md", "text/markdown"),
        (".csv", "text/csv"),
        (".json", "application/json"),
        (".xml", "application/xml"),
        (".yaml", "application/x-yaml"),
        (".yml", "application/x-yaml"),
        (".toml", "application/toml"),
        (".png", "image/png"),
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".gif", "image/gif"),
        (".bmp", "image/bmp"),
        (".svg", "image/svg+xml"),
        (".webp", "image/webp"),
        (".tiff", "image/tiff"),
        (".ico", "image/x-icon"),
        (".heic", "image/heic"),
        (".mp3", "audio/mpeg"),
        (".flac", "audio/flac"),
        (".wav", "audio/wav"),
        (".ogg", "audio/ogg"),
        (".mp4", "video/mp4"),
        (".mkv", "video/x-matroska"),
        (".avi", "video/x-msvideo"),
        (".mov", "video/quicktime"),
        (".webm", "video/webm"),
        (".zip", "application/zip"),
        (".rar", "application/x-rar-compressed"),
        (".7z", "application/x-7z-compressed"),
        (".tar", "application/x-tar"),
        (".gz", "application/gzip"),
        (".deb", "application/vnd.debian.binary-package"),
        (".iso", "application/x-iso9660-image"),
        (".py", "text/x-python"),
        (".js", "text/javascript"),
        (".java", "text/x-java"),
        (".c", "text/x-c"),
        (".cpp", "text/x-c++"),
        (".go", "text/x-go"),
        (".rs", "text/x-rust"),
        (".rb", "text/x-ruby"),
        (".html", "text/html"),
        (".css", "text/css"),
        (".sql", "application/sql"),
        (".sh", "application/x-shellscript"),
        (".epub", "application/epub+zip"),
        (".ttf", "font/ttf"),
        (".otf", "font/otf"),
        (".woff2", "font/woff2"),
    ])
    def test_common_extensions(self, tmp_path, ext, expected):
        """MIME detection maps 50+ common extensions correctly."""
        fpath = _write_file(tmp_path / f"test{ext}")
        assert DeterministicMime.guess_mime(fpath) == expected

    def test_case_insensitive_extension(self, tmp_path):
        fpath = _write_file(tmp_path / "REPORT.PDF")
        assert DeterministicMime.guess_mime(fpath) == "application/pdf"

    def test_unknown_extension_falls_back(self, tmp_path):
        fpath = _write_file(tmp_path / "data.xyz123")
        mime = DeterministicMime.guess_mime(fpath)
        assert isinstance(mime, str)
        assert len(mime) > 0

    def test_no_extension(self, tmp_path):
        fpath = _write_file(tmp_path / "Makefile")
        mime = DeterministicMime.guess_mime(fpath)
        assert isinstance(mime, str)

    def test_magic_bytes_pdf(self, tmp_path):
        """PDF magic bytes override unknown extension."""
        fpath = _write_file(tmp_path / "mystery.bin", b"%PDF-1.4 fake content")
        assert DeterministicMime.guess_mime(fpath) == "application/pdf"

    def test_magic_bytes_png(self, tmp_path):
        header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        fpath = _write_file(tmp_path / "image.bin", header)
        assert DeterministicMime.guess_mime(fpath) == "image/png"

    def test_magic_bytes_jpeg(self, tmp_path):
        header = b"\xff\xd8\xff\xe0" + b"\x00" * 20
        fpath = _write_file(tmp_path / "photo.bin", header)
        assert DeterministicMime.guess_mime(fpath) == "image/jpeg"

    def test_magic_bytes_zip(self, tmp_path):
        header = b"PK\x03\x04" + b"\x00" * 20
        fpath = _write_file(tmp_path / "archive.bin", header)
        assert DeterministicMime.guess_mime(fpath) == "application/zip"

    def test_magic_bytes_gzip(self, tmp_path):
        header = b"\x1f\x8b\x08" + b"\x00" * 20
        fpath = _write_file(tmp_path / "compressed.bin", header)
        assert DeterministicMime.guess_mime(fpath) == "application/gzip"

    def test_magic_bytes_elf(self, tmp_path):
        header = b"\x7fELF" + b"\x00" * 20
        fpath = _write_file(tmp_path / "binary.bin", header)
        assert DeterministicMime.guess_mime(fpath) == "application/x-executable"

    def test_riff_wav(self, tmp_path):
        """RIFF container with WAVE FourCC."""
        header = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 20
        fpath = _write_file(tmp_path / "audio.bin", header)
        assert DeterministicMime.guess_mime(fpath) == "audio/wav"

    def test_riff_webp(self, tmp_path):
        """RIFF container with WEBP FourCC."""
        header = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20
        fpath = _write_file(tmp_path / "image2.bin", header)
        assert DeterministicMime.guess_mime(fpath) == "image/webp"

    def test_extension_takes_priority_over_magic(self, tmp_path):
        """Known extension is preferred over magic bytes."""
        fpath = _write_file(tmp_path / "report.pdf", b"not actually pdf")
        assert DeterministicMime.guess_mime(fpath) == "application/pdf"

    def test_empty_file(self, tmp_path):
        fpath = _write_file(tmp_path / "empty.xyz", b"")
        mime = DeterministicMime.guess_mime(fpath)
        assert isinstance(mime, str)


class TestDeterministicMimeCategoryHint:
    """Tests for DeterministicMime.get_category_hint()."""

    @pytest.mark.parametrize("ext,expected", [
        (".pdf", "Documents"),
        (".docx", "Documents"),
        (".txt", "Documents"),
        (".md", "Documents"),
        (".csv", "Documents"),
        (".epub", "Documents"),
        (".png", "Images"),
        (".jpg", "Images"),
        (".svg", "Images"),
        (".webp", "Images"),
        (".mp3", "Media"),
        (".mp4", "Media"),
        (".mkv", "Media"),
        (".flac", "Media"),
        (".zip", "Archives"),
        (".tar", "Archives"),
        (".7z", "Archives"),
        (".deb", "Archives"),
        (".py", "Code"),
        (".js", "Code"),
        (".java", "Code"),
        (".html", "Code"),
        (".json", "Code"),
        (".exe", "Applications"),
    ])
    def test_category_hints(self, ext, expected):
        assert DeterministicMime.get_category_hint(ext) == expected

    def test_unknown_extension(self):
        assert DeterministicMime.get_category_hint(".xyz999") == "Others"

    def test_case_insensitive(self):
        assert DeterministicMime.get_category_hint(".PDF") == "Documents"
        assert DeterministicMime.get_category_hint(".Py") == "Code"

    def test_empty_extension(self):
        assert DeterministicMime.get_category_hint("") == "Others"


# ===================================================================
# FileContextBuilder Tests
# ===================================================================

class TestFileContextBuilderBasic:
    """Basic FileContextBuilder.build_initial_context tests."""

    def test_regular_file(self, tmp_path):
        content = b"This is test content for Phase 2."
        fpath = _write_file(tmp_path / "report.pdf", content)

        ctx = FileContextBuilder.build_initial_context(fpath)

        assert isinstance(ctx, FileContext)
        assert ctx.filename == "report.pdf"
        assert ctx.stem == "report"
        assert ctx.extension == ".pdf"
        assert ctx.mime_type == "application/pdf"
        assert ctx.size_bytes == len(content)
        assert ctx.inode > 0
        assert ctx.device > 0
        assert ctx.created_timestamp > 0
        assert ctx.modified_timestamp > 0
        assert ctx.sha256_hash is None  # Not requested

    def test_canonical_path(self, tmp_path):
        """Path in FileContext must be absolute and canonical."""
        fpath = _write_file(tmp_path / "file.txt")
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert os.path.isabs(ctx.path)
        assert ctx.path == os.path.abspath(os.path.realpath(fpath))

    def test_relative_path_resolved(self, tmp_path):
        """Relative paths are resolved to absolute canonical paths."""
        fpath = _write_file(tmp_path / "data.csv")
        # Create a relative path by going through parent
        rel = os.path.join(
            str(tmp_path), "..", os.path.basename(str(tmp_path)), "data.csv"
        )
        ctx = FileContextBuilder.build_initial_context(rel)
        assert os.path.isabs(ctx.path)
        assert ctx.path == os.path.abspath(os.path.realpath(fpath))

    def test_stat_fields(self, tmp_path):
        content = b"x" * 1024
        fpath = _write_file(tmp_path / "sized.bin", content)
        st = os.stat(fpath)

        ctx = FileContextBuilder.build_initial_context(fpath)

        assert ctx.size_bytes == st.st_size == 1024
        assert ctx.inode == st.st_ino
        assert ctx.device == st.st_dev
        assert ctx.created_timestamp == st.st_ctime
        assert ctx.modified_timestamp == st.st_mtime

    def test_metadata_status_success(self, tmp_path):
        fpath = _write_file(tmp_path / "ok.txt")
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.metadata.extractor_name == "filesystem"
        assert ctx.metadata.extraction_status == "SUCCESS"
        assert ctx.metadata.error_message == ""

    def test_origin_populated_from_xattr(self, tmp_path, monkeypatch):
        fpath = _write_file(tmp_path / "download.pdf")

        def mock_getxattr(path, attr):
            if attr == b"user.xdg.origin.url":
                return b"https://downloads.example/report.pdf?token=secret"
            raise OSError("No data available")

        monkeypatch.setattr(os, "getxattr", mock_getxattr)

        ctx = FileContextBuilder.build_initial_context(fpath)

        assert ctx.origin.url == "https://downloads.example/report.pdf"
        assert ctx.origin.source is OriginSource.EXTENDED_ATTRIBUTE
        assert ctx.origin.confidence is ConfidenceLevel.CONFIRMED


class TestFileContextBuilderHashing:
    """Tests for optional SHA-256 hashing."""

    def test_hash_disabled_by_default(self, tmp_path):
        fpath = _write_file(tmp_path / "nohash.txt")
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.sha256_hash is None

    def test_hash_computed_when_requested(self, tmp_path):
        content = b"deterministic content for hashing"
        fpath = _write_file(tmp_path / "hashme.txt", content)

        ctx = FileContextBuilder.build_initial_context(fpath, compute_hash=True)

        expected = hashlib.sha256(content).hexdigest()
        assert ctx.sha256_hash == expected

    def test_hash_deterministic(self, tmp_path):
        content = b"same content twice"
        fpath = _write_file(tmp_path / "det.bin", content)

        ctx1 = FileContextBuilder.build_initial_context(fpath, compute_hash=True)
        ctx2 = FileContextBuilder.build_initial_context(fpath, compute_hash=True)

        assert ctx1.sha256_hash == ctx2.sha256_hash


class TestFileMetadataExtractorXattrs:
    """Extended attribute extraction tests."""

    def test_read_xattr_returns_decoded_value(self, tmp_path, monkeypatch):
        fpath = _write_file(tmp_path / "download.pdf")

        def mock_getxattr(path, attr):
            assert path == fpath
            assert attr == b"user.xdg.origin.url"
            return b"https://example.com/files/report.pdf"

        monkeypatch.setattr(os, "getxattr", mock_getxattr)

        value = FileMetadataExtractor.read_xattr(fpath, "user.xdg.origin.url")

        assert value == "https://example.com/files/report.pdf"

    def test_read_xattr_missing_returns_none(self, tmp_path, monkeypatch):
        fpath = _write_file(tmp_path / "download.pdf")

        def mock_getxattr(path, attr):
            raise OSError("No data available")

        monkeypatch.setattr(os, "getxattr", mock_getxattr)

        assert FileMetadataExtractor.read_xattr(fpath, "user.xdg.origin.url") is None

    def test_read_extended_attributes_collects_available_values(
        self,
        tmp_path,
        monkeypatch,
    ):
        fpath = _write_file(tmp_path / "download.pdf")

        def mock_getxattr(path, attr):
            if attr == b"user.xdg.origin.url":
                return b"https://example.com/downloads/report.pdf"
            raise OSError("No data available")

        monkeypatch.setattr(os, "getxattr", mock_getxattr)

        attributes = FileMetadataExtractor.read_extended_attributes(fpath)

        assert attributes == {
            "user.xdg.origin.url": "https://example.com/downloads/report.pdf",
        }

    def test_extract_origin_from_xattrs_strips_query_and_fragment(
        self,
        tmp_path,
        monkeypatch,
    ):
        fpath = _write_file(tmp_path / "download.pdf")

        def mock_getxattr(path, attr):
            if attr == b"user.xdg.origin.url":
                return b"https://example.com/file.pdf?token=secret#section"
            raise OSError("No data available")

        monkeypatch.setattr(os, "getxattr", mock_getxattr)

        origin = FileMetadataExtractor.extract_origin_from_xattrs(fpath)

        assert origin.url == "https://example.com/file.pdf"
        assert origin.source is OriginSource.EXTENDED_ATTRIBUTE
        assert origin.confidence is ConfidenceLevel.CONFIRMED
        assert "user.xdg.origin.url" in origin.evidence_detail

    def test_extract_origin_from_xattrs_uses_referrer_fallback(
        self,
        tmp_path,
        monkeypatch,
    ):
        fpath = _write_file(tmp_path / "download.pdf")

        def mock_getxattr(path, attr):
            if attr == b"user.xdg.referrer.url":
                return b"https://referrer.example/path?auth=secret"
            raise OSError("No data available")

        monkeypatch.setattr(os, "getxattr", mock_getxattr)

        origin = FileMetadataExtractor.extract_origin_from_xattrs(fpath)

        assert origin.url == "https://referrer.example/path"
        assert origin.source is OriginSource.EXTENDED_ATTRIBUTE

    def test_extract_origin_from_xattrs_unavailable_is_unknown(
        self,
        tmp_path,
        monkeypatch,
    ):
        fpath = _write_file(tmp_path / "download.pdf")

        def mock_getxattr(path, attr):
            raise AttributeError("xattrs unavailable")

        monkeypatch.setattr(os, "getxattr", mock_getxattr)

        origin = FileMetadataExtractor.extract_origin_from_xattrs(fpath)

        assert origin.url == ""
        assert origin.source is OriginSource.UNKNOWN
        assert origin.confidence is ConfidenceLevel.UNKNOWN


class TestFileContextBuilderFilenameEdgeCases:
    """Filename, stem, and extension edge cases."""

    def test_multiple_extensions(self, tmp_path):
        fpath = _write_file(tmp_path / "archive.tar.gz")
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.filename == "archive.tar.gz"
        assert ctx.stem == "archive.tar"
        assert ctx.extension == ".gz"

    def test_dotfile(self, tmp_path):
        fpath = _write_file(tmp_path / ".gitignore")
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.filename == ".gitignore"
        assert ctx.stem == ".gitignore"
        assert ctx.extension == ""

    def test_no_extension(self, tmp_path):
        fpath = _write_file(tmp_path / "Makefile")
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.filename == "Makefile"
        assert ctx.extension == ""

    def test_unicode_filename(self, tmp_path):
        fpath = _write_file(tmp_path / "数据库_讲义.pdf")
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.filename == "数据库_讲义.pdf"
        assert ctx.stem == "数据库_讲义"
        assert ctx.extension == ".pdf"

    def test_spaces_in_path(self, tmp_path):
        spaced = tmp_path / "My Documents"
        spaced.mkdir()
        fpath = _write_file(spaced / "Final Report (v2).docx")
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.filename == "Final Report (v2).docx"
        assert " " in ctx.path

    def test_uppercase_extension(self, tmp_path):
        fpath = _write_file(tmp_path / "PHOTO.JPG")
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.extension == ".JPG"
        # MIME should still be resolved correctly
        assert ctx.mime_type == "image/jpeg"


class TestFileContextBuilderErrorHandling:
    """Error handling: missing files, permissions, broken symlinks."""

    def test_missing_file_raises_valueerror(self, tmp_path):
        missing = str(tmp_path / "nonexistent.txt")
        with pytest.raises(ValueError, match="File not found"):
            FileContextBuilder.build_initial_context(missing)

    def test_missing_file_error_includes_path(self, tmp_path):
        missing = str(tmp_path / "ghost.pdf")
        with pytest.raises(ValueError, match="ghost.pdf"):
            FileContextBuilder.build_initial_context(missing)

    def test_broken_symlink_raises_valueerror(self, tmp_path):
        target = tmp_path / "target.txt"
        link = tmp_path / "broken_link"
        link.symlink_to(target)  # target doesn't exist
        with pytest.raises(ValueError, match="File not found"):
            FileContextBuilder.build_initial_context(str(link))

    def test_permission_denied(self, tmp_path):
        """PermissionError returns FileContext with PERMISSION_DENIED status."""
        fpath = tmp_path / "secret.txt"
        fpath.write_bytes(b"secret")
        fpath.chmod(0o000)

        try:
            # If running as root, chmod 000 still allows stat, so skip
            try:
                os.stat(str(fpath))
                # If stat succeeds, we can't test permission denied
                pytest.skip("Cannot test PermissionError (running as root?)")
            except PermissionError:
                pass

            ctx = FileContextBuilder.build_initial_context(str(fpath))
            assert ctx.metadata.extraction_status == "PERMISSION_DENIED"
            assert ctx.size_bytes == 0
            assert "Permission denied" in ctx.metadata.error_message
        finally:
            # Restore permissions for cleanup
            fpath.chmod(0o644)


class TestFileContextBuilderSymlinks:
    """Symlink handling."""

    def test_symlink_resolves_to_target(self, tmp_path):
        target = tmp_path / "real_file.txt"
        target.write_bytes(b"real content")
        link = tmp_path / "link.txt"
        link.symlink_to(target)

        ctx = FileContextBuilder.build_initial_context(str(link))

        # Path should be resolved to the real file
        assert ctx.path == str(target.resolve())
        assert ctx.size_bytes == len(b"real content")


class TestFileContextBuilderFileSizes:
    """File size edge cases."""

    def test_empty_file(self, tmp_path):
        fpath = _write_file(tmp_path / "empty.txt", b"")
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.size_bytes == 0

    def test_large_content(self, tmp_path):
        content = b"x" * (1024 * 1024)  # 1 MB
        fpath = _write_file(tmp_path / "large.bin", content)
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.size_bytes == 1024 * 1024


class TestFileContextBuilderDeterminism:
    """Repeated collection must be deterministic."""

    def test_repeated_stat_same_result(self, tmp_path):
        fpath = _write_file(tmp_path / "stable.txt", b"stable")

        ctx1 = FileContextBuilder.build_initial_context(fpath)
        ctx2 = FileContextBuilder.build_initial_context(fpath)

        assert ctx1.path == ctx2.path
        assert ctx1.filename == ctx2.filename
        assert ctx1.stem == ctx2.stem
        assert ctx1.extension == ctx2.extension
        assert ctx1.mime_type == ctx2.mime_type
        assert ctx1.size_bytes == ctx2.size_bytes
        assert ctx1.inode == ctx2.inode
        assert ctx1.device == ctx2.device
        assert ctx1.created_timestamp == ctx2.created_timestamp
        assert ctx1.modified_timestamp == ctx2.modified_timestamp

    def test_no_filesystem_mutation(self, tmp_path):
        """Builder must not create, modify, or delete files."""
        fpath = _write_file(tmp_path / "readonly.txt", b"readonly")
        original_content = (tmp_path / "readonly.txt").read_bytes()
        original_entries = set(os.listdir(str(tmp_path)))

        FileContextBuilder.build_initial_context(fpath)

        assert (tmp_path / "readonly.txt").read_bytes() == original_content
        assert set(os.listdir(str(tmp_path))) == original_entries


class TestFileContextBuilderSerialization:
    """Serialization round-trip with Phase 1 to_dict/from_dict."""

    def test_round_trip(self, tmp_path):
        content = b"round trip test"
        fpath = _write_file(tmp_path / "roundtrip.pdf", content)

        original = FileContextBuilder.build_initial_context(fpath, compute_hash=True)
        d = original.to_dict()
        restored = FileContext.from_dict(d)

        assert restored.path == original.path
        assert restored.filename == original.filename
        assert restored.size_bytes == original.size_bytes
        assert restored.sha256_hash == original.sha256_hash
        assert restored.metadata.extraction_status == "SUCCESS"

    def test_json_serializable(self, tmp_path):
        fpath = _write_file(tmp_path / "json_test.txt", b"json")
        ctx = FileContextBuilder.build_initial_context(fpath)
        json_str = json.dumps(ctx.to_dict())
        data = json.loads(json_str)
        restored = FileContext.from_dict(data)
        assert restored == ctx


class TestFileContextBuilderMIME:
    """MIME type integration in FileContextBuilder."""

    @pytest.mark.parametrize("name,content,expected_mime", [
        ("doc.pdf", b"%PDF-1.4 content", "application/pdf"),
        ("code.py", b"print('hello')", "text/x-python"),
        ("data.json", b'{"key": "value"}', "application/json"),
        ("image.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "image/png"),
        ("archive.zip", b"PK\x03\x04" + b"\x00" * 20, "application/zip"),
    ])
    def test_mime_populated(self, tmp_path, name, content, expected_mime):
        fpath = _write_file(tmp_path / name, content)
        ctx = FileContextBuilder.build_initial_context(fpath)
        assert ctx.mime_type == expected_mime


# ===================================================================
# Module Isolation Tests
# ===================================================================

class TestModuleIsolation:
    """Verify Phase 2 modules have zero Qt and no forbidden dependencies."""

    @pytest.mark.parametrize("module_path", [
        "src/core/file_intelligence/metadata.py",
        "src/core/file_intelligence/mime.py",
    ])
    def test_no_qt_imports(self, module_path):
        with open(module_path, "r") as f:
            source = f.read()
        assert "PyQt" not in source
        assert "QApplication" not in source
        assert "QThread" not in source
        assert "QWidget" not in source

    def test_package_exports_phase2(self):
        """Phase 2 classes exported from __init__."""
        import src.core.file_intelligence as fi
        assert hasattr(fi, "FileContextBuilder")
        assert hasattr(fi, "FileMetadataExtractor")
        assert hasattr(fi, "DeterministicMime")

    def test_phase1_exports_preserved(self):
        """Phase 1 exports must still be accessible."""
        import src.core.file_intelligence as fi
        assert hasattr(fi, "ConfidenceLevel")
        assert hasattr(fi, "FileContext")
        assert hasattr(fi, "ExtractedMetadata")
        assert hasattr(fi, "EvidenceItem")
