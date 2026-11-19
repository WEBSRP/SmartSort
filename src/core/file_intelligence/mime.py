"""Deterministic MIME type detection for the File Intelligence Engine.

Provides consistent MIME type resolution based on file extension mapping
and binary magic byte prefix inspection. Pure Python with zero Qt or
network dependencies.
"""

from __future__ import annotations

import mimetypes
from typing import Optional


# ---------------------------------------------------------------------------
# Magic byte signatures (prefix → MIME type)
# ---------------------------------------------------------------------------

_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    # PDF
    (b"%PDF-", "application/pdf"),
    # PNG
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    # JPEG
    (b"\xff\xd8\xff", "image/jpeg"),
    # GIF87a / GIF89a
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    # BMP
    (b"BM", "image/bmp"),
    # TIFF (little-endian / big-endian)
    (b"II\x2a\x00", "image/tiff"),
    (b"MM\x00\x2a", "image/tiff"),
    # WebP (RIFF....WEBP)
    (b"RIFF", "image/webp"),  # requires secondary check for WEBP
    # ZIP-based (OOXML, JAR, etc.) — PK\x03\x04
    (b"PK\x03\x04", "application/zip"),
    # RAR
    (b"Rar!\x1a\x07", "application/x-rar-compressed"),
    # 7z
    (b"7z\xbc\xaf\x27\x1c", "application/x-7z-compressed"),
    # Gzip
    (b"\x1f\x8b", "application/gzip"),
    # Bzip2
    (b"BZh", "application/x-bzip2"),
    # XZ
    (b"\xfd7zXZ\x00", "application/x-xz"),
    # ELF
    (b"\x7fELF", "application/x-executable"),
    # WAV (RIFF....WAVE)
    # Note: WAV also starts with RIFF; handled via secondary check
    # MP3 (ID3 tag)
    (b"ID3", "audio/mpeg"),
    # MP3 (sync word)
    (b"\xff\xfb", "audio/mpeg"),
    (b"\xff\xf3", "audio/mpeg"),
    (b"\xff\xf2", "audio/mpeg"),
    # OGG
    (b"OggS", "audio/ogg"),
    # FLAC
    (b"fLaC", "audio/flac"),
    # SQLite
    (b"SQLite format 3\x00", "application/x-sqlite3"),
]

# Longest magic prefix we need to read
_MAX_MAGIC_LEN = max(len(sig) for sig, _ in _MAGIC_SIGNATURES)


# ---------------------------------------------------------------------------
# Extension → MIME mapping (supplements stdlib mimetypes)
# ---------------------------------------------------------------------------

_EXTENSION_MIME_MAP: dict[str, str] = {
    # Documents
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".rtf": "application/rtf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".rst": "text/x-rst",
    ".tex": "text/x-tex",
    ".latex": "text/x-tex",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".log": "text/plain",
    ".json": "application/json",
    ".xml": "application/xml",
    ".yaml": "application/x-yaml",
    ".yml": "application/x-yaml",
    ".toml": "application/toml",
    ".ini": "text/plain",
    ".cfg": "text/plain",
    ".conf": "text/plain",
    # Presentations
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    # Spreadsheets
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    # Images
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".ico": "image/x-icon",
    ".heic": "image/heic",
    ".heif": "image/heif",
    # Audio
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".wma": "audio/x-ms-wma",
    ".opus": "audio/opus",
    # Video
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".wmv": "video/x-ms-wmv",
    ".flv": "video/x-flv",
    ".webm": "video/webm",
    ".m4v": "video/mp4",
    ".3gp": "video/3gpp",
    # Archives
    ".zip": "application/zip",
    ".rar": "application/x-rar-compressed",
    ".7z": "application/x-7z-compressed",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".bz2": "application/x-bzip2",
    ".xz": "application/x-xz",
    ".zst": "application/zstd",
    # Packages / Disk images
    ".deb": "application/vnd.debian.binary-package",
    ".rpm": "application/x-rpm",
    ".appimage": "application/x-executable",
    ".iso": "application/x-iso9660-image",
    ".img": "application/x-raw-disk-image",
    # Executables / Scripts
    ".exe": "application/x-dosexec",
    ".msi": "application/x-msi",
    ".sh": "application/x-shellscript",
    ".bash": "application/x-shellscript",
    ".zsh": "application/x-shellscript",
    ".fish": "application/x-shellscript",
    # Code
    ".py": "text/x-python",
    ".pyw": "text/x-python",
    ".js": "text/javascript",
    ".ts": "text/typescript",
    ".jsx": "text/jsx",
    ".tsx": "text/tsx",
    ".java": "text/x-java",
    ".c": "text/x-c",
    ".h": "text/x-c",
    ".cpp": "text/x-c++",
    ".hpp": "text/x-c++",
    ".cs": "text/x-csharp",
    ".go": "text/x-go",
    ".rs": "text/x-rust",
    ".rb": "text/x-ruby",
    ".php": "text/x-php",
    ".swift": "text/x-swift",
    ".kt": "text/x-kotlin",
    ".scala": "text/x-scala",
    ".r": "text/x-r",
    ".R": "text/x-r",
    ".m": "text/x-matlab",
    ".sql": "application/sql",
    ".html": "text/html",
    ".htm": "text/html",
    ".css": "text/css",
    # Fonts
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    # Ebooks
    ".epub": "application/epub+zip",
    ".mobi": "application/x-mobipocket-ebook",
    # Misc data
    ".sqlite": "application/x-sqlite3",
    ".db": "application/x-sqlite3",
}


