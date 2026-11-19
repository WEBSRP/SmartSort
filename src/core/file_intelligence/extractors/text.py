"""Text, Markdown, and plain document content extractor.

Extracts title, headings, text preview, and keyword tokens from plaintext,
Markdown, CSV, log, and structured text files.  Uses multi-encoding
detection (UTF-8 → Latin-1 → errors='ignore') and bounded reading
(default 64 KB) to guarantee safe, fast extraction.

Pure Python — zero third-party dependencies, zero Qt, zero network.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import FrozenSet, List, Optional

from src.core.file_intelligence.context import ExtractedMetadata
from src.core.file_intelligence.extractors.base import BaseExtractor
from src.core.file_intelligence.privacy import redact_url_text


# ---------------------------------------------------------------------------
# Stop-words (common English words stripped from keyword extraction)
# ---------------------------------------------------------------------------

_STOP_WORDS: FrozenSet[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "as", "be", "was", "were",
    "are", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "may", "might", "must", "can",
    "could", "not", "no", "nor", "so", "if", "then", "than", "that",
    "this", "these", "those", "i", "me", "my", "we", "our", "you",
    "your", "he", "him", "his", "she", "her", "they", "them", "their",
    "its", "what", "which", "who", "whom", "how", "when", "where", "why",
    "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "only", "own", "same", "just", "also", "very",
    "about", "up", "out", "into", "over", "after", "before", "between",
    "under", "again", "further", "here", "there", "once", "during",
    "while", "too", "any", "above", "below", "through", "s", "t", "re",
    "don", "doesn", "didn", "won", "wouldn", "shouldn", "couldn", "ve",
    "ll", "d", "m", "o", "ain", "aren", "hasn", "haven", "isn", "wasn",
    "weren", "needn", "shan", "now",
})

# Markdown heading pattern: lines starting with 1-6 '#' followed by space
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

# Word token pattern for keyword extraction
_WORD_TOKEN_RE = re.compile(r"[a-zA-Z]{2,}")


class TextExtractor(BaseExtractor):
    """Extractor for plaintext, Markdown, and structured text files.

    Supports 13 text-based extensions.  Reads at most ``MAX_TEXT_BYTES``
    (64 KB by default) to bound memory usage on large log/CSV files.
    """

    SUPPORTED_EXTENSIONS: FrozenSet[str] = frozenset([
        ".txt", ".md", ".markdown", ".rst", ".log", ".csv",
        ".tsv", ".json", ".yaml", ".yml", ".xml", ".html", ".htm",
    ])

    # Extensions treated as Markdown for heading/title extraction
    _MARKDOWN_EXTENSIONS: FrozenSet[str] = frozenset([
        ".md", ".markdown",
    ])

    def can_extract(self, extension: str, mime_type: str) -> bool:
        """Return ``True`` if *extension* is in the supported set."""
        return extension.lower() in self.SUPPORTED_EXTENSIONS

    def extract(
        self,
        file_path: str,
        max_bytes: Optional[int] = None,
    ) -> ExtractedMetadata:
        """Extract metadata from a text/Markdown file.

        Parameters
        ----------
        file_path:
            Path to the target text file.
        max_bytes:
            Non-negative integer read limit, capped at ``MAX_TEXT_BYTES``.
            Defaults to ``MAX_TEXT_BYTES``; zero produces an empty sample.

        Returns
        -------
        ExtractedMetadata
            Populated with ``title``, ``headings``, ``text_preview``,
            and ``keywords``.  ``extraction_status`` is ``"SUCCESS"``
            on full extraction, ``"PARTIAL"`` on encoding fallback,
            or ``"FAILED"`` on I/O errors.
        """
        try:
            if max_bytes is not None and (
                isinstance(max_bytes, bool)
                or not isinstance(max_bytes, int)
                or max_bytes < 0
            ):
                raise ValueError("max_bytes must be a non-negative integer or None")
            limit = self.MAX_TEXT_BYTES if max_bytes is None else min(
                max_bytes, self.MAX_TEXT_BYTES
            )
            raw_bytes = self._read_bounded(file_path, limit)
        except (OSError, ValueError, TypeError) as e:
            return ExtractedMetadata(
                extractor_name="TextExtractor",
                extraction_status="FAILED",
                error_message=str(e),
            )

        text, status = self._decode_bytes(raw_bytes)
        text = redact_url_text(text)

        # Determine whether this is Markdown
        ext = os.path.splitext(file_path)[1].lower()
        is_markdown = ext in self._MARKDOWN_EXTENSIONS

        # Extract structured data
        headings = self._extract_headings(text) if is_markdown else []
        title = self._extract_title(text, headings, is_markdown)
        text_preview = text[:1024]
        keywords = self._extract_keywords(text)

        return ExtractedMetadata(
            title=title,
            headings=headings,
            text_preview=text_preview,
            keywords=keywords,
            extractor_name="TextExtractor",
            extraction_status=status,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_bounded(file_path: str, max_bytes: int) -> bytes:
        """Read at most *max_bytes* from *file_path*.

        Raises ``FileNotFoundError``, ``PermissionError``, or ``OSError``
        on I/O failure.
        """
        with open(file_path, "rb") as fh:
            return fh.read(max_bytes)

    @staticmethod
    def _decode_bytes(raw: bytes) -> tuple:
        """Decode *raw* bytes using the multi-encoding fallback chain.

        Returns ``(text, status)`` where *status* is ``"SUCCESS"`` for
        clean UTF-8, ``"PARTIAL"`` for fallback decoding.
        """
        # Strip UTF-8 BOM if present
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]

        # Try UTF-8 strict
        try:
            return raw.decode("utf-8"), "SUCCESS"
        except UnicodeDecodeError:
            pass

        # Try Latin-1 (never raises, accepts any byte)
        try:
            return raw.decode("latin-1"), "PARTIAL"
        except Exception:
            pass

        # Final fallback: UTF-8 with errors='ignore'
        return raw.decode("utf-8", errors="ignore"), "PARTIAL"

    @staticmethod
    def _extract_headings(text: str) -> List[str]:
        """Extract Markdown headings from *text*.

        Returns a list of heading text strings (without the ``#`` prefix).
        """
        headings: List[str] = []
        for line in text.splitlines():
            m = _MD_HEADING_RE.match(line)
            if m:
                headings.append(m.group(2).strip())
        return headings

    @staticmethod
    def _extract_title(
        text: str,
        headings: List[str],
        is_markdown: bool,
    ) -> Optional[str]:
        """Extract a title from *text*.

        For Markdown: uses the first ``# Heading`` (level-1) if present.
        For plaintext: uses the first non-empty line.
        Returns ``None`` if no title can be determined.
        """
        if is_markdown and headings:
            for line in text.splitlines():
                match = _MD_HEADING_RE.match(line)
                if match and match.group(1) == "#":
                    return match.group(2).strip()[:256]

        # Fallback: first non-empty line
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                # Cap title length to a reasonable bound
                return stripped[:256]
        return None

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """Extract high-frequency domain tokens, stripping stop-words.

        Returns the top 20 keywords by frequency, lowercased.
        """
        tokens = _WORD_TOKEN_RE.findall(redact_url_text(text).lower())
        filtered = [t for t in tokens if t not in _STOP_WORDS]

        if not filtered:
            return []

        counter = Counter(filtered)
        return [word for word, _ in counter.most_common(20)]
