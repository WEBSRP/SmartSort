# Phase 03: Text, Markdown, and Plain Document Extractor

## Objective
Implement the `BaseExtractor` abstract interface, the central `ExtractorRegistry`, and the `TextExtractor` module in `src/core/file_intelligence/extractors/text.py` supporting plaintext, Markdown, CSV, Log, and structured text formats.

## Why This Phase Exists
Plain text, Markdown notes, configuration files, and tabular CSV files represent a substantial portion of user documents. This phase establishes the pluggable extractor architecture and delivers fast, zero-dependency text extraction.

## Inputs
- File path to text-based document.

## Outputs
- `src/core/file_intelligence/extractors/base.py` (`BaseExtractor`, `ExtractorRegistry`).
- `src/core/file_intelligence/extractors/text.py` (`TextExtractor`).
- Tests in `tests/test_file_intelligence/test_extractors_text.py`.

## Files To Create
- `src/core/file_intelligence/extractors/base.py`
- `src/core/file_intelligence/extractors/text.py`
- `tests/test_file_intelligence/test_extractors_text.py`

## Files To Modify
- `src/core/file_intelligence/extractors/__init__.py`: Export `BaseExtractor`, `ExtractorRegistry`, `TextExtractor`.

## Existing Components To Reuse
- `src/core/file_intelligence/context.py`: For `ExtractedMetadata`.

## APIs / Interfaces
```python
# src/core/file_intelligence/extractors/base.py
class BaseExtractor(ABC):
    MAX_TEXT_BYTES: int = 64 * 1024
    TIMEOUT_SECONDS: float = 3.0

    @abstractmethod
    def can_extract(self, extension: str, mime_type: str) -> bool:
        ...

    @abstractmethod
    def extract(self, file_path: str, max_bytes: Optional[int] = None) -> ExtractedMetadata:
        ...

# src/core/file_intelligence/extractors/text.py
class TextExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([
        ".txt", ".md", ".markdown", ".rst", ".log", ".csv",
        ".tsv", ".json", ".yaml", ".yml", ".xml", ".html", ".htm"
    ])
    ...
```

## Data Structures
- Produces `ExtractedMetadata` with populated `title`, `headings`, `text_preview`, `keywords`.

## Algorithms
- Multi-encoding detection stream (UTF-8 with BOM check $\rightarrow$ Latin-1 fallback $\rightarrow$ `errors='ignore'`).
- Markdown heading parsing (Regex: `r'^(#{1,6})\s+(.+)$'`).
- Title heuristic: Markdown `# Heading` or first non-empty line of plaintext.
- Keyword frequency extraction (stripping standard English stop-words).

## Error Handling
- Capture `UnicodeDecodeError`, `OSError`, `PermissionError` without crashing; return `ExtractedMetadata(extraction_status="FAILED", error_message=str(e))`.

## Security Considerations
- Bounded read: Read only first 64 KB using `f.read(65536)`. Never load entire multi-gigabyte log or CSV files into memory.

## Performance Considerations
- Sub-millisecond execution (< 0.5 ms per text file).

## CI / Headless Requirements
- Pure Python standard library. Zero Qt imports. 100% headless.

## Tests
- `tests/test_file_intelligence/test_extractors_text.py`:
  - Test Markdown file with headings and title extraction.
  - Test Plaintext `.txt` note extraction.
  - Test large log file (>10 MB) ensuring memory truncation to 64 KB.
  - Test UTF-8, Latin-1, and corrupted encoding handling.

## Acceptance Criteria
- [ ] `BaseExtractor` and `ExtractorRegistry` implemented.
- [ ] `TextExtractor` handles all 13 supported text extensions.
- [ ] Memory strictly bounded on large files.
- [ ] 100% test pass on `test_extractors_text.py`.

## Dependencies
- Standard library (`re`, `io`, `typing`).

## What This Phase MUST NOT Change
- Must NOT modify existing SmartSort rules or GUI.

## Completion Checklist
- [ ] Base extractor and text extractor created.
- [ ] Unit tests passing.
