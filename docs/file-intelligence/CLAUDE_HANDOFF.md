# Claude Opus Handoff Guide: File Intelligence Engine

**Target Codebase:** SmartSort (v1.1.6+)  
**Target Architecture:** File Intelligence Engine  
**Document Purpose:** Exact operational instructions for Claude Opus during phase-by-phase implementation.

---

## 1. Golden Rules of Engagement

1. **Read Before Writing**: Read `docs/file-intelligence/IMPLEMENTATION_PLAN.md` and the designated `docs/file-intelligence/phases/phase-XX-*.md` document completely before modifying any code.
2. **One Phase at a Time**: Implement **ONLY** the designated phase. Do not skip ahead, combine phases, or write speculative code for future phases.
3. **Zero Qt in Core**: Under no circumstances should any file inside `src/core/file_intelligence/` import `PyQt6`, `QApplication`, `QWidget`, `QMessageBox`, or `QThread`. Core logic must remain 100% pure Python.
4. **Preserve Safe Transfer Invariant**: Never implement direct moves (`shutil.move`) or bypass the 6-stage copy-verify-delete protocol in `FileUtils` and `DirectoryOrganizer`.
5. **No Regressions**: Every phase must leave the repository in a fully passing, releasable state. The existing 116 tests must pass at every step.
6. **No Breaking Packaging**: Debian `.deb` is the only supported package format.

---

## 2. Standard Implementation Workflow Per Phase

For every phase `phase-XX`:

### Step 1: Pre-Implementation Inspection
- Review the phase document: `docs/file-intelligence/phases/phase-XX-*.md`.
- Inspect existing files referenced in the "Existing Components To Reuse" and "Files To Modify" sections.
- Verify existing test suite passes:
  ```bash
  QT_QPA_PLATFORM=offscreen python3 -m pytest tests/
  ```

### Step 2: Implementation
- Create the files specified in "Files To Create".
- Modify the files specified in "Files To Modify" strictly according to the phase specification.
- Adhere strictly to the defined APIs, dataclasses, and error-handling requirements.

### Step 3: Test Creation & Verification
- Create or update the unit tests in `tests/test_file_intelligence/`.
- Run the dedicated phase tests:
  ```bash
  QT_QPA_PLATFORM=offscreen python3 -m pytest -vv tests/test_file_intelligence/test_phase_XX.py
  ```
- Run the full test suite:
  ```bash
  QT_QPA_PLATFORM=offscreen python3 -m pytest tests/
  ```

### Step 4: Code Quality & Compilation Check
- Verify Python compilation:
  ```bash
  python3 -m compileall src main.py
  ```
- Review git diff for unwanted artifacts, debug prints, or formatting regressions:
  ```bash
  git status
  git diff --check
  ```

### Step 5: Phase Completion Report
- Fill out the Completion Checklist in the phase document and confirm all Acceptance Criteria are met.
- Provide a structured summary of files created, tests passed, and readiness for the next phase.

---

## 3. Troubleshooting & Common Pitfalls

| Issue | Root Cause | Solution |
|---|---|---|
| **Headless Pytest Hangs** | Code instantiated `QMessageBox` or started an unmanaged `QTimer` | Ensure core intelligence modules have zero Qt imports. In GUI tests, always mock `QMessageBox` and use the session `qapp` fixture. |
| **ImportError on Optional Libs** | `pypdf`, `docx`, etc. not installed | Wrap third-party imports in `try/except ImportError` blocks and execute pure-Python fallback code paths. |
| **Path Traversal Violations** | Relative paths (`..`) in proposals | Always validate candidate targets using `os.path.commonpath([root, target]) == root`. |
| **Zip Bomb Memory Spike** | Decompressing archive files during extraction | Never decompress archives. Only read member headers via `zipfile.ZipFile.infolist()`. |
| **Locked Browser SQLite DB** | Browser has an active lock on `History` | Connect with `file:path?mode=ro&immutable=1` URI or create a temporary shadow copy. |
