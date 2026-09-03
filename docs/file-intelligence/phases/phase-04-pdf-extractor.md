# Phase 04: PDF Content & Metadata Extractor

## Objective
Implement `src/core/file_intelligence/extractors/pdf.py` (`PdfExtractor`) to extract document metadata (Title, Author, Subject, Keywords), Table of Contents outlines, and bounded text samples from PDF files using `pypdf` with a pure-Python dictionary fallback parser.

## Why This Phase Exists
PDFs are the primary medium for course notes, lecture slides, academic papers, research reports, and official invoices. Accurate extraction of internal PDF titles and headings is essential for distinguishing `College/DBMS/` from `Work/Invoices/`.

## Inputs
- PDF file path (`.pdf`).

## Outputs
- `src/core/file_intelligence/extractors/pdf.py` (`PdfExtractor`).
- Tests in `tests/test_file_intelligence/test_extractors_pdf.py`.

## Files To Create
- `src/core/file_intelligence/extractors/pdf.py`
- `tests/test_file_intelligence/test_extractors_pdf.py`

## Files To Modify
- `src/core/file_intelligence/extractors/__init__.py`: Register `PdfExtractor`.

## Existing Components To Reuse
- `src/core/file_intelligence/extractors/base.py`: Inherits `BaseExtractor`.

## APIs / Interfaces
```python
# src/core/file_intelligence/extractors/pdf.py
class PdfExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([".pdf"])

    def can_extract(self, extension: str, mime_type: str) -> bool:
        return extension.lower() in self.SUPPORTED_EXTENSIONS or mime_type == "application/pdf"

    def extract(self, file_path: str, max_bytes: Optional[int] = None) -> ExtractedMetadata:
        ...
```

## Data Structures
- Produces `ExtractedMetadata` populated with `title`, `author`, `subject`, `keywords`, `headings`, `text_preview`.

## Algorithms
- `pypdf.PdfReader` inspection:
  - Read `reader.metadata`: `/Title`, `/Author`, `/Subject`, `/Keywords`.
  - Extract outline headings from `reader.outline`.
  - Extract text across pages 1 to 5 (bounded to `MAX_TEXT_BYTES`).
- Pure-Python Fallback Parser:
  - Scans binary PDF trailer and `/Info` object dictionary for `/Title (string)` and `/Author (string)` when `pypdf` is unavailable.

## Error Handling
- Password-protected PDFs: Catch `pypdf.errors.FileNotDecryptedError` and return `extraction_status="ENCRYPTED"`.
- Malformed/corrupted PDFs: Catch `pypdf.errors.PdfReadError` and return `extraction_status="CORRUPTED"`.

## Security Considerations
- Execution timeout of 3.0 seconds per PDF to defend against deeply recursive or circular PDF objects.

## Performance Considerations
- Max 5 pages scanned per document to ensure execution completes in < 50 ms.

## CI / Headless Requirements
- Zero Qt imports. Pure Python execution.

## Tests
- `tests/test_file_intelligence/test_extractors_pdf.py`:
  - Test synthetic PDF with valid `/Title` and text.
  - Test fallback parser when `pypdf` is mocked as unavailable.
  - Test encrypted PDF handling.
  - Test corrupt PDF handling without uncaught exceptions.

## Acceptance Criteria
- [ ] `PdfExtractor` extracts title, author, and text from standard PDFs.
- [ ] Fallback parser functions cleanly without `pypdf`.
- [ ] 100% test pass on `test_extractors_pdf.py`.

## Dependencies
- `pypdf` (recommended: `python3-pypdf`), with standard library fallback (`re`, `io`).

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [ ] `pdf.py` implemented.
- [ ] Tests passing.
