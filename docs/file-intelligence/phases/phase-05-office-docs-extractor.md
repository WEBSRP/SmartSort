# Phase 05: Office Document Extractors (DOCX, PPTX, XLSX)

## Objective
Implement Office document extractors for Word (`docx.py`), PowerPoint (`pptx.py`), and Excel (`xlsx.py`) in `src/core/file_intelligence/extractors/` supporting modern OOXML formats and legacy document metadata.

## Why This Phase Exists
Presentations (`.pptx`), lecture notes (`.docx`), and spreadsheets (`.xlsx`) are staple formats in academic and work environments. Extracting presentation titles (e.g. "Lecture 4: Database Transactions") and document properties provides critical signals for subcategory classification.

## Inputs
- Office document paths (`.docx`, `.pptx`, `.xlsx`, `.odt`, `.odp`, `.ods`).

## Outputs
- `src/core/file_intelligence/extractors/docx.py` (`DocxExtractor`).
- `src/core/file_intelligence/extractors/pptx.py` (`PptxExtractor`).
- `src/core/file_intelligence/extractors/xlsx.py` (`XlsxExtractor`).
- Tests in `tests/test_file_intelligence/test_extractors_office.py`.

## Files To Create
- `src/core/file_intelligence/extractors/_office.py`: Shared ZIP/XML budget,
  package relationships, core properties, and error handling for this phase.
- `src/core/file_intelligence/extractors/docx.py`
- `src/core/file_intelligence/extractors/pptx.py`
- `src/core/file_intelligence/extractors/xlsx.py`
- `tests/test_file_intelligence/test_extractors_office.py`

## Files To Modify
- `src/core/file_intelligence/extractors/__init__.py`: Export the three extractors.
- `src/core/file_intelligence/extractors/base.py`: Register the three extractors
  in `ExtractorRegistry._register_default_extractors()`.

## Existing Components To Reuse
- `src/core/file_intelligence/extractors/base.py`: Inherits `BaseExtractor`.

## APIs / Interfaces
```python
# src/core/file_intelligence/extractors/docx.py
class DocxExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([".docx", ".doc", ".odt", ".rtf"])
    ...

# src/core/file_intelligence/extractors/pptx.py
class PptxExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([".pptx", ".ppt", ".odp"])
    ...

# src/core/file_intelligence/extractors/xlsx.py
class XlsxExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([".xlsx", ".xls", ".ods"])
    ...
```

## Data Structures
- Produces `ExtractedMetadata` populated with `title`, `author`, `headings`, `text_preview`.

## Algorithms
- OOXML Zip Parsing with `xml.etree.ElementTree`:
  - Read `docProps/core.xml` for `dc:title`, `dc:creator`, `dc:subject`.
  - `DocxExtractor`: Read `word/document.xml` for leading paragraphs and heading styles.
  - `PptxExtractor`: Inspect `ppt/slides/slide1.xml` to `slide5.xml` for slide titles (`<a:t>` tags inside title shape elements).
  - `XlsxExtractor`: Inspect `xl/workbook.xml` for sheet names and table headers.

## Error Handling
- Corrupted zip archives or non-OOXML binary `.doc` files gracefully fallback to binary string inspection or report `extraction_status="PARTIAL"`.

## Security Considerations
- Guard against zip bombs: Bounded XML stream parsing (max 500 KB XML payload parsed per document).
- The implemented budget is **500 KiB total decompressed XML**, shared across
  properties, relationships, content, and shared strings. XML reads use chunks
  of at most 4 KiB; content sampling stops early at the documented limits.
- Reject DTD/entity declarations before feeding XML, including UTF-16/32 and
  declarations crossing read boundaries. Validate expected XML root elements.
- Before loading ZIP entries, bound the index to 2 MiB and 10,000 declared
  entries; also check the actual entry count afterward. ZIP64-sized indexes
  and unsupported compression methods return explicit partial results.
- No archive members are extracted to disk. External relationships are skipped;
  URI schemes and targets escaping the package root are rejected. Formulas,
  macros, embedded objects, links, and scripts are never evaluated or fetched.

## Performance Considerations
- Direct zip inspection executes in < 15 ms per document.

