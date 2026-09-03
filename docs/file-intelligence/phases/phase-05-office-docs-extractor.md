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
- `src/core/file_intelligence/extractors/docx.py`
- `src/core/file_intelligence/extractors/pptx.py`
- `src/core/file_intelligence/extractors/xlsx.py`
- `tests/test_file_intelligence/test_extractors_office.py`

## Files To Modify
- `src/core/file_intelligence/extractors/__init__.py`: Register `DocxExtractor`, `PptxExtractor`, `XlsxExtractor`.

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
- [ ] `DocxExtractor`, `PptxExtractor`, `XlsxExtractor` implemented and registered.
- [ ] OOXML metadata parsed accurately without requiring external heavy libraries.
- [ ] 100% test pass on `test_extractors_office.py`.

## Dependencies
- Standard library `zipfile`, `xml.etree.ElementTree`. Optional: `python-docx`, `openpyxl`.

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [ ] Office extractors implemented.
- [ ] Tests passing.
