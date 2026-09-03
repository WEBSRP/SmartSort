# Phase 15: GUI Preview, Evidence Display, & Review Workflow

## Objective
Update `src/gui/main_window.py` (`SmartSortGUI`) to render rich intelligence feedback, cluster summaries, confidence tags (`[CONFIRMED]`, `[PROBABLE]`), and detailed evidence justifications in the Directory Organizer tab and Settings panel.

## Why This Phase Exists
Transparency is a core design principle of the File Intelligence Engine. Users must be able to inspect dry-run previews and clearly understand *why* SmartSort proposed a specific destination (e.g. "Matched Title: DBMS Normalization", "Origin: Canvas LMS") before committing file transfers.

## Inputs
- `DirectoryPreviewSummary` containing enriched `OrganizePlanItem`s with confidence and evidence lists.

## Outputs
- Updated `src/gui/main_window.py` with enriched preview and settings controls.
- Tests in `tests/test_core.py`.

## Files To Create
- None.

## Files To Modify
- `src/gui/main_window.py`: Update `on_dir_worker_preview_ready()`, `on_dir_worker_finished()`, and `setup_settings()`.
- `tests/test_core.py`: Add test verifying GUI rendering of intelligence evidence and settings toggles.

## Existing Components To Reuse
- `src/gui/main_window.py`: Reuses existing `DirectoryOrganizerWorker`, `DirectoryOrganizerSignals`, `QProgressBar`, and Adwaita styles.

## APIs / Interfaces
```python
# src/gui/main_window.py
class SmartSortGUI(QMainWindow):
    def on_dir_worker_preview_ready(self, summary: DirectoryPreviewSummary):
        """Renders dry-run summary with clusters, confidence ratings, and evidence reasons."""
        ...
```

## Data Structures
- Consumes `DirectoryPreviewSummary`, `OrganizePlanItem`, `EvidenceItem`.

## Algorithms
- Formats structured monospace text preview:
  ```text
  === DRY-RUN PREVIEW SUMMARY ===
  Total Files Found: 4
  Clusters Discovered: 1 (DBMS Course Material)

  Planned Moves:
    Lecture_1_DBMS.pdf -> College/DBMS/Lectures/Lecture_1_DBMS.pdf [CONFIRMED (92%)]
      └ Evidence: Title ("DBMS Normalization"), Origin (canvas.stanford.edu), Sibling Cluster
    Lecture_3_DBMS.zip -> College/DBMS/Lectures/Lecture_3_DBMS.zip [CONFIRMED (88%)]
      └ Evidence: Archive contains PPTX/PDF, Origin (canvas.stanford.edu), Sibling Cluster
  ```
- Adds settings checkboxes in Settings tab:
  - "Enable Browser Origin Detection" (`enable_origin_detection`)
  - "Enable Deep Document Content Extraction" (`enable_deep_content_extraction`)

## Error Handling
- Handles long evidence lists with neat wrapping and indentation.

## Security Considerations
- All file manager launch commands continue using sanitized `open_file_in_manager()`.

## Performance Considerations
- UI string formatting executes in < 5 ms for 500 files.

## CI / Headless Requirements
- All GUI tests MUST use the session `qapp` fixture and mock static `QMessageBox` calls to prevent CI hangs.

## Tests
- `tests/test_core.py`:
  - Test `on_dir_worker_preview_ready` formats preview text containing confidence and evidence.
  - Test settings toggles update config and persist.

## Acceptance Criteria
- [ ] Directory Organizer tab displays enriched preview with confidence and evidence.
- [ ] Settings tab includes new intelligence toggles.
- [ ] All GUI tests pass 100% in headless offscreen mode.

## Dependencies
- PyQt6.

## What This Phase MUST NOT Change
- Must NOT alter core intelligence logic in `src/core/file_intelligence/`.

## Completion Checklist
- [ ] `main_window.py` updated.
- [ ] GUI tests passing.
