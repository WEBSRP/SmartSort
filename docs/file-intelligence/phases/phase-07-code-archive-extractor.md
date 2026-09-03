# Phase 07: Source Code & Archive Inspection Extractor

## Objective
Implement `src/core/file_intelligence/extractors/code.py` (`CodeExtractor`) and `src/core/file_intelligence/extractors/archive.py` (`ArchiveExtractor`) to inspect programming source files and compressed archive tables-of-contents without uncompressing archives to disk.

## Why This Phase Exists
Archives (`.zip`, `.tar.gz`) are opaque containers. A file named `Lecture_3_DBMS.zip` or `Project_Source.zip` can only be categorized accurately by inspecting its internal structure. Similarly, source code files contain critical symbol definitions (`class`, `def`, `import`) that identify software projects.

## Inputs
- Source code file paths (`.py`, `.c`, `.cpp`, `.java`, `.js`, `.rs`, `.go`, `.sh`) and archive paths (`.zip`, `.tar.gz`, `.tar.bz2`, `.tar.xz`, `.7z`).

## Outputs
- `src/core/file_intelligence/extractors/code.py` (`CodeExtractor`).
- `src/core/file_intelligence/extractors/archive.py` (`ArchiveExtractor`).
- Tests in `tests/test_file_intelligence/test_extractors_code_archive.py`.

## Files To Create
- `src/core/file_intelligence/extractors/code.py`
- `src/core/file_intelligence/extractors/archive.py`
- `tests/test_file_intelligence/test_extractors_code_archive.py`

## Files To Modify
- `src/core/file_intelligence/extractors/__init__.py`: Register `CodeExtractor`, `ArchiveExtractor`.

## Existing Components To Reuse
- `src/core/file_intelligence/extractors/base.py`: Inherits `BaseExtractor`.

## APIs / Interfaces
```python
# src/core/file_intelligence/extractors/code.py
class CodeExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([
        ".py", ".c", ".cpp", ".h", ".hpp", ".java", ".js",
        ".ts", ".go", ".rs", ".sh", ".bash", ".sql", ".php"
    ])
    ...

# src/core/file_intelligence/extractors/archive.py
class ArchiveExtractor(BaseExtractor):
    SUPPORTED_EXTENSIONS = frozenset([
        ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".7z"
    ])
    ...
```

## Data Structures
- Produces `ExtractedMetadata` populated with `code_language`, `code_symbols`, `toc_entries`, `headings`, `keywords`.

## Algorithms
- `CodeExtractor`:
  - Scans first 200 lines.
  - Regex symbol extraction for imports (`import `, `from ... import`, `#include `, `use `).
  - Class and function definitions (`class Name`, `def func`, `fn func`, `function func`).
  - Top-level docstring / block comment extraction.
- `ArchiveExtractor`:
  - Inspects `zipfile.ZipFile.infolist()` or `tarfile.TarFile.getmembers()`.
  - Collects internal member paths (up to 500 entries).
  - Derives content keywords based on internal extensions (e.g. presence of `.pptx` $\rightarrow$ `presentation`, `Makefile` $\rightarrow$ `code_project`).

## Error Handling
- Encrypted zip archives (`RuntimeError: File is encrypted`) report `extraction_status="ENCRYPTED"`.
- Corrupted archive headers return `extraction_status="CORRUPTED"`.

## Security Considerations
- **ZIP BOMB DEFENSE**: Member files are **never decompressed to disk**.
- Max 500 TOC entries inspected to prevent memory exhaustion on giant tarballs.

## Performance Considerations
- Header TOC inspection executes in < 10 ms per archive.

## CI / Headless Requirements
- Pure Python standard library (`zipfile`, `tarfile`, `re`). Zero Qt imports.

## Tests
- `tests/test_file_intelligence/test_extractors_code_archive.py`:
  - Test Python and C++ source code symbol extraction.
  - Test synthetic ZIP archive TOC extraction.
  - Test TAR.GZ archive TOC extraction.
  - Test archive with >500 files ensuring truncation limit is respected.
  - Test encrypted zip handling.

## Acceptance Criteria
- [ ] `CodeExtractor` and `ArchiveExtractor` implemented and registered.
- [ ] Zero archive files decompressed to disk during analysis.
- [ ] 100% test pass on `test_extractors_code_archive.py`.

## Dependencies
- Standard library `zipfile`, `tarfile`, `re`.

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [ ] Code and archive extractors created.
- [ ] Unit tests passing.
