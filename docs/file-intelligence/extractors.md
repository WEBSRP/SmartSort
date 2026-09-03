# SmartSort File Intelligence Engine: Content Extractors

## 1. Overview & Base Extractor Interface

All format-specific content extractors inherit from `BaseExtractor`. Extractors must remain strictly **offline**, **thread-safe**, **bounded in memory and CPU**, and produce standardized `ExtractedMetadata` objects.

```python
from abc import ABC, abstractmethod
from typing import Optional
from src.core.file_intelligence.context import ExtractedMetadata

class BaseExtractor(ABC):
    """Abstract base class for all file content extractors."""

    # Maximum raw text bytes extracted per file to bound memory footprint
    MAX_TEXT_BYTES: int = 64 * 1024        # 64 KB
    # Maximum execution timeout per file
    TIMEOUT_SECONDS: float = 3.0

    @abstractmethod
    def can_extract(self, extension: str, mime_type: str) -> bool:
        """Returns True if this extractor can process the specified file type."""
        pass

    @abstractmethod
    def extract(self, file_path: str, max_bytes: Optional[int] = None) -> ExtractedMetadata:
        """
        Extracts metadata and bounded text from the target file.
        Must never raise unhandled exceptions; errors are captured in ExtractedMetadata.
        """
        pass
```

---

## 2. Format-Specific Extractor Specifications

### 2.1 Plain Text & Markdown (`text.py`)
- **Extensions**: `.txt`, `.md`, `.markdown`, `.rst`, `.log`, `.csv`, `.tsv`, `.json`, `.yaml`, `.yml`, `.xml`, `.html`, `.htm`
- **Implementation Library**: Standard Python `open()` with UTF-8 / Latin-1 encoding detection and chunked stream reading.
- **Extracted Fields**:
  - `title`: Extracted from `# Title` (Markdown) or first non-empty line.
  - `headings`: Markdown headings (`#`, `##`, `###`) or key section markers.
  - `text_preview`: First 1,024 characters.
  - `keywords`: High-frequency domain tokens stripped of common stop-words.
- **Boundaries**: Reads up to `MAX_TEXT_BYTES` (64 KB). Large log/CSV files are not loaded entirely into memory.
- **Failure Mode**: Encoding fallback (UTF-8 $\rightarrow$ Latin-1 $\rightarrow$ `errors='ignore'`). Returns `extraction_status="PARTIAL"` on decoding errors.

### 2.2 PDF Documents (`pdf.py`)
- **Extensions**: `.pdf`
- **Primary Library**: `pypdf` (`python3-pypdf` in Debian/Ubuntu).
- **Fallback Library**: Pure-Python raw PDF dictionary parsing (`/Title`, `/Author`, `/Subject`, `/Keywords`).
- **Extracted Fields**:
  - `title`: From `/Title` metadata or first page top-level heading.
  - `author`: From `/Author` metadata.
  - `subject`: From `/Subject` metadata.
  - `created_date`: From `/CreationDate`.
  - `headings`: Extracted from PDF Table of Contents (`outline`) or large font-size spans.
  - `text_preview`: Extracted from Page 1 (max 1024 chars).
  - `keywords`: From `/Keywords` or extracted from Page 1 text.
- **Boundaries**: Maximum 5 pages parsed for text extraction. Encrypted/password-protected PDFs cleanly report `extraction_status="ENCRYPTED"`.

### 2.3 Word Documents (`docx.py`)
- **Extensions**: `.docx`
- **Primary Library**: `python-docx` (`python3-docx`).
- **Fallback Library**: Standard `zipfile` reading `docProps/core.xml` and `word/document.xml` using `xml.etree.ElementTree`.
- **Extracted Fields**:
  - `title`: From `core.xml` `dc:title` or Paragraph with `Style="Heading 1"` or `"Title"`.
  - `author`: From `core.xml` `dc:creator`.
  - `subject`: From `core.xml` `dc:subject`.
  - `headings`: Paragraphs styled as `Heading 1`, `Heading 2`, `Heading 3`.
  - `text_preview`: First 1,024 characters across leading paragraphs.
- **Boundaries**: Max 20 paragraphs extracted.

### 2.4 PowerPoint Presentations (`pptx.py`)
- **Extensions**: `.pptx`
- **Primary Library**: `zipfile` reading `docProps/core.xml` and `ppt/slides/slide*.xml` (or `python3-pptx` if installed).
- **Extracted Fields**:
  - `title`: From `core.xml` `dc:title` or title placeholder on Slide 1.
  - `author`: From `core.xml` `dc:creator`.
  - `headings`: Titles extracted across Slide 1 to Slide 5.
  - `text_preview`: Combined slide titles and bullet points from first 3 slides.
- **Boundaries**: Max 5 slides parsed.

