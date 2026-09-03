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

## Files To Modify
- `src/organizer.py`: Update `get_category()`, `get_destination_path()`, and `process_file()`.

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
- Total real-time processing latency < 50 ms per download file.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_integration_download.py`:
  - Test simulated incoming PDF download with Canvas LMS origin routing to `College/`.
  - Test simulated incoming GitHub repo archive routing to `Projects/`.
  - Test large video approval flow preserved.
  - Regression: Run all existing download tests (`test_duplicate_detection.py`, `test_filename_cleanup.py`).

## Acceptance Criteria
- [ ] `FileOrganizer` uses intelligence pipeline for categorization.
- [ ] All existing download tests pass 100% without regression.
- [ ] 100% test pass on `test_integration_download.py`.

## Dependencies
- Standard library and internal intelligence modules.

## What This Phase MUST NOT Change
- Must NOT alter `MonitorThread` or watchdog event handling in `src/monitor.py`.

## Completion Checklist
- [ ] `src/organizer.py` updated.
- [ ] Integration tests passing.
- [ ] Existing test suite passing 100%.
