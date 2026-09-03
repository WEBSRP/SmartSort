# Phase 00: Architecture Audit & Extractor Environment Verification

## Objective
Audit the current SmartSort v1.1.6 codebase, verify the Python runtime environment, inspect optional library availability (`pypdf`, `python-docx`, `openpyxl`, `Pillow`, `mutagen`, `sqlite3`), and establish the foundation directory structure and test scaffolding for the File Intelligence Engine.

## Why This Phase Exists
Before implementing data models or extractors, the development environment must be validated against Debian/Ubuntu dependencies, verifying that all optional libraries degrade gracefully when missing and that existing tests pass with 100% reliability.

## Inputs
- Existing SmartSort v1.1.6 repository structure.
- Current Python runtime environment (Python 3.8+ / Debian 11+ / Ubuntu 22.04+).

## Outputs
- Verified environment report.
- Directory scaffold: `src/core/file_intelligence/` and `src/core/file_intelligence/extractors/`.
- Test scaffold: `tests/test_file_intelligence/`.
- Clean baseline test execution (116/116 passing).

## Files To Create
- `src/core/file_intelligence/__init__.py`
- `src/core/file_intelligence/extractors/__init__.py`
- `tests/test_file_intelligence/__init__.py`
- `tests/test_file_intelligence/test_scaffold.py`

## Files To Modify
- None.

## Existing Components To Reuse
- `src/utils/paths.py`: For resolving application and cache directories.
- `src/utils/logger.py`: For standardized application logging.

## APIs / Interfaces
```python
# src/core/file_intelligence/__init__.py
"""SmartSort File Intelligence Engine package."""
__version__ = "1.0.0"
```

## Data Structures
- Standard package initialization.

## Algorithms
- Environment capability detection (checking `importlib.util.find_spec` for optional dependencies).

## Error Handling
- Capture and log missing optional libraries without throwing uncaught exceptions.

## Security Considerations
- Ensure no sensitive development or personal paths are hardcoded.

## Performance Considerations
- Zero startup latency impact on application initialization.

## CI / Headless Requirements
- Zero Qt imports.
- Tests run headless with `QT_QPA_PLATFORM=offscreen`.

## Tests
- `tests/test_file_intelligence/test_scaffold.py`:
  - `test_package_import`: Verifies `src.core.file_intelligence` can be imported in pure Python without Qt.
  - `test_extractors_package_import`: Verifies `src.core.file_intelligence.extractors` imports cleanly.

## Acceptance Criteria
- [ ] `src/core/file_intelligence/` and `extractors/` directories exist with valid `__init__.py`.
- [ ] `tests/test_file_intelligence/test_scaffold.py` passes 100%.
- [ ] Full test suite passes 116+ tests with exit code 0.
- [ ] `python3 -m compileall src main.py` exits with 0.

## Dependencies
- Standard library (`os`, `sys`, `importlib`).

## What This Phase MUST NOT Change
- Must NOT modify existing `src/organizer.py`, `src/core/directory_organizer.py`, or GUI files.

## Completion Checklist
- [ ] Environment verified.
- [ ] Scaffold packages created.
- [ ] Baseline test suite passes with zero regressions.
