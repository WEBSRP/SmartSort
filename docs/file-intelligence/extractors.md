# SmartSort File Intelligence Engine: Content Extractors


Phase 17 adds private XDG SQLite caching of successful extraction and corroborated
origins, with identity and provenance invalidation. See the
[cache implementation notes](phases/phase-17-caching-performance.md) for API,
privacy, retention and performance limits.

## 1. Overview & Base Extractor Interface

All format-specific content extractors inherit from `BaseExtractor`. Extractors must remain strictly **offline**, **thread-safe**, **bounded in memory and CPU**, and produce standardized `ExtractedMetadata` objects.

**Current implementation boundary (Phase 06):** Text reads have a hard 64 KB
cap. The PDF extractor enforces its three-second budget in a separate worker
with Linux resource limits. The text extractor's timeout constant remains
advisory; Office extractors share a 500 KiB streaming XML budget with cooperative
deadline checks. The registry does not impose a deadline on arbitrary custom
extractors. Image/media header readers enforce a shared 64 KiB cumulative read
budget across native and optional-library parsing, with cooperative deadlines.

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
- **Read-limit API**: `max_bytes` may lower this budget, never increase it.
  Negative values, booleans, and non-integers return `FAILED`; zero yields an
  empty sample. Titles are capped at 256 characters. For Markdown, the first
  level-one heading takes precedence over earlier subheadings; without a
  level-one heading, the first non-empty line is used.
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
- **Current implementation**: Uses a fresh parser worker, a three-second
  timeout, and a 512 MiB address-space cap. Text sampling is limited to 64 KiB
  of UTF-8 data, with a 1,024-character preview, at most 64 outline headings,
  20 keywords, and 256-character title/author/subject fields. Metadata dates
  retain bounded raw PDF date strings. Deadline expiration returns `TIMEOUT`.
- **Fallback limits**: Recovers classic trailer `/Info` strings from at most
  1 MiB of head/tail data. Results are `PARTIAL`; page text, compressed object
  streams, and XMP-only metadata are not supported by the fallback. No OCR is
  performed by either backend. The per-phase report records validation and
  the outstanding latency target.

### 2.3 Word Documents (`docx.py`)
- **Extensions**: `.docx`, `.odt`; `.doc` and `.rtf` return explicit partial results.
- **Implementation**: Standard `zipfile` and streaming `xml.etree.ElementTree`,
  reading `docProps/core.xml` and `word/document.xml`, or OpenDocument
  `meta.xml` and `content.xml`. `python-docx` is not required.
- **Extracted Fields**:
  - `title`: From `core.xml` `dc:title` or Paragraph with `Style="Heading 1"` or `"Title"`.
  - `author`: From `core.xml` `dc:creator`.
  - `subject`: From `core.xml` `dc:subject`.
  - `headings`: Paragraphs styled as `Heading 1`, `Heading 2`, `Heading 3`.
  - `text_preview`: First 1,024 characters across leading paragraphs.
- **Boundaries**: Max 20 paragraphs extracted.

### 2.4 PowerPoint Presentations (`pptx.py`)
- **Extensions**: `.pptx`, `.odp`; `.ppt` returns an explicit partial result.
- **Implementation**: Standard-library ZIP/XML inspection in presentation
  relationship order, with numeric slide filename fallback for minimal packages.
  OpenDocument presentation content is inspected directly as XML.
- **Extracted Fields**:
  - `title`: From `core.xml` `dc:title` or title placeholder on Slide 1.
  - `author`: From `core.xml` `dc:creator`.
  - `headings`: Titles extracted across Slide 1 to Slide 5.
  - `text_preview`: Combined slide titles and bullet points from first 3 slides.
- **Boundaries**: Max 5 slides parsed.

### 2.5 Excel Spreadsheets (`xlsx.py`)
- **Extensions**: `.xlsx`, `.ods`; `.xls` returns an explicit partial result.
- **Implementation**: Standard-library ZIP/XML inspection of properties,
  workbook/sheet relationships, inline/shared strings, and cached header values.
  OpenDocument spreadsheet headers are also supported. `openpyxl` is not required.
- **Extracted Fields**:
  - `title`: From `core.xml` `dc:title` or first Sheet name.
  - `headings`: Sheet names (e.g. `['Q3_Financials', 'Summary', 'Charts']`) and column headers from Row 1.
  - `text_preview`: Comma-delimited list of Sheet names and Table headers.
- **Boundaries**: Up to 32 sheet names and 64 first-row cells per sheet. Body
  rows are omitted; formulas are never evaluated.

**Shared Office boundaries:** `_office.py` enforces a 500 KiB total decompressed
XML budget and bounded text/metadata outputs. DTD/entity declarations, unsafe
relationship targets, and oversized ZIP indexes are rejected or reported as
partial inspection. No ZIP members are written to disk. Compound-binary
containers and unsupported legacy formats return `PARTIAL`, rather than
invented metadata. See the Phase 05 report for tests, timing, and limitations.

### 2.6 Images & EXIF (`image.py`)
- **Extensions**: `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`, `.tiff`, `.tif`, `.svg`
- **Primary Library**: `Pillow` (`python3-pil`) with EXIF tag dictionary mapping.
- **Fallback Library**: Pure-Python binary header inspection (JPEG SOF/EXIF markers, PNG IHDR chunk).
- **Extracted Fields**:
  - `dimensions`: Width $\times$ Height in pixels.
  - `created_date`: From EXIF `DateTimeOriginal` or `CreateDate`.
  - `exif_tags`: Camera Make/Model (`Make`, `Model`), Software (`Software`), Lens (`LensModel`).
  - `keywords`: Software tags (e.g. `"Blender"`, `"Adobe Photoshop"`, `"GIMP"`, `"Inkscape"`).
