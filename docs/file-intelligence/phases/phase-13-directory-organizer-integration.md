# Phase 13: Directory Organizer Integration & Batch Profiling

## Objective
Integrate the File Intelligence pipeline into `src/core/directory_organizer.py` (`DirectoryOrganizer`), enabling batch multi-file relationship discovery, intelligent hierarchy generation, and dry-run preview while preserving the inviolable 6-stage transfer engine and 100% backward compatibility.

## Why This Phase Exists
This phase connects the intelligence components built in Phases 01-12 to the existing Directory Organizer feature. It elevates batch organization from flat extension sorting to cluster-aware, hierarchical subfolder organization.

## Inputs
- Directory path string and user configuration.

## Outputs
- Updated `src/core/directory_organizer.py` with intelligence integration.
- Tests in `tests/test_file_intelligence/test_integration_directory.py`.

## Files To Create
- `tests/test_file_intelligence/test_integration_directory.py`

## Files To Modify
- `src/core/directory_organizer.py`: Integrate intelligence components into `plan()`, `preview()`, and `execute()`.

## Existing Components To Reuse
- `src/core/directory_organizer.py`: Reuses `scan()`, `execute()`, `generate_report()`, `_validate_root()`.
- `src/core/file_intelligence/`: Uses `ExtractorRegistry`, `OriginDetector`, `RelationshipEngine`, `MultiSignalClassifier`, `OrganizationPlanner`.

## APIs / Interfaces
```python
# src/core/directory_organizer.py
@dataclass
class OrganizePlanItem:
    source_path: str
    target_path: str
    category: str
    rule_name: str
    confidence: str = "CONFIRMED"                # Added for intelligence
    evidence: List[str] = field(default_factory=list) # Added for intelligence

@dataclass
class DirectoryPreviewSummary:
    total_files: int
    category_counts: Dict[str, int]
    items: List[OrganizePlanItem]
    cluster_count: int = 0                       # Added for intelligence
```

## Data Structures
- Enriched `OrganizePlanItem` and `DirectoryPreviewSummary` dataclasses.

## Algorithms
- **Batch Processing Pipeline in `DirectoryOrganizer.plan()`**:
  1. Build initial `FileContext` for all scanned files.
  2. Run `OriginDetector.detect_origin()` on each context.
  3. Run `ExtractorRegistry.extract_metadata()` on each context.
  4. Run `SignalExtractor.extract_signals()` on each context.
  5. Run `RelationshipEngine.cluster_files()` across all contexts.
  6. Run `MultiSignalClassifier.classify()` on each context.
  7. Run `OrganizationPlanner.plan_file()` to generate `OrganizePlan`.

## Error Handling
- Failed extractions fall back to standard extension-based categorization.
- Existing failure isolation during `execute()` remains strictly enforced.

## Security Considerations
- Zero change to 6-stage copy-verify-delete protocol.
- Root path containment verified on every proposed move.

## Performance Considerations
- Batch intelligence analysis for 100 files executes in < 1.0 second.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_integration_directory.py`:
  - Test batch academic directory organizing into `College/Course/Subtype/`.
  - Test batch project directory organizing into `Projects/Project/Source/`.
  - Test dry-run preview verifies zero filesystem mutations.
  - Regression: Run all 28 existing tests in `tests/test_directory_organizer.py` verifying 100% pass.

## Acceptance Criteria
- [ ] `DirectoryOrganizer` integrates intelligence pipeline.
- [ ] Existing 28 `test_directory_organizer.py` tests pass without modification.
- [ ] 100% test pass on `test_integration_directory.py`.

## Dependencies
- Standard library and internal intelligence modules.

## What This Phase MUST NOT Change
- Must NOT alter the 6-stage transfer loop in `execute()`.
- Must NOT alter `FileUtils.safe_copy()`.

## Completion Checklist
- [ ] `directory_organizer.py` updated.
- [ ] Integration tests passing.
- [ ] Existing test suite passing 100%.