# ---------------------------------------------------------------------------
# Extension → category hint mapping
# ---------------------------------------------------------------------------

_CATEGORY_HINTS: dict[str, str] = {
    # Documents
    ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
    ".odt": "Documents", ".rtf": "Documents", ".txt": "Documents",
    ".md": "Documents", ".markdown": "Documents", ".rst": "Documents",
    ".tex": "Documents", ".latex": "Documents",
    ".csv": "Documents", ".tsv": "Documents", ".log": "Documents",
    ".epub": "Documents", ".mobi": "Documents",
    # Presentations
    ".ppt": "Documents", ".pptx": "Documents", ".odp": "Documents",
    # Spreadsheets
    ".xls": "Documents", ".xlsx": "Documents", ".ods": "Documents",
    # Images
    ".png": "Images", ".jpg": "Images", ".jpeg": "Images",
    ".gif": "Images", ".bmp": "Images", ".svg": "Images",
    ".webp": "Images", ".tiff": "Images", ".tif": "Images",
    ".ico": "Images", ".heic": "Images", ".heif": "Images",
    # Audio
    ".mp3": "Media", ".flac": "Media", ".wav": "Media",
    ".aac": "Media", ".ogg": "Media", ".m4a": "Media",
    ".wma": "Media", ".opus": "Media",
    # Video
    ".mp4": "Media", ".mkv": "Media", ".avi": "Media",
    ".mov": "Media", ".wmv": "Media", ".flv": "Media",
    ".webm": "Media", ".m4v": "Media", ".3gp": "Media",
    # Archives
    ".zip": "Archives", ".rar": "Archives", ".7z": "Archives",
    ".tar": "Archives", ".gz": "Archives", ".bz2": "Archives",
    ".xz": "Archives", ".zst": "Archives",
    # Packages
    ".deb": "Archives", ".rpm": "Archives", ".appimage": "Archives",
    ".iso": "Archives", ".img": "Archives",
    # Executables
    ".exe": "Applications", ".msi": "Applications",
    ".sh": "Code", ".bash": "Code", ".zsh": "Code", ".fish": "Code",
    # Code
    ".py": "Code", ".pyw": "Code", ".js": "Code", ".ts": "Code",
    ".jsx": "Code", ".tsx": "Code", ".java": "Code",
    ".c": "Code", ".h": "Code", ".cpp": "Code", ".hpp": "Code",
    ".cs": "Code", ".go": "Code", ".rs": "Code", ".rb": "Code",
    ".php": "Code", ".swift": "Code", ".kt": "Code", ".scala": "Code",
    ".r": "Code", ".R": "Code", ".m": "Code",
    ".sql": "Code", ".html": "Code", ".htm": "Code", ".css": "Code",
    # Data / Config
    ".json": "Code", ".xml": "Code", ".yaml": "Code", ".yml": "Code",
    ".toml": "Code", ".ini": "Code", ".cfg": "Code", ".conf": "Code",
    # Fonts
    ".ttf": "Others", ".otf": "Others", ".woff": "Others", ".woff2": "Others",
}


