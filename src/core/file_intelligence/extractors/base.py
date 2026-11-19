"""Abstract base extractor and central extractor registry.

Defines the ``BaseExtractor`` interface that all format-specific content
extractors must implement, and the ``ExtractorRegistry`` for discovering
and dispatching extractors by file extension and MIME type.

Pure Python — zero Qt, zero network dependencies.
"""

from __future__ import annotations

import os
import math
import stat
import threading
from abc import ABC, abstractmethod
from typing import List, Optional

from src.core.file_intelligence.context import ExtractedMetadata
from src.core.file_intelligence.mime import DeterministicMime
from src.core.file_intelligence.privacy import normalize_metadata


class BaseExtractor(ABC):
    """Abstract base class for all file content extractors.

    Subclasses implement ``can_extract`` to declare supported file types
    and ``extract`` to produce an ``ExtractedMetadata`` result.  The
    ``extract`` method must never raise unhandled exceptions; errors are
    captured inside the returned ``ExtractedMetadata``.
    """

    #: Maximum raw text bytes read per file to bound memory footprint.
    MAX_TEXT_BYTES: int = 64 * 1024  # 64 KB

    #: Execution budget; concrete extractors define its enforcement.
    TIMEOUT_SECONDS: float = 3.0

    @abstractmethod
    def can_extract(self, extension: str, mime_type: str) -> bool:
        """Return ``True`` if this extractor can process the given file type.

        Parameters
        ----------
        extension:
            Lowercased file extension including the leading dot (e.g. ``".pdf"``).
        mime_type:
            MIME type string (e.g. ``"application/pdf"``).
        """

    @abstractmethod
    def extract(
        self,
        file_path: str,
        max_bytes: Optional[int] = None,
    ) -> ExtractedMetadata:
        """Extract metadata and bounded text from *file_path*.

        Must never raise unhandled exceptions.  Errors are captured in
        the returned ``ExtractedMetadata`` via ``extraction_status`` and
        ``error_message``.

        Parameters
        ----------
        file_path:
            Absolute or relative path to the target file.
        max_bytes:
            Optional non-negative integer read/sample limit. Each concrete
            extractor caps its own budget; text samples use ``MAX_TEXT_BYTES``.
        """


class ExtractorRegistry:
    """Central registry for discovering and dispatching content extractors.

    Maintains an ordered list of ``BaseExtractor`` instances.  The first
    extractor whose ``can_extract`` returns ``True`` for a given file is
    selected.
    """

    def __init__(self, cache=True) -> None:
        self._cache = cache
        self._cache_lock = threading.Lock()
        self._custom_registered = False
        self._extractors: List[BaseExtractor] = []
        self._register_default_extractors()

    def _register_default_extractors(self) -> None:
        """Register the built-in extractors that ship with Phase 3+."""
        # Import here to avoid circular imports.
        from src.core.file_intelligence.extractors.text import TextExtractor
        from src.core.file_intelligence.extractors.pdf import PdfExtractor
        from src.core.file_intelligence.extractors.docx import DocxExtractor
        from src.core.file_intelligence.extractors.pptx import PptxExtractor
        from src.core.file_intelligence.extractors.xlsx import XlsxExtractor
        from src.core.file_intelligence.extractors.image import ImageExtractor
        from src.core.file_intelligence.extractors.media import MediaExtractor
        from src.core.file_intelligence.extractors.code import CodeExtractor
        from src.core.file_intelligence.extractors.archive import ArchiveExtractor

        self._extractors.extend([
            TextExtractor(), PdfExtractor(), DocxExtractor(), PptxExtractor(), XlsxExtractor(),
            ImageExtractor(), MediaExtractor(), CodeExtractor(), ArchiveExtractor(),
        ])

    def register(self, extractor: BaseExtractor) -> None:
        """Append a custom extractor to the registry."""
        self._extractors.append(extractor)
        self._custom_registered = True

    def get_extractor(self, file_path: str) -> Optional[BaseExtractor]:
        """Return the first extractor that can handle *file_path*, or ``None``."""
        path = os.fsdecode(file_path).lower()
        ext = next((suffix for suffix in (".tar.gz", ".tar.bz2", ".tar.xz")
                    if path.endswith(suffix)), os.path.splitext(path)[1])
        mime_type = DeterministicMime.guess_mime(file_path)
        for extractor in self._extractors:
            if extractor.can_extract(ext, mime_type):
                return extractor
        return None

    @staticmethod
    def _identity(file_path):
        info = os.stat(file_path, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            return None
        return (info.st_ino, info.st_dev, info.st_mtime, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    def _metadata_cache(self):
        with self._cache_lock:
            if self._cache is True:
                from src.core.file_intelligence.cache import MetadataCache
                self._cache = MetadataCache()
            return self._cache if self._cache not in (False, None) else None

    def extract_metadata(self, file_path: str, *, timeout_seconds: Optional[float] = None) -> ExtractedMetadata:
        """Reuse unchanged successful built-in extraction before MIME/content I/O.

        Normal and process-bounded extraction use separate versioned namespaces.
        Runtime registrations bypass persistence. Failures, partial results and
        unsupported files are retried rather than cached. ``cache=False`` opts out.
        """
        # Preserve invalid-timeout behavior even when this file is already cached.
        if timeout_seconds is not None and (isinstance(timeout_seconds, bool) or
                not isinstance(timeout_seconds, (int, float)) or
                not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
            return self._extract_uncached(file_path, timeout_seconds=timeout_seconds)
        cache = identity = None
        namespace = 'extractors-v2:' + ('normal' if timeout_seconds is None else 'bounded')
        try:
            if not self._custom_registered:
                identity = self._identity(file_path)
                cache = self._metadata_cache() if identity is not None else None
            if cache is not None:
                inode, device, mtime, size, mtime_ns, ctime_ns = identity
                cached = cache.get(file_path, inode, mtime, size, device=device,
                                   mtime_ns=mtime_ns, ctime_ns=ctime_ns, namespace=namespace)
                if cached is not None and self._identity(file_path) == identity:
                    return normalize_metadata(cached)
        except Exception:
            cache = None
        # Normalize every return path, including disabled/unavailable caches and
        # partial results, before signals or persistence can observe the profile.
        result = normalize_metadata(self._extract_uncached(file_path, timeout_seconds=timeout_seconds))
        try:
            if cache is not None and self._identity(file_path) == identity:
                cache.put(file_path, inode, device, mtime, size, result,
                          mtime_ns=mtime_ns, ctime_ns=ctime_ns, namespace=namespace)
        except Exception:
            pass
        return result

    def _extract_uncached(self, file_path, *, timeout_seconds=None):
        """Original dispatch, including the bounded download worker boundary."""
        if timeout_seconds is not None:
            from src.core.file_intelligence.extractors.isolated import extract_metadata
            return extract_metadata(file_path, timeout_seconds)
        extractor = None
        try:
            extractor = self.get_extractor(file_path)
            if extractor is None:
                return ExtractedMetadata(
                    extractor_name="none",
                    extraction_status="UNSUPPORTED",
                )
            return extractor.extract(file_path)
        except Exception as e:
            return ExtractedMetadata(
                extractor_name=extractor.__class__.__name__ if extractor else "registry",
                extraction_status="FAILED",
                error_message=str(e),
            )
