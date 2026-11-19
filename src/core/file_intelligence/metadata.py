"""Filesystem metadata extraction and FileContext construction.

Provides ``FileContextBuilder`` for initializing a ``FileContext`` from
a filesystem path, collecting stat attributes, MIME type, and optionally
a SHA-256 hash. Pure Python with zero Qt or network dependencies.
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, Optional

from src.core.file_intelligence.context import (
    ExtractedMetadata,
    FileContext,
    OriginInfo,
)
from src.core.file_intelligence.mime import DeterministicMime
from src.utils.file_utils import FileUtils


class FileMetadataExtractor:
    """Pure filesystem metadata helpers used during initial context building."""

    ORIGIN_XATTRS = (
        "user.xdg.origin.url",
        "user.xdg.referrer.url",
    )

    @staticmethod
    def read_xattr(file_path: str, attr_name: str) -> Optional[str]:
        """Read a UTF-8 extended attribute, returning ``None`` if unavailable."""
        try:
            raw_value = os.getxattr(file_path, attr_name.encode("utf-8"))
        except (AttributeError, OSError, ValueError):
            return None

        try:
            value = raw_value.decode("utf-8", errors="ignore").strip()
        except (AttributeError, UnicodeDecodeError):
            return None

        return value or None

    @classmethod
    def read_extended_attributes(
        cls,
        file_path: str,
        attr_names: Optional[Iterable[str]] = None,
    ) -> Dict[str, str]:
        """Read selected extended attributes without raising on unsupported filesystems."""
        names = attr_names if attr_names is not None else cls.ORIGIN_XATTRS
        attributes: Dict[str, str] = {}
        for attr_name in names:
            value = cls.read_xattr(file_path, attr_name)
            if value:
                attributes[attr_name] = value
        return attributes

    @classmethod
    def extract_origin_from_xattrs(cls, file_path: str) -> OriginInfo:
        """Populate minimal origin evidence from local xattrs only."""
        attributes = cls.read_extended_attributes(file_path)
        from src.core.file_intelligence.origin import origin_from_url
        for attr_name in cls.ORIGIN_XATTRS:
            url = attributes.get(attr_name)
            if url:
                origin = origin_from_url(url, detail=f"Read {attr_name} extended attribute")
                if origin.url:
                    return origin
        return OriginInfo()

    @staticmethod
    def _strip_url_query_and_fragment(url: str) -> str:
        """Remove query strings and fragments before storing URL evidence."""
        from src.core.file_intelligence.origin import origin_from_url
        return origin_from_url(url).url


class FileContextBuilder:
    """Constructs an initialized ``FileContext`` from a filesystem path.

    Performs ``os.stat``, canonical path resolution, MIME detection,
    and optional SHA-256 hashing. Does **not** extract document content,
    origin provenance, or perform classification — those are handled by
    later pipeline phases.
    """

    @staticmethod
    def build_initial_context(
        file_path: str,
        compute_hash: bool = False,
        *,
        read_origin_xattrs: bool = True,
    ) -> FileContext:
        """Create a ``FileContext`` populated with filesystem metadata.

        Parameters
        ----------
        file_path:
            Path to the target file (absolute or relative).
        compute_hash:
            If ``True``, compute and store the SHA-256 hash. Deferred by
            default for performance.
        read_origin_xattrs:
            Keep the legacy xattr-only origin probe by default. Batch pipelines
            can disable it when delegating provenance to a configured detector.

        Returns
        -------
        FileContext
            An initialized context with identity, filesystem, and MIME
            fields populated.

        Raises
        ------
        ValueError
            If the file does not exist (wraps ``FileNotFoundError``
            with path context).
        """
        # Canonical path resolution
        canonical = os.path.abspath(os.path.realpath(file_path))

        # --- Existence check ---
        if not os.path.exists(canonical):
            raise ValueError(
                f"File not found: {file_path!r} "
                f"(resolved to {canonical!r})"
            )

        # --- Permission-safe stat ---
        try:
            stat_result = os.stat(canonical)
        except PermissionError:
            # Return a minimal FileContext with error status
            filename = os.path.basename(canonical)
            stem, ext = os.path.splitext(filename)
            meta = ExtractedMetadata(
                extractor_name="filesystem",
                extraction_status="PERMISSION_DENIED",
                error_message=f"Permission denied: {canonical!r}",
            )
            return FileContext(
                path=canonical,
                filename=filename,
                stem=stem,
                extension=ext,
                mime_type="application/octet-stream",
                size_bytes=0,
                created_timestamp=0.0,
                modified_timestamp=0.0,
                inode=0,
                device=0,
                metadata=meta,
            )

        # --- Identity ---
        filename = os.path.basename(canonical)
        stem, ext = os.path.splitext(filename)

        # --- MIME type ---
        mime_type = DeterministicMime.guess_mime(canonical)

        # --- Optional SHA-256 ---
        sha256: Optional[str] = None
        if compute_hash:
            sha256 = FileUtils.calculate_sha256(canonical)

        # --- Metadata stub ---
        meta = ExtractedMetadata(
            extractor_name="filesystem",
            extraction_status="SUCCESS",
        )
        origin = FileMetadataExtractor.extract_origin_from_xattrs(canonical) if read_origin_xattrs else OriginInfo()

        return FileContext(
            path=canonical,
            filename=filename,
            stem=stem,
            extension=ext,
            mime_type=mime_type,
            size_bytes=stat_result.st_size,
            created_timestamp=stat_result.st_ctime,
            modified_timestamp=stat_result.st_mtime,
            inode=stat_result.st_ino,
            device=stat_result.st_dev,
            sha256_hash=sha256,
            metadata=meta,
            origin=origin,
        )