_CODE_FOLDERS = {
    **dict.fromkeys((".py", ".pyw"), "Python"),
    **dict.fromkeys((".sh", ".bash", ".zsh", ".fish"), "Shell"),
    **dict.fromkeys((".js", ".mjs", ".cjs", ".jsx"), "JavaScript"),
    **dict.fromkeys((".ts", ".tsx"), "TypeScript"),
    **dict.fromkeys((".c", ".h"), "C"),
    **dict.fromkeys((".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"), "C++"),
    ".java": "Java", ".go": "Go", ".rs": "Rust", ".cs": "CSharp",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin",
    ".kts": "Kotlin", ".scala": "Scala", ".sql": "SQL", ".r": "R",
    ".ps1": "PowerShell", ".bat": "Batch", ".cmd": "Batch",
    ".lua": "Lua", ".pl": "Perl", ".dart": "Dart",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "CSS",
}
_LANGUAGE_FOLDERS = {name.casefold(): name for name in _CODE_FOLDERS.values()}
_LANGUAGE_FOLDERS.update({"c#": "CSharp", "bash": "Shell", "zsh": "Shell", "fish": "Shell"})
_CATEGORY_HINTS.update({extension: "Code" for extension in _CODE_FOLDERS})


class DeterministicMime:
    """Deterministic MIME type resolution via extension mapping and magic bytes.

    Uses a curated extension-to-MIME dictionary as the primary lookup,
    falling back to binary magic byte prefix inspection and finally to
    the stdlib ``mimetypes`` module. No network or external service
    dependencies.
    """

    @staticmethod
    def guess_mime(file_path: str) -> str:
        """Determine the MIME type for *file_path*.

        Resolution order:
        1. Extension lookup in the curated ``_EXTENSION_MIME_MAP``.
        2. Binary magic byte prefix inspection (first ``_MAX_MAGIC_LEN``
           bytes of the file, if readable).
        3. Stdlib ``mimetypes.guess_type`` fallback.
        4. ``"application/octet-stream"`` if all else fails.
        """
        import os

        # 1. Extension lookup
        _, ext = os.path.splitext(file_path)
        ext_lower = ext.lower()
        if ext_lower in _EXTENSION_MIME_MAP:
            return _EXTENSION_MIME_MAP[ext_lower]

        # 2. Magic byte inspection (best-effort, never raise)
        try:
            with open(file_path, "rb") as fh:
                header = fh.read(_MAX_MAGIC_LEN)
            if header:
                # Special handling: RIFF container can be WAV or WEBP
                if header[:4] == b"RIFF" and len(header) >= 12:
                    four_cc = header[8:12]
                    if four_cc == b"WAVE":
                        return "audio/wav"
                    if four_cc == b"WEBP":
                        return "image/webp"

                for sig, mime in _MAGIC_SIGNATURES:
                    if header.startswith(sig):
                        return mime
        except (OSError, IOError):
            pass

        # 3. Stdlib fallback
        guessed, _ = mimetypes.guess_type(file_path, strict=False)
        if guessed:
            return guessed

        # 4. Default
        return "application/octet-stream"

    @staticmethod
    def get_category_hint(extension: str) -> str:
        """Return a primary category hint for *extension*.

        Returns one of: ``'Documents'``, ``'Images'``, ``'Media'``,
        ``'Archives'``, ``'Code'``, ``'Applications'``, or ``'Others'``.
        """
        ext_lower = extension.lower()
        return _CATEGORY_HINTS.get(ext_lower, "Others")

    @staticmethod
    def get_sorting_fallback(extension: str, mime_type: str = "") -> str:
        """Useful file-type destinations when semantic evidence is insufficient.

        Keep classifier hints separate: a known format is useful for routing,
        but is not proof of the document's subject or purpose.
        """
        extension = extension.lower()
        if extension in {".deb", ".rpm", ".appimage", ".apk", ".xapk", ".exe", ".msi", ".dmg", ".pkg"}:
            return "Applications"
        known_mime = _EXTENSION_MIME_MAP.get(extension, mime_type)
        if known_mime.startswith("video/"):
            return "Videos"
        if known_mime.startswith("audio/"):
            return "Audio"
        category = DeterministicMime.get_category_hint(extension)
        if category == "Others" and known_mime.startswith("image/"):
            return "Images"
        return category

    @staticmethod
    def get_code_folder(extension, code_language=None):
        """Use a fixed language vocabulary, never an arbitrary metadata path."""
        if isinstance(code_language, str):
            language = _LANGUAGE_FOLDERS.get(code_language.strip().casefold())
            if language:
                return language
        return _CODE_FOLDERS.get(extension.lower())

    @staticmethod
    def get_sorting_parts(extension, mime_type="", code_language=None):
        language = DeterministicMime.get_code_folder(extension, code_language)
        if language:
            return ("Code", language)
        return (DeterministicMime.get_sorting_fallback(extension, mime_type),)
