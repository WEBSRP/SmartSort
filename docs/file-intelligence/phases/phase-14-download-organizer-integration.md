# Phase 14: Download Organizer Integration & Real-Time Profiling

## Objective
Integrate the File Intelligence pipeline into `src/organizer.py` (`FileOrganizer`), enabling intelligent profiling, origin resolution, and dynamic subcategory placement for real-time downloads from `~/Downloads`.

## Why This Phase Exists
When users download files in real time, the Download Monitor must immediately analyze the incoming file's provenance (e.g. download URL from browser history) and content to route it to the appropriate subfolder (e.g. `College/DBMS/Assignments/` or `Projects/`) rather than dumping all downloads into a flat `Documents/` folder.

## Inputs
- Single incoming download file path string.

## Outputs
- Updated `src/organizer.py` with intelligence integration.
- Tests in `tests/test_file_intelligence/test_integration_download.py`.

## Files To Create
- `tests/test_file_intelligence/test_integration_download.py`
- `src/core/file_intelligence/extractors/isolated.py`: Enforce the download
  extraction deadline with a killable/reaped child and bounded JSON output.

## Files To Modify
- `src/organizer.py`: Update `get_category()`, `get_destination_path()`, and `process_file()`.
- `src/core/file_intelligence/extractors/base.py`: Add optional bounded dispatch;
  existing default registry behavior is preserved.
- `src/core/file_intelligence/planner.py`: Add a validated target-only filename
  override while retaining original source/rule/provenance identity.

## Existing Components To Reuse
- `src/organizer.py`: Reuses `NotificationManager`, `FilenameCleanup`, `SmartSortLogger`.
- `src/core/file_intelligence/`: Uses `FileContextBuilder`, `OriginDetector`, `ExtractorRegistry`, `MultiSignalClassifier`, `OrganizationPlanner`.

## APIs / Interfaces
```python
# src/organizer.py
class FileOrganizer:
    def __init__(self, config_manager: ConfigManager, logger: SmartSortLogger):
        ...
        self.extractor_registry = ExtractorRegistry()
        self.origin_detector = OriginDetector(config_manager)
        self.classifier = MultiSignalClassifier(config_manager)
        self.planner = OrganizationPlanner(self.rule_manager, config_manager)

    def analyze_download(self, file_path: str, override_filename: Optional[str] = None) -> OrganizationProposal:
        """Profiles an incoming download and generates an intelligent proposal."""
        ...
```

## Data Structures
- Consumes `FileContext`, produces `OrganizationProposal`.

## Algorithms
- **Real-Time Download Pipeline**:
  1. Evaluate `FilenameCleanup` (if enabled) to obtain clean override filename.
  2. Build `FileContext` using `FileContextBuilder`.
  3. Query local browser history and xattr via `OriginDetector.detect_origin()`.
  4. Extract metadata and text snippet via `ExtractorRegistry.extract_metadata()`.
  5. Classify domain and subcategories via `MultiSignalClassifier.classify()`.
  6. Generate destination proposal via `OrganizationPlanner.plan_file()`.
  7. Check large video threshold if applicable.
  8. Execute transfer via `FileUtils.safe_copy()` and delete original.
  9. Dispatch interactive desktop notification with category and file manager highlight.

## Error Handling
- Extraction timeouts (> 2.0s) fall back to extension categorization.
- All file transfer failures preserve the original download in `~/Downloads`.

## Security Considerations
- Zero change to transfer engine. Destination path validated against `destination_base`.