## CI / Headless Requirements
- Pure Python standard library (`zipfile`, `xml.etree.ElementTree`). Zero Qt imports.

## Tests
- `tests/test_file_intelligence/test_extractors_office.py`:
  - Test synthetic `.docx` metadata and paragraph extraction.
  - Test synthetic `.pptx` slide title and metadata extraction.
  - Test synthetic `.xlsx` sheet name and metadata extraction.
  - Test corrupted office file handling.

## Acceptance Criteria
- [x] `DocxExtractor`, `PptxExtractor`, `XlsxExtractor` implemented and registered.
- [x] OOXML metadata parsed accurately without requiring external heavy libraries.
- [x] 100% test pass on `test_extractors_office.py`.

## Dependencies
- Standard library `zipfile`, `xml.etree.ElementTree`. Optional: `python-docx`, `openpyxl`.

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [x] Office extractors implemented.
- [x] Tests passing.

## Implementation State — 2026-11-14

Phase 05 is complete in the local working tree. The shared `_office.py` helper
keeps the three formats on one per-document byte budget; it introduces no
dependency or later-phase implementation.

Implemented behavior:

- DOCX: core properties, first 20 paragraphs, heading styles 1–3, and title
  fallback (Title style, first Heading 1, then first non-empty sampled line).
- PPTX: presentation relationship order, title/center-title placeholders from
  at most five slides, and preview text from the first three slides. Minimal
  packages lacking a presentation list use numeric slide filename order.
- XLSX: up to 32 sheet names and up to 64 first-row cells per sheet, resolving
  worksheet relationships, inline strings, shared strings, and cached values.
  Body rows are not included. Shared string parsing stops once required header
  indexes are resolved, subject to the shared byte budget.
- ODT/ODP/ODS: standard-library parsing of `meta.xml` and bounded content samples
  for text headings, presentation titles, and spreadsheet headers respectively.
- Legacy `.doc`, `.ppt`, `.xls`, and `.rtf`: honest `PARTIAL` results; binary/RTF
  metadata recovery is not implemented. Compound-binary containers, including
  potentially encrypted modern Office files, also return `PARTIAL`.
- `max_bytes` accepts non-negative integers or `None`, caps sampled text at
  64 KiB UTF-8, and permits zero-length samples with metadata retained. Previews
  have at most 1,024 characters, headings at most 64 entries of 256 characters,
  title/author/subject at most 256 characters, and keywords at most 20 entries.
- Malformed packages/XML return `CORRUPTED`, encrypted ZIP members `ENCRYPTED`,
  budget exhaustion `PARTIAL`, and inaccessible/non-regular inputs `FAILED`.

Validation on Python 3.13.5:

- **60 Phase 05 tests passed**, no failures or skips.
- **534 full-suite tests passed, 1 existing skip**, genuine pytest exit code **0**.
  Baseline was **474 passed, 1 skipped**. The skip remains Phase 02's
  permission test under a privileged user.
- Successful smoke tests with actual files generated by `python-docx` and
  `openpyxl`; the extractors themselves do not import those libraries.
- Twenty small synthetic document extractions per format measured median
  latency of **0.167 ms DOCX**, **0.296 ms PPTX**, and **0.267 ms XLSX** on this
  machine. Maximum observed values were **0.807, 0.476, and 0.331 ms**. These
  observations meet the 15 ms target for these fixtures, not every document.
- Source compilation, syntax checks, and whitespace checks passed. Full-suite
  validation captured pytest's actual return value despite the existing Qt
  teardown exit-zero hook; test state and compilation output used temporary
  locations.

Remaining boundaries:

- Office deadlines are checked cooperatively between bounded XML reads. They
  do not provide the PDF worker's hard process timeout; the registry still
  does not enforce a universal deadline.
- This is sampled metadata inspection, not complete Office format validation.
  Unsupported compression, very large indexes/parts, unusual custom styles,
  and unavailable legacy parsing can limit recovered metadata.
- Existing sorting/move logic, GUI, packaging dependencies, and other phases
  were not changed. Changes remain uncommitted.

Next implementation phase: **06 — Image (EXIF) & Media Metadata Extractor**.