- **Privacy Rule**: GPS coordinates (`GPSInfo`) are **never persisted or logged** in `FileContext` or Markdown reports to safeguard user privacy.
- **Current implementation**: EXIF fields are explicitly allowlisted; native
  IFD parsing handles both byte orders and never follows the GPS IFD. PNG
  EXIF lookup avoids implicit pixel loads, while WebP/SVG remain on native
  header-only paths. No source image is rewritten or rasterized. See Phase 06
  for exact fallback coverage, read limits, and first-use latency observations.

### 2.7 Audio & Video Media (`media.py`)
- **Extensions**: `.mp3`, `.flac`, `.wav`, `.ogg`, `.m4a`, `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.wmv`
- **Primary Library**: `mutagen` (`python3-mutagen`).
- **Fallback Library**: Binary header parser for ID3v2 (MP3), Vorbis comments (OGG/FLAC), and MP4 `moov`/`udta` atoms.
- **Extracted Fields**:
  - `title`: Track title / Video name.
  - `author`: Artist / Performer / Author.
  - `subject`: Album / Series.
  - `duration_seconds`: Track duration in seconds.
  - `keywords`: Genre, encoder, codec.
- **Current implementation**: Allowlisted Mutagen tags plus bounded native
  ID3, MP4/MOV, WAV/AVI, and FLAC header parsing. Large artwork and payload
  atoms are skipped. Unknown/unsupported streams and missing backends return
  explicit partial results. Private/location tags and raw backend diagnostics
  are excluded from output; durations are finite and non-negative. Full codec
  support and a universal hard timeout are not provided by this phase.

### 2.8 Source Code & Scripts (`code.py`)
- **Implemented extensions**: `.py`, `.c`, `.cpp`, `.h`, `.hpp`, `.java`, `.js`, `.ts`, `.go`, `.rs`, `.sh`, `.bash`, `.sql`, `.php`. HTML remains with `TextExtractor`; CSS analysis is not implemented in Phase 07.
- **Implementation**: Pure Python token analysis and regex symbol extraction.
- **Extracted Fields**:
  - `code_language`: Detected language based on extension and shebang (`#!/usr/bin/env python3`).
  - `code_symbols`: Extracted function definitions (`def `, `function `, `fn `), class definitions (`class `), and import statements (`import `, `#include `, `use `).
  - `headings`: Section header comments (e.g. `// --- Database Configuration ---`).
  - `text_preview`: Module/file docstring or top block comment.
- **Boundaries**: Max 200 lines scanned.
- **Current implementation**: Reads at most 64 KiB from regular files, masks
  strings/comments before matching symbols, and recognizes supported shebangs.
  Source is never executed or imported. Leading docstrings/comments form the
  preview; section comments form headings. Limits: 128 unique symbols, 64
  headings, 20 keywords, 256-character titles/symbols/headings, and a
  1,024-character preview. Sampling/encoding fallback/symbol-cap results are
  `PARTIAL`. This is lexical inspection, not complete language parsing.

### 2.9 Archives & Compressed Bundles (`archive.py`)
- **Extensions**: `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`, `.7z`
- **Implementation**: Sequential classic ZIP central-directory parsing and
  incremental `tarfile` inspection, with bounded standard-library gzip, bz2,
  and XZ decoding. `ZipFile.infolist()` and `TarFile.getmembers()` are avoided
  because they materialize all records before an output limit can be applied.
- **Extracted Fields**:
  - `toc_entries`: Table of contents (list of internal member file paths).
  - `headings`: Top-level internal directory names.
  - `keywords`: Inferred content types (e.g. if archive contains `.pptx` and `.pdf` files, keywords include `presentation`, `document`, `course_material`).
- **Security Constraint (Zip Bomb Prevention)**: Max 500 member headers read; member files are **never decompressed to disk** during metadata extraction.
- **Current boundaries**: At most 500 listed members; auxiliary TAR headers
  also consume the byte budget. Input reads and decoded TAR scanning are each
  limited to 2 MiB; `max_bytes` may lower these limits. XZ dictionary memory is
  limited to 32 MiB. Names are capped at 1,024 characters; unsafe names are
  skipped. ZIP payloads/codecs are never opened, and TAR links are never followed.
  Compressed TAR may require decoding intervening payload bytes in memory to
  reach later headers and can return a partial listing when its budget runs out.
- **Status/coverage**: Inspected encrypted ZIP flags return `ENCRYPTED`;
  malformed inspected structures return `CORRUPTED`. 7z, ZIP64 directories,
  and multi-volume ZIP return explicit `PARTIAL` results. Deadlines are
  cooperative. Listings do not establish payload/CRC integrity. See Phase 07
  for validation, exact coverage, and timing observations.

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
        path = os.fsdecode(file_path).lower()
        ext = next((suffix for suffix in (".tar.gz", ".tar.bz2", ".tar.xz")
                    if path.endswith(suffix)), os.path.splitext(path)[1])
        mime_type = DeterministicMime.guess_mime(file_path)
        for extractor in self._extractors:
            if extractor.can_extract(ext, mime_type):
                return extractor
        return None

    def extract_metadata(self, file_path: str) -> ExtractedMetadata:
        extractor = None
        try:
            extractor = self.get_extractor(file_path)
            if extractor is None:
                return ExtractedMetadata(
                    extractor_name="none",
                    extraction_status="UNSUPPORTED"
                )
            return extractor.extract(file_path)
        except Exception as e:
            return ExtractedMetadata(
                extractor_name=extractor.__class__.__name__ if extractor else "registry",
                extraction_status="FAILED",
                error_message=str(e)
            )
```
