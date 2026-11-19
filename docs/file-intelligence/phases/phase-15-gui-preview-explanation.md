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
- `tests/test_gui.py`: Extend the existing offscreen GUI regression suite for
  review actions, stale plans, evidence inspection, settings and both themes.
- `src/utils/config.py` and `config/config.default.json`: Validate, persist and
  default the deep-content flag; expose the existing origin flag.
- `src/core/directory_organizer.py` and `src/organizer.py`: Honor the deep-content
  flag around registry dispatch. Core intelligence algorithms remain unchanged.

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
- Target: UI string formatting executes in < 5 ms for 500 files. The measured
  fixture meets this at its median, with occasional slower runs (see below).

## CI / Headless Requirements
- All GUI tests MUST use the session `qapp` fixture and mock static `QMessageBox` calls to prevent CI hangs.

## Tests
- `tests/test_core.py`:
  - Test `on_dir_worker_preview_ready` formats preview text containing confidence and evidence.
  - Test settings toggles update config and persist.

## Acceptance Criteria
- [x] Directory Organizer tab displays enriched preview with confidence and evidence.
- [x] Settings tab includes new intelligence toggles.
- [x] All GUI tests pass 100% in headless offscreen mode.

## Dependencies
- PyQt6.

## What This Phase MUST NOT Change
- Must NOT alter core intelligence logic in `src/core/file_intelligence/`.

## Completion Checklist
- [x] `main_window.py` updated.
- [x] GUI tests passing.

## Implementation State — 2026-11-18

Functional implementation is complete in the working tree, preserving the
existing lightweight ivory/light and charcoal/dark themes. The directory page
uses a native read-only monospace `QPlainTextEdit`. It shows every planned move
(removing the old 50-file sample limit), numbered to match the inspection picker,
with relative destination, confidence level/percentage, cluster names and
evidence. Warnings include their counts and reasons. The main review shows up to
eight reasons per file with an explicit additional-reason count; **Inspect
evidence** opens the complete selected-file evidence and full source/target paths
in a read-only native dialog. Dialogs are disposed after use.

Displayed confidence is explicitly an estimate rather than a calibrated
correctness probability; a confirmed rule match confirms configured policy.
Text remains literal, including HTML-looking filenames/reasons. C0/DEL control
characters are rendered as visible escapes so they cannot forge review rows.
Wrapping, native scrolling and theme colors are retained. Progress percentages
remain in the status text rather than low-contrast text over the progress fill.

### Review and execution

The GUI's **Review moves** action first generates a dry-run plan if none is
available. Preview workers retain an independent copy of the actual plan and
emit a matching summary. Once displayed, **Organize reviewed moves** asks for one
batch decision, defaulting to No, showing exact move count, root, low-confidence
count, warning count, collision policy and duplicate-detection state.

Approved execution receives a frozen copy of the reviewed plan: it does not scan
or re-plan and therefore does not add newly arrived files or new destinations.
Collision/duplicate settings are frozen for that execution. Backend identity and
containment checks still reject changed sources/paths; configured collision
renaming can produce a suffix, and the results show the actual final target.
This binds the UI decision to proposed intent rather than guaranteeing every
planned transfer will succeed.

Changes to folder/options, rules or saved settings invalidate the review. Rule
data is synchronized from the GUI's rule manager before preview. Late previews
whose routing key or summary no longer matches their execution snapshot cannot
be organized. Queued preview signals arriving after cancellation are discarded.
Errors, completion and cancellation clear executable review state. Execution
results retain planning warnings and correlate confidence with the reviewed
source, while displaying actual recorded target paths. Report/file-manager
launches continue using the existing helper.

Legacy direct worker callers can still omit a supplied plan and use the original
scan/plan/execute path. The GUI uses the reviewed-plan path. There is no per-file
destination editor or subset checkbox workflow in this phase; the confirmation
applies to the whole listed batch. Standalone summary rendering without an
associated worker snapshot is display-only and requires a fresh preview to run.

### Settings behavior

Settings includes **Enable Browser Origin Detection** and **Enable Deep Document
Content Extraction**, both defaulting to true for existing configurations. The
deep-content flag is boolean-validated and survives reload. Saving applies both
flags to the shared config used by the directory and download organizers and
invalidates any reviewed plan.

With deep extraction disabled, the organizers skip format-registry dispatch but
still build filesystem/MIME context and classify filename plus optional origin
signals. This does not promise zero file reads: MIME sniffing, origin lookup and
independently enabled filename cleanup retain their documented behavior.
Configured rules always take priority. Invalid settings leave the saved file
unchanged, following existing validation.

### Validation and limits

- Baseline: **1,280 passed, 1 skipped**, real pytest exit code 0.
- Added **26 tests**, including core plain-text/config contracts and GUI review,
  confirmation/decline, immutable-plan binding, stale/mutated/cancelled summaries,
  approved collision policy, changed sources, exact subset execution, settings
  persistence/behavior, full evidence and minimum-window theme checks.
- Final full suite: **1,306 passed, 1 skipped** in 21.22 s, preserved exit code
  **0** despite the existing Qt teardown's forced exit-zero backstop.
- Source compilation and `git diff --check` pass. Hash comparisons confirm no
  changes to `src/core/file_intelligence/`, `src/monitor.py` or `FileUtils`.
- Real offscreen Qt captures of review, settings and evidence were visually
  inspected in both themes with synthetic data. Tests cover all pages and the
  new controls at 860×620, with no horizontal page overflow.
- A 500-file fixture with three reasons per file formatted to 122,005 characters.
  Across 101 runs: first **3.907 ms**, subsequent median **4.363 ms**, maximum
  **9.433 ms**. The median meets the 5 ms target; this is not a hard deadline.
  Qt document layout, copying snapshots, populating the picker and paint time
  are additional work, outside the string-only measurement.

Core classification/planning/extraction algorithms, download monitor and safe
transfer implementation remain unchanged. The only backend changes are config
plumbing and two registry-dispatch guards outside the intelligence package.
Directory scan/profiling cancellation still follows its existing stage boundaries;
this phase does not solve earlier PDF parsing/batch latency limits.

Next: **Phase 16 — Enhanced Arrangement Index Report & Searchable Audit**.
