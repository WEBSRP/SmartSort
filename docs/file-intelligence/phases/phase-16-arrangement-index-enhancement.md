# Phase 16: Enhanced Arrangement Index Report & Searchable Audit

## Objective
Enhance `DirectoryOrganizer.generate_report()` in `src/core/directory_organizer.py` to include confidence ratings, cluster groupings, and explicit evidence reasons in the generated `SmartSort_Arrangement.md` index file while preserving atomic file generation and offline `file:///` local links.

## Why This Phase Exists
`SmartSort_Arrangement.md` is the permanent, human-readable audit record left in the organized directory. Augmenting it with intelligence evidence provides users with a searchable, transparent record of why every file was moved where it was.

## Inputs
- `OrganizeResult` containing operation records enriched with intelligence metadata.

## Outputs
- Updated `generate_report()` method in `src/core/directory_organizer.py`.
- Tests in `tests/test_directory_organizer.py`.

## Files To Create
- None.

## Files To Modify
- `src/core/directory_organizer.py`: Update `FileOperationRecord` and `generate_report()`.
- `tests/test_directory_organizer.py`: Update report verification tests.

## Existing Components To Reuse
- `src/core/directory_organizer.py`: Reuses atomic file replacement (`.tmp` $\rightarrow$ `os.replace`), size formatting, and `file:///` URI generation.

## APIs / Interfaces
```python
# src/core/directory_organizer.py
@dataclass
class FileOperationRecord:
    source: str
    target: str
    category: str
    rule_name: str
    status: OperationStatus
    error: str = ""
    hash: str = ""
    size: int = 0
    confidence: str = "CONFIRMED"                # Added
    evidence: List[str] = field(default_factory=list) # Added
    cluster_name: str = ""                       # Added
    confidence_score: Optional[float] = None      # Unknown for legacy records
    cluster_id: Optional[str] = None             # Distinguishes same-named groups
```

## Data Structures
- Enriched `FileOperationRecord`.

## Algorithms
- **Enhanced Markdown Report Structure**:
  ```markdown
  # SmartSort Arrangement Index

  **Root Directory:** `/home/user/College`  
  **Date of Operation:** `2026-08-18 23:45:00`  
  **Total Files Processed:** `4`  
  **Summary:** 3 Verified & Moved | 0 Collision Resolved | 1 Duplicate Preserved | 0 Skipped | 0 Errors  

  ---

  ## Table of Contents
  - [College/DBMS/Lectures](#collegedbmslectures)
  - [Images](#images)

  ---

  ## College/DBMS/Lectures

  ### Lecture_1_DBMS.pdf
  - **Original Path:** `/home/user/College/Lecture_1_DBMS.pdf`
  - **Final Location:** `/home/user/College/College/DBMS/Lectures/Lecture_1_DBMS.pdf`
  - **Category:** College/DBMS/Lectures
  - **Confidence:** `CONFIRMED (92%)`
  - **Cluster:** `DBMS_Course`
  - **Evidence:**
    - Document Title: *"Database Normalization Lecture 1"*
    - Origin Domain: `canvas.stanford.edu`
    - Sibling Cluster: Matched `Lecture_2_DBMS.pptx`
  - **Size:** 1.25 MB
  - **SHA-256:** `a3f8...`
  - **Status:** `VERIFIED_AND_MOVED`
  - **Actions:** [Open File](file:///home/user/College/College/DBMS/Lectures/Lecture_1_DBMS.pdf) | [Open Folder](file:///home/user/College/College/DBMS/Lectures)
  ```

## Error Handling
- Write to an exclusively created hidden sibling `.SmartSort_Arrangement.*.tmp`, flush and fsync the file, then `os.replace`. Readers see the previous or complete replacement report. Handled write/sync/replace failures preserve the previous report and clean the temporary file. Abrupt termination may leave a hidden temporary file; power-loss durability of directory metadata is not guaranteed.

## Security Considerations
- All file links use RFC-compliant `file:///` local URIs with zero external web dependencies.

## Performance Considerations
- Target: < 2 ms for 500 files. **Not met** by the measured implementation; see the validation notes below.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_directory_organizer.py`:
  - Test report includes Confidence and Evidence sections.
  - Test report contains valid `file:///` local URIs.
  - Test report atomic write works reliably.

## Acceptance Criteria
- [x] `generate_report()` outputs enhanced report with confidence and evidence.
- [x] Atomic write and offline `file:///` links preserved.
- [x] 100% pass on report test suite.

## Dependencies
- Standard library (`pathlib`, `os`, `datetime`).

## What This Phase MUST NOT Change
- Must NOT alter copy-verify-delete transfer safety.

## Completion Checklist
- [x] Report generation updated.
- [x] Unit tests passing.


## Implementation State — 2026-11-18

Functional implementation is complete in the working tree. Execution snapshots
confidence, numeric score, evidence, cluster name/ID and planning warnings before
callbacks, and copies the metadata to every produced operation record, including
failure, duplicate and skip outcomes. The original execution loop and transfer
protocol are unchanged. Added dataclass fields have defaults and follow all old
positional fields; legacy records keep their confidence label with no fabricated
percentage and an explicit missing-evidence message.

The index groups all recorded outcomes by actual destination directory relative
to the root (for example `College/DBMS/Lectures`). Collision records use the final
renamed path. Failed/skipped destinations are explicitly labeled **Intended
Destination**. Cluster summaries link to stable per-record anchors; IDs distinguish
same-named groups. Each record retains source/target paths, category, rule, size,
SHA-256 when recorded, status, error and local actions, plus all recorded evidence.
Failed/skipped actions link to the source and source folder, duplicates link to
both preserved copies, and moved files link to their final file/folder. Confidence
is described as an estimate, not a calibrated probability.

This remains a **latest-operation snapshot**, replacing the previous index rather
than accumulating history. Cancellation and planning warnings are visible; files
not processed before cancellation do not acquire invented records. No new GUI,
cloud dependency, content extraction or Qt import is required.

Report text escapes Markdown/HTML, uses variable-length code spans for paths and
IDs, flattens embedded line breaks, and percent-encoded `file:///` destinations.
Explicit generated anchors avoid punctuation/Unicode heading-slug ambiguity.
The sibling temporary file avoids the old predictable `.tmp` symlink hazard and
cross-device rename failures. It is hidden and excluded from directory scans.
Concurrent report writers use distinct temporaries; the last replacement wins.
The file is synced before replacement, but the directory is not fsynced, so this
is not a promise of power-loss durability on every filesystem.

### Validation and remaining target

- Baseline: **1,306 passed, 1 skipped**.
- Added **28 tests** for metadata on all outcomes and cancellation, hierarchy,
  confidence, clusters, legacy/empty records, Unicode/Markdown paths, local URI
  actions, and injected partial-write/sync/replace failures with cleanup.
- Full suite: **1,334 passed, 1 skipped**, preserving pytest's actual exit status
  despite the existing Qt teardown exit-zero backstop.
- The entire original execution-loop AST matches the pre-phase snapshot;
  `FileUtils` SHA-256 is unchanged. Compilation and whitespace checks pass.
- A separate CommonMark render check confirms adversarial paths/cluster names
  and evidence do not create script/image elements or remote hyperlinks.
- Measured 500 records, 10 clusters, two evidence strings per record, approximately
  432 KB of Markdown: first call **30.634 ms**, warmed median **29.559 ms**, range
  **27.669–31.283 ms** over 20 runs, including write/flush/fsync/replace. The **2 ms
  target is not met**. These are local observations rather than portable latency
  guarantees. Phase 17 remains the next performance/caching phase.
