# Phase 02: Filesystem & Extended Attribute Metadata Extractor

## Objective
Implement `src/core/file_intelligence/metadata.py` and `src/core/file_intelligence/mime.py` to extract filesystem stat attributes, deterministic MIME types, and extended attributes (`xattrs`) into an initialized `FileContext`.

## Why This Phase Exists
Every file analysis pipeline begins with fast, lightweight filesystem inspection. Establishing consistent file identification (inode, device, timestamp, size) prevents redundant analysis and provides the base structure for deeper content extraction.

## Inputs
- Absolute or relative file path string.

## Outputs
- `src/core/file_intelligence/metadata.py` (`FileMetadataExtractor`, `FileContextBuilder`).
- `src/core/file_intelligence/mime.py` (`DeterministicMime`).
- Tests in `tests/test_file_intelligence/test_metadata.py`.

## Files To Create
- `src/core/file_intelligence/metadata.py`
- `src/core/file_intelligence/mime.py`
- `tests/test_file_intelligence/test_metadata.py`

## Files To Modify
- `src/core/file_intelligence/__init__.py`: Export `FileContextBuilder`, `DeterministicMime`.

## Existing Components To Reuse
- `src/utils/file_utils.py`: For hashing and path utilities.
- `src/core/filename_cleanup.py`: For reference on `os.getxattr` handling.

## APIs / Interfaces
```python
# src/core/file_intelligence/mime.py
class DeterministicMime:
    @staticmethod
    def guess_mime(file_path: str) -> str:
        """Determines standardized MIME type based on extension and magic headers."""
        ...

    @staticmethod
    def get_category_hint(extension: str) -> str:
        """Returns primary category hint (e.g. 'Documents', 'Images', 'Code')."""
        ...

# src/core/file_intelligence/metadata.py
class FileContextBuilder:
    @staticmethod
    def build_initial_context(file_path: str, compute_hash: bool = False) -> FileContext:
        """
        Performs os.stat, resolves canonical path, populates filesystem metadata,
        and returns an initialized FileContext.
        """
        ...
```

## Data Structures
- Consumes and populates `FileContext` from `src.core.file_intelligence.context`.

## Algorithms
- Canonical path resolution using `os.path.abspath(os.path.realpath(file_path))`.
- Stat extraction (`os.stat(file_path)`): `st_size`, `st_mtime`, `st_ctime`, `st_ino`, `st_dev`.
- MIME lookup dictionary with fast extension mapping and binary magic byte prefix inspection (e.g. `%PDF-`, `\x89PNG`, `PK\x03\x04`).

## Error Handling
- `FileNotFoundError`: Raises `ValueError` with clear path context.
- `PermissionError`: Returns `FileContext` with `metadata.extraction_status = "PERMISSION_DENIED"`.

## Security Considerations
- Validate path against root escape; ignore symlinks during initial scan if configured.

## Performance Considerations
- Sub-millisecond execution (< 0.1 ms per file). Hash computation is deferred and optional.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_metadata.py`:
  - Test regular file stat population (size, times, inode, device).
  - Test MIME guessing across common extensions (`.pdf`, `.docx`, `.png`, `.py`, `.zip`).
  - Test non-existent file handling.
  - Test xattr reading on supported filesystems (with mock fallback).

## Acceptance Criteria
- [ ] `FileContextBuilder.build_initial_context` creates valid `FileContext` objects.
- [ ] MIME detection accurately maps 30+ common extensions.
- [ ] 100% pass on `test_metadata.py`.

## Dependencies
- Standard library (`os`, `pathlib`, `mimetypes`).

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [ ] `metadata.py` and `mime.py` created.
- [ ] Unit tests passing.