## Performance Considerations
- Target: total real-time processing latency < 50 ms per download file. Matched
  policies meet it on local fixtures; unmatched process-isolated parsing does not.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_integration_download.py`:
  - Test simulated incoming PDF download with Canvas LMS origin routing to `College/`.
  - Test simulated incoming GitHub repo archive routing to `Projects/`.
  - Test large video approval flow preserved.
  - Regression: Run all existing download tests (`test_duplicate_detection.py`, `test_filename_cleanup.py`).

## Acceptance Criteria
- [x] `FileOrganizer` uses intelligence pipeline for categorization.
- [x] All existing download tests pass 100% without regression.
- [x] 100% test pass on `test_integration_download.py`.

## Dependencies
- Standard library and internal intelligence modules.

## What This Phase MUST NOT Change
- Must NOT alter `MonitorThread` or watchdog event handling in `src/monitor.py`.

## Completion Checklist
- [x] `src/organizer.py` updated.
- [x] Integration tests passing.
- [x] Existing test suite passing 100%.

## Implementation State — 2026-11-18

Functional integration is complete in the local working tree. Unmatched
downloads receive ingestion, configured provenance, bounded content extraction,
signals, classification and destination proposals. Matched configured rules
bypass profiling and preserve existing priority/conditions/variables. Policy
and destination-base snapshots remain stable for a processing request. Broad
default rules continue to override semantic routing, as required by precedence.

`analyze_download()` provides read-only proposals. Cleanup names affect only the
target; original paths remain authoritative for rule matching, content and
history lookup. Category/destination hooks share one thread-local proposal
within a `process_file()` call, without persistent path caches. The optional new
planner override keyword leaves existing callers and basename checks intact.

The extraction boundary uses at most two short-lived child processes, a maximum
two-second extraction/slot budget, 512 MiB child address-space and CPU limits,
and a 1 MiB JSON output bound. Timed-out/invalid/crashed workers are killed and
reaped. PDF uses its existing parser directly inside the outer isolated worker,
avoiding nested worker startup. Default registry dispatch is unchanged; bounded
dispatch uses the built-in registry rather than serializing custom instances.

Content/metadata/classifier failures fall back to fixed extension categories
with UNKNOWN confidence; provenance failures retain content-based results.
Origins honor the opt-out flag, with the builder's legacy xattr probe disabled.
Independently enabled filename cleanup retains its previous xattr behavior.
Unsafe rules and changed sources fail without an alternative automatic move.

Video approval covers legacy Videos categories, known video extensions and
detected video MIME types, including semantic Media/custom rule categories.
Concurrent duplicate physical downloads are suppressed only while active;
per-organizer collision/copy decisions are serialized to preserve same-name
downloads. Identity/base/target checks run before copy and before deletion.
Existing duplicate/collision policies, status tuples, successful notification
dispatch and notification-error isolation are preserved. `src/monitor.py` and
`FileUtils` are unchanged, verified by hashes. This does not eliminate all
path-based transfer races or create cross-process destination locks.

Validation:

- Baseline: **1,232 passed, 1 skipped**, actual exit code 0.
- Added **48 integration tests** covering real PDF/LMS and archive/GitHub routes,
  rule short-circuit/snapshots, cleanup/override safety, origin settings, fallback,
  approval, duplicate/collision/copy/notification behavior, stale paths, concurrent
  workers, actual process timeout/reaping, malformed/oversized output and imports.
- Existing download, duplicate, cleanup and notification tests pass unchanged.
- Final full suite: **1,280 passed, 1 skipped** in 20.12 s, genuine pytest exit
  code **0** preserved before the existing Qt teardown's forced exit-zero hook.
- Source compilation and whitespace checks pass; no dependencies or GUI changes.

Local end-to-end processing timings for three small files per fixture, in ms,
including verified copy and source removal. Notifications/history reads were
disabled; PDF/ZIP origin evidence was mocked:

| Fixture | Run 1 | Run 2 | Run 3 |
| --- | ---: | ---: | ---: |
| Markdown invoice | 89.968 | 98.129 | 92.236 |
| Academic PDF | 165.327 | 164.605 | 165.350 |
| GitHub ZIP | 98.992 | 95.232 | 98.934 |
| Matched configured rule | 0.613 | 0.499 | 0.483 |

The **universal 50 ms target remains outstanding**. Isolation startup costs more
than 50 ms even for small unmatched text/archives on this machine. Real history
snapshots and large verified copies add latency. Extraction has an enforced
child deadline; ingestion, provenance, legacy cleanup, OS scheduling/cleanup,
transfer and notifications are not one whole-operation two-second deadline.
The existing GUI worker keeps this synchronous work off the UI/watchdog thread.

See [download-integration.md](../download-integration.md) for exact contracts.
Next: **Phase 15 — GUI Preview, Evidence Display, & Review Workflow**.
