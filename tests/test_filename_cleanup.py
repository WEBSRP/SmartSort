"""
Tests for the Smart Filename Cleanup feature.

Tests cover: disabled feature, short/long/generic/numeric/camera/repeated
filenames, extension preservation, fallback names, xattr website extraction,
CDN domain mapping, unicode handling, config customization, truncation,
and sanitization.
"""

import os
import pytest
from src.core.filename_cleanup import (
    FilenameCleanup, _GENERIC_NAMES, _EXTENSION_FALLBACKS, _CDN_TO_SITE
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cleanup():
    """Return an enabled FilenameCleanup instance with defaults."""
    return FilenameCleanup(enabled=True, min_length=4, max_length=80)


@pytest.fixture
def cleanup_disabled():
    """Return a disabled FilenameCleanup instance."""
    return FilenameCleanup(enabled=False)


# ---------------------------------------------------------------------------
# 1. Disabled Feature
# ---------------------------------------------------------------------------

def test_disabled_feature(cleanup_disabled):
    """When disabled, needs_cleanup always returns False."""
    assert cleanup_disabled.needs_cleanup("_.jpg") is False
    assert cleanup_disabled.needs_cleanup("download.pdf") is False
    assert cleanup_disabled.needs_cleanup("1.txt") is False
    assert cleanup_disabled.needs_cleanup("a" * 200 + ".txt") is False


# ---------------------------------------------------------------------------
# 2. Short Filenames
# ---------------------------------------------------------------------------

def test_short_filename(cleanup):
    """Filenames shorter than min_length (4) trigger cleanup."""
    assert cleanup.needs_cleanup("_.jpg") is True        # name="_", len=1
    assert cleanup.needs_cleanup("ab.pdf") is True       # name="ab", len=2
    assert cleanup.needs_cleanup("abc.txt") is True      # name="abc", len=3
    assert cleanup.needs_cleanup("abcd.txt") is False    # name="abcd", len=4


# ---------------------------------------------------------------------------
# 3. Long Filenames
# ---------------------------------------------------------------------------

def test_long_filename(cleanup):
    """Filenames longer than max_length (80) trigger cleanup."""
    # Use varied characters to avoid triggering repeated-char detection
    long_name = "abcdefghij" * 9  # 90 chars, well over 80
    assert cleanup.needs_cleanup(long_name + ".txt") is True
    varied_80 = "abcdefghij" * 8  # exactly 80 chars
    assert cleanup.needs_cleanup(varied_80 + ".txt") is False  # exactly at limit


# ---------------------------------------------------------------------------
# 4. Generic Filenames
# ---------------------------------------------------------------------------

def test_generic_filename(cleanup):
    """All _GENERIC_NAMES trigger cleanup, case-insensitive."""
    for generic in _GENERIC_NAMES:
        # Skip names shorter than min_length (they'd trigger for length, not name)
        filename = f"{generic}.txt"
        assert cleanup.needs_cleanup(filename) is True, f"Expected True for '{filename}'"

    # Case-insensitive
    assert cleanup.needs_cleanup("DOWNLOAD.pdf") is True
    assert cleanup.needs_cleanup("Image.jpg") is True
    assert cleanup.needs_cleanup("FILE.zip") is True
    assert cleanup.needs_cleanup("Document.docx") is True


# ---------------------------------------------------------------------------
# 5. Numeric Filenames
# ---------------------------------------------------------------------------

def test_numeric_filename(cleanup):
    """Pure digit filenames trigger cleanup."""
    assert cleanup.needs_cleanup("1.jpg") is True
    assert cleanup.needs_cleanup("42.pdf") is True
    assert cleanup.needs_cleanup("1000.txt") is True
    assert cleanup.needs_cleanup("abc123.txt") is False  # mixed, len>=4


# ---------------------------------------------------------------------------
# 6. Camera Pattern
# ---------------------------------------------------------------------------

def test_camera_pattern(cleanup):
    """Camera-style filenames trigger cleanup."""
    assert cleanup.needs_cleanup("IMG_0001.png") is True
    assert cleanup.needs_cleanup("DSC_1234.jpg") is True
    assert cleanup.needs_cleanup("IMG0001.png") is True
    assert cleanup.needs_cleanup("PXL_20240101.jpg") is True
    assert cleanup.needs_cleanup("VID-0001.mp4") is True
    assert cleanup.needs_cleanup("DCIM_0042.jpg") is True
    assert cleanup.needs_cleanup("DJI_0100.mp4") is True
    assert cleanup.needs_cleanup("MOV_1234.mp4") is True


# ---------------------------------------------------------------------------
# 7. Repeated Characters
# ---------------------------------------------------------------------------

def test_repeated_chars(cleanup):
    """Filenames with repeated characters trigger cleanup."""
    assert cleanup.needs_cleanup("aaaaaaaaaa.pdf") is True
    assert cleanup.needs_cleanup("xxxxxxxxxx.jpg") is True
    assert cleanup.needs_cleanup("abababab.txt") is True    # 2 unique chars, len>=8
    assert cleanup.needs_cleanup("abcdefgh.txt") is False   # many unique chars


# ---------------------------------------------------------------------------
# 8. Normal Filenames (no cleanup needed)
# ---------------------------------------------------------------------------

def test_normal_filename_no_cleanup(cleanup):
    """Reasonable filenames should NOT trigger cleanup."""
    assert cleanup.needs_cleanup("vacation_photo_2024.jpg") is False
    assert cleanup.needs_cleanup("budget_report_q4.xlsx") is False
    assert cleanup.needs_cleanup("my_document.pdf") is False
    assert cleanup.needs_cleanup("project_proposal.docx") is False
    assert cleanup.needs_cleanup("meeting_notes_jan.txt") is False


# ---------------------------------------------------------------------------
# 9. Extension Preservation
# ---------------------------------------------------------------------------

def test_extension_preservation(cleanup, tmp_path):
    """generate_clean_name always preserves the original extension."""
    for name, ext in [("_", ".jpg"), ("download", ".pdf"), ("image", ".PNG")]:
        fp = tmp_path / (name + ext)
        fp.write_text("test")
        result = cleanup.generate_clean_name(str(fp))
        assert result.endswith(ext), f"Expected extension '{ext}', got '{result}'"


# ---------------------------------------------------------------------------
# 10. Fallback Names
# ---------------------------------------------------------------------------

def test_fallback_names(cleanup, tmp_path):
    """Without xattr metadata, uses extension-based fallback names."""
    cases = [
        ("_.jpg", "image.jpg"),
        ("_.pdf", "document.pdf"),
        ("_.mp4", "video.mp4"),
        ("_.zip", "archive.zip"),
        ("_.xyz", "file.xyz"),      # unknown extension
        ("_.mp3", "audio.mp3"),
        ("_.xlsx", "spreadsheet.xlsx"),
        ("_.pptx", "presentation.pptx"),
        ("_.epub", "ebook.epub"),
    ]
    for src_name, expected in cases:
        fp = tmp_path / src_name
        fp.write_text("test")
        result = cleanup.generate_clean_name(str(fp))
        assert result == expected, f"For '{src_name}': expected '{expected}', got '{result}'"


# ---------------------------------------------------------------------------
# 11. Website Extraction from xattr
# ---------------------------------------------------------------------------

def test_website_extraction_from_xattr(cleanup, tmp_path, monkeypatch):
    """When xattr metadata is available, use website domain as filename."""
    # Test with reddit referrer
    fp1 = tmp_path / "_.jpg"
    fp1.write_text("test")

    def mock_getxattr_reddit(path, attr):
        attr_str = attr.decode('utf-8') if isinstance(attr, bytes) else attr
        if attr_str == "user.xdg.referrer.url":
            return b"https://www.reddit.com/r/wallpapers/comments/abc"
        raise OSError("No such attribute")

    monkeypatch.setattr(os, "getxattr", mock_getxattr_reddit)
    result = cleanup.generate_clean_name(str(fp1))
    assert result == "reddit.jpg"

    # Test with github origin
    fp2 = tmp_path / "download.pdf"
    fp2.write_text("test")

    def mock_getxattr_github(path, attr):
        attr_str = attr.decode('utf-8') if isinstance(attr, bytes) else attr
        if attr_str == "user.xdg.referrer.url":
            return b"https://github.com/user/repo/releases"
        raise OSError("No such attribute")

    monkeypatch.setattr(os, "getxattr", mock_getxattr_github)
    result = cleanup.generate_clean_name(str(fp2))
    assert result == "github.pdf"


# ---------------------------------------------------------------------------
# 12. CDN Domain Mapping
# ---------------------------------------------------------------------------

def test_cdn_domain_mapping():
    """CDN domains correctly map to their parent site names."""
    cases = [
        ("https://i.redd.it/abc.jpg", "reddit"),
        ("https://i.pinimg.com/img.png", "pinterest"),
        ("https://raw.githubusercontent.com/file.txt", "github"),
        ("https://upload.wikimedia.org/file.png", "wikipedia"),
        ("https://cdn.wallpaperflare.com/img.jpg", "wallpaperflare"),
        ("https://pbs.twimg.com/media/photo.jpg", "twitter"),
        ("https://scontent.cdninstagram.com/v/img.jpg", "instagram"),
        ("https://external-preview.redd.it/img.jpg", "reddit"),
        ("https://images.unsplash.com/photo.jpg", "unsplash"),
        ("https://live.staticflickr.com/img.jpg", "flickr"),
    ]
    for url, expected in cases:
        result = FilenameCleanup._domain_to_site_name(url)
        assert result == expected, f"URL '{url}': expected '{expected}', got '{result}'"


# ---------------------------------------------------------------------------
# 13. Regular Domain Extraction
# ---------------------------------------------------------------------------

def test_domain_extraction_regular_sites():
    """Regular website domains are extracted correctly."""
    cases = [
        ("https://www.example.com/file.pdf", "example"),
        ("https://stackoverflow.com/questions/1", "stackoverflow"),
        ("https://docs.python.org/3/library", "python"),
        ("https://en.wikipedia.org/wiki/Test", "wikipedia"),  # CDN mapping
    ]
    for url, expected in cases:
        result = FilenameCleanup._domain_to_site_name(url)
        assert result == expected, f"URL '{url}': expected '{expected}', got '{result}'"


# ---------------------------------------------------------------------------
# 14. Unicode Filenames
# ---------------------------------------------------------------------------

def test_unicode_filename(cleanup):
    """Unicode characters in filenames are handled correctly."""
    assert cleanup.needs_cleanup("très_long_name_with_accents.txt") is False
    assert cleanup.needs_cleanup("日.txt") is True  # too short
    assert cleanup.needs_cleanup("日本語テスト.txt") is False  # len >= 4
    assert cleanup.needs_cleanup("café_menu.pdf") is False


# ---------------------------------------------------------------------------
# 15. Config Migration / Custom Values
# ---------------------------------------------------------------------------

def test_config_custom_values():
    """FilenameCleanup respects custom min/max length settings."""
    custom = FilenameCleanup(enabled=True, min_length=2, max_length=50)

    # Custom min_length: "ab" (len 2) should NOT trigger cleanup
    assert custom.needs_cleanup("ab.txt") is False

    # Custom max_length: 51 chars should trigger cleanup (use varied chars)
    varied_51 = "abcdefghij" * 5 + "k"  # 51 chars
    assert custom.needs_cleanup(varied_51 + ".txt") is True
    varied_50 = "abcdefghij" * 5  # exactly 50 chars
    assert custom.needs_cleanup(varied_50 + ".txt") is False


# ---------------------------------------------------------------------------
# 16. Long Filename Truncation
# ---------------------------------------------------------------------------

def test_long_filename_truncation(cleanup, tmp_path):
    """Long filenames are intelligently truncated at word boundaries."""
    long_name = "This is a very long filename with many words " * 5
    fp = tmp_path / (long_name.strip() + ".txt")
    fp.write_text("test")

    result = cleanup.generate_clean_name(str(fp))
    name, ext = os.path.splitext(result)
    assert ext == ".txt"
    assert len(name) <= 80


# ---------------------------------------------------------------------------
# 17. Sanitize Name
# ---------------------------------------------------------------------------

def test_sanitize_name():
    """_sanitize_name removes unsafe chars and normalizes spacing."""
    assert FilenameCleanup._sanitize_name("hello  world") == "hello_world"
    assert FilenameCleanup._sanitize_name("test<>file") == "test_file"
    assert FilenameCleanup._sanitize_name("___leading___") == "leading"
    assert FilenameCleanup._sanitize_name('file:with"bad|chars') == "file_with_bad_chars"
    assert FilenameCleanup._sanitize_name("  spaced  out  ") == "spaced_out"
    assert FilenameCleanup._sanitize_name("normal_name") == "normal_name"


# ---------------------------------------------------------------------------
# 18. Missing Metadata Fallback
# ---------------------------------------------------------------------------

def test_missing_metadata_fallback(cleanup, tmp_path, monkeypatch):
    """When xattr raises errors, gracefully falls back to extension-based name."""
    def mock_getxattr_fail(path, attr):
        raise OSError("No xattr support")

    monkeypatch.setattr(os, "getxattr", mock_getxattr_fail)

    fp = tmp_path / "_.jpg"
    fp.write_text("test")
    result = cleanup.generate_clean_name(str(fp))
    assert result == "image.jpg"


# ---------------------------------------------------------------------------
# 19. Empty / Edge Case Filenames
# ---------------------------------------------------------------------------

def test_edge_case_filenames(cleanup):
    """Edge cases for needs_cleanup."""
    # os.path.splitext(".hidden") returns (".hidden", "") — name is ".hidden", not empty
    # ".hidden" has len=7, >= min_length, not generic, not digit -> False
    assert cleanup.needs_cleanup(".hidden") is False
    # Truly empty name part (whitespace before extension)
    assert cleanup.needs_cleanup(" .png") is True  # name is empty string after splitext and strip
    # Dots prefix with short name
    assert cleanup.needs_cleanup("..a.pdf") is True   # name is "..a", len=3 < min
    assert cleanup.needs_cleanup("  .txt") is True    # whitespace-only name after strip


# ---------------------------------------------------------------------------
# 20. Domain Extraction Edge Cases
# ---------------------------------------------------------------------------

def test_domain_extraction_edge_cases():
    """Edge cases for _domain_to_site_name."""
    # Invalid URLs
    assert FilenameCleanup._domain_to_site_name("") is None
    assert FilenameCleanup._domain_to_site_name("not-a-url") is None
    assert FilenameCleanup._domain_to_site_name("file:///local/path") is None

    # URL with IP address
    result = FilenameCleanup._domain_to_site_name("http://192.168.1.1/file")
    # IP addresses have numeric parts, should return None or a number
    # 192.168.1.1 -> parts[-2] = "1" which is < 2 chars, so None
    assert result is None

    # URL with single-part hostname (localhost)
    result = FilenameCleanup._domain_to_site_name("http://localhost/file")
    # "localhost" has no dots after www removal, parts has 1 element
    # Falls through to return None since len(parts) < 2
    assert result is None or result == "localhost"