### 2.5 Excel Spreadsheets (`xlsx.py`)
- **Extensions**: `.xlsx`
- **Primary Library**: `openpyxl` (`python3-openpyxl`) or `zipfile` reading `docProps/core.xml` and `xl/workbook.xml`.
- **Extracted Fields**:
  - `title`: From `core.xml` `dc:title` or first Sheet name.
  - `headings`: Sheet names (e.g. `['Q3_Financials', 'Summary', 'Charts']`) and column headers from Row 1.
  - `text_preview`: Comma-delimited list of Sheet names and Table headers.
- **Boundaries**: Reads metadata and headers only. Cell data beyond row 5 is ignored.

### 2.6 Images & EXIF (`image.py`)
- **Extensions**: `.jpg`, `.jpeg`, `.png`, `.webp`, `.tiff`, `.tif`, `.svg`
- **Primary Library**: `Pillow` (`python3-pil`) with EXIF tag dictionary mapping.
- **Fallback Library**: Pure-Python binary header inspection (JPEG SOF/EXIF markers, PNG IHDR chunk).
- **Extracted Fields**:
  - `dimensions`: Width $\times$ Height in pixels.
  - `created_date`: From EXIF `DateTimeOriginal` or `CreateDate`.
  - `exif_tags`: Camera Make/Model (`Make`, `Model`), Software (`Software`), Lens (`LensModel`).
  - `keywords`: Software tags (e.g. `"Blender"`, `"Adobe Photoshop"`, `"GIMP"`, `"Inkscape"`).
- **Privacy Rule**: GPS coordinates (`GPSInfo`) are **never persisted or logged** in `FileContext` or Markdown reports to safeguard user privacy.

### 2.7 Audio & Video Media (`media.py`)
- **Extensions**: `.mp3`, `.flac`, `.wav`, `.ogg`, `.m4a`, `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`
- **Primary Library**: `mutagen` (`python3-mutagen`).
- **Fallback Library**: Binary header parser for ID3v2 (MP3), Vorbis comments (OGG/FLAC), and MP4 `moov`/`udta` atoms.
- **Extracted Fields**:
  - `title`: Track title / Video name.
  - `author`: Artist / Performer / Author.
  - `subject`: Album / Series.
  - `duration_seconds`: Track duration in seconds.
  - `keywords`: Genre, encoder, codec.

### 2.8 Source Code & Scripts (`code.py`)
- **Extensions**: `.py`, `.c`, `.cpp`, `.h`, `.hpp`, `.java`, `.js`, `.ts`, `.go`, `.rs`, `.sh`, `.bash`, `.sql`, `.html`, `.css`, `.php`
- **Implementation**: Pure Python token analysis and regex symbol extraction.
- **Extracted Fields**:
  - `code_language`: Detected language based on extension and shebang (`#!/usr/bin/env python3`).
  - `code_symbols`: Extracted function definitions (`def `, `function `, `fn `), class definitions (`class `), and import statements (`import `, `#include `, `use `).
  - `headings`: Section header comments (e.g. `// --- Database Configuration ---`).
  - `text_preview`: Module/file docstring or top block comment.
- **Boundaries**: Max 200 lines scanned.

### 2.9 Archives & Compressed Bundles (`archive.py`)
- **Extensions**: `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`, `.7z`
- **Implementation**: Standard library `zipfile`, `tarfile`.
- **Extracted Fields**:
  - `toc_entries`: Table of contents (list of internal member file paths).
  - `headings`: Top-level internal directory names.
  - `keywords`: Inferred content types (e.g. if archive contains `.pptx` and `.pdf` files, keywords include `presentation`, `document`, `course_material`).
- **Security Constraint (Zip Bomb Prevention)**: Max 500 member headers read; member files are **never decompressed to disk** during metadata extraction.

---

## 3. Extractor Dispatch Registry

```python
class ExtractorRegistry:
    """Central registry for discovering and dispatching extractors."""

    def __init__(self):
        self._extractors: List[BaseExtractor] = []
        self._register_default_extractors()

    def register(self, extractor: BaseExtractor):
        self._extractors.append(extractor)

    def get_extractor(self, file_path: str) -> Optional[BaseExtractor]:
        ext = os.path.splitext(file_path)[1].lower()
        mime_type = DeterministicMime.guess_mime(file_path)
        for extractor in self._extractors:
            if extractor.can_extract(ext, mime_type):
                return extractor
        return None

    def extract_metadata(self, file_path: str) -> ExtractedMetadata:
        extractor = self.get_extractor(file_path)
        if not extractor:
            return ExtractedMetadata(
                extractor_name="none",
                extraction_status="UNSUPPORTED"
            )
        try:
            return extractor.extract(file_path)
        except Exception as e:
            return ExtractedMetadata(
                extractor_name=extractor.__class__.__name__,
                extraction_status="FAILED",
                error_message=str(e)
            )
```
