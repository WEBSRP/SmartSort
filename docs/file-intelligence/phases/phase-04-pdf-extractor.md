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
- `src/core/file_intelligence/extractors/__init__.py`: Export `PdfExtractor`.
- `src/core/file_intelligence/extractors/base.py`: Register `PdfExtractor` in
  `ExtractorRegistry._register_default_extractors()`.

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
- Each PDF is parsed in a fresh interpreter process. `subprocess.run(timeout=...)`
  kills and reaps the worker on timeout, including when called from GUI worker
  threads. No application-wide signals, timers, or persistent workers are used.
- On Linux, worker address space is capped at 512 MiB and CPU time at three
  seconds (or a stricter inherited hard limit). Non-regular inputs are rejected.
- Text sampling is capped at 64 KiB of UTF-8 data across at most five pages;
  the preview is capped at 1,024 characters. Headings, keywords, and metadata
  strings also have bounded output sizes. `max_bytes` may lower the text budget.

## Performance Considerations
- Max 5 pages scanned per document. The original target is < 50 ms, but page
  count alone cannot guarantee it. Fresh-process isolation adds startup cost;
  measured total times and outstanding performance work are recorded below.

## CI / Headless Requirements
- Zero Qt imports. Pure Python execution.

## Tests
- `tests/test_file_intelligence/test_extractors_pdf.py`:
  - Test synthetic PDF with valid `/Title` and text.
  - Test fallback parser when `pypdf` is mocked as unavailable.
  - Test encrypted PDF handling.
  - Test corrupt PDF handling without uncaught exceptions.

## Acceptance Criteria
- [x] `PdfExtractor` extracts title, author, and text from standard PDFs.
- [x] Fallback parser functions cleanly without `pypdf`.
- [x] 100% test pass on `test_extractors_pdf.py`.

## Dependencies
- `pypdf` (recommended: `python3-pypdf`), with standard library fallback (`re`, `io`).

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [x] `pdf.py` implemented.
- [x] Tests passing.

## Implementation State — 2026-11-14

Functional acceptance is complete in the local working tree. The latency target
remains outstanding. Implementation uses Python 3.13.5 and was validated against
installed `pypdf` 6.15.0; the dependency remains optional and is loaded only inside
the parser worker.

Behavior:

- Reads title, author, subject, creation/modification date strings, keywords,
  nested outline headings, and text from at most five pages.
- Missing titles/keywords can be derived from the bounded extracted text.
- Returns `SUCCESS`, `PARTIAL`, `ENCRYPTED`, `CORRUPTED`, `TIMEOUT`, or `FAILED`
  as appropriate. Worker crashes and protocol errors are isolated.
- Without `pypdf`, inspects at most 1 MiB total from the beginning/end of the
  container and follows a classic trailer's `/Info` reference. Supports nested
  literal strings, escapes, octal escapes, hex strings, and UTF-16 BOM strings.
- Fallback results are explicitly `PARTIAL`, with no invented page text.
  Object streams, XMP-only metadata, and `/Info` objects outside the sampled
  windows may yield no metadata. Non-Unicode fallback strings use Latin-1 as
  a conservative approximation rather than a complete PDFDocEncoding decoder.
- Image-only scans do not receive OCR in this phase.

Validation:

- **45 Phase 04 tests passed**, no failures or skips.
- **474 full-suite tests passed, 1 skipped**, genuine pytest return code **0**.
  The existing skip is Phase 02's permission test under a privileged user.
- Baseline before Phase 04: **429 passed, 1 skipped**.
- Real worker timeout test confirms termination and reaping; additional tests
  verify resource limits, concurrent thread callers, corrupt/encrypted inputs,
  fallback import failures, read/output bounds, and source preservation.
- Source compilation and whitespace checks pass. Test state and bytecode were
  directed to temporary locations; the full-suite runner preserved pytest's
  actual return code despite the existing Qt fixture's exit-zero backstop.

Performance limitation:

- Three small synthetic PDF extractions took **180.1, 205.6, and 181.6 ms**,
  including fresh interpreter and backend startup during validation. These are
  observations on this machine, not a cross-platform benchmark or a guarantee.
- The **< 50 ms total latency target is not met**. Process isolation is retained
  for the enforceable deadline and memory cap; performance optimization needs
  separate validation without weakening those bounds.

Next phase: **05 — Office Document Extractors**. File organizing, transfer logic,
GUI code, dependency declarations, and later-phase implementations were not
changed by Phase 04.
