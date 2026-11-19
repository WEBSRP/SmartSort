"""Pluggable content extractor registry for the File Intelligence Engine.

Exports the base extractor interface, the central registry, and the
text/Markdown, PDF, Office, image, media, code, and archive extractors with zero Qt
dependencies.
"""

from src.core.file_intelligence.extractors.base import (
    BaseExtractor,
    ExtractorRegistry,
)
from src.core.file_intelligence.extractors.text import TextExtractor
from src.core.file_intelligence.extractors.pdf import PdfExtractor
from src.core.file_intelligence.extractors.docx import DocxExtractor
from src.core.file_intelligence.extractors.pptx import PptxExtractor
from src.core.file_intelligence.extractors.xlsx import XlsxExtractor
from src.core.file_intelligence.extractors.image import ImageExtractor
from src.core.file_intelligence.extractors.media import MediaExtractor
from src.core.file_intelligence.extractors.code import CodeExtractor
from src.core.file_intelligence.extractors.archive import ArchiveExtractor

__all__ = [
    "BaseExtractor",
    "ExtractorRegistry",
    "TextExtractor",
    "PdfExtractor",
    "DocxExtractor",
    "PptxExtractor",
    "XlsxExtractor",
    "ImageExtractor",
    "MediaExtractor",
    "CodeExtractor",
    "ArchiveExtractor",
]
