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
- `src/core/file_intelligence/metadata.py`: Add an opt-out keyword for the
  builder's legacy xattr probe; existing callers retain the default behavior.
- `src/core/file_intelligence/classifier.py`: Accept the explicit
  `cluster.inferred_domain` source field used by batch integration.
- `src/core/file_intelligence/relationships.py`: Exclude weak directory/extension
  votes from typed cluster-domain consensus, as required by integration fixtures.

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

Implementation evaluates a batch snapshot of configured rules before deep
profiling: matching rules bypass content/history reads and still use the Phase
12 planner. Only unmatched, successfully profiled contexts enter clustering.
This preserves policy precedence and avoids work whose result would be discarded.

## Error Handling
- Failed extractions fall back to standard extension-based categorization.
- Existing failure isolation during `execute()` remains strictly enforced.

## Security Considerations
- Zero change to 6-stage copy-verify-delete protocol.
- Root path containment verified on every proposed move.

## Performance Considerations
- Target: batch intelligence analysis for 100 files executes in < 1.0 second.
  Markdown and matched-rule fixtures meet it; PDF analysis does not (see below).

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_integration_directory.py`:
  - Test batch academic directory organizing into `College/Course/Subtype/`.
  - Test batch project directory organizing into `Projects/Project/Source/`.
  - Test dry-run preview verifies zero filesystem mutations.
  - Regression: Run all 28 existing tests in `tests/test_directory_organizer.py` verifying 100% pass.

## Acceptance Criteria
- [x] `DirectoryOrganizer` integrates intelligence pipeline.
- [x] Existing 28 `test_directory_organizer.py` tests pass without modification.
- [x] 100% test pass on `test_integration_directory.py`.

## Dependencies
- Standard library and internal intelligence modules.

## What This Phase MUST NOT Change
- Must NOT alter the 6-stage transfer loop in `execute()`.
- Must NOT alter `FileUtils.safe_copy()`.

## Completion Checklist
- [x] `directory_organizer.py` updated.
- [x] Integration tests passing.
- [x] Existing test suite passing 100%.

## Implementation State — 2026-11-18

Functional integration is complete in the local working tree. Unmatched files
receive filesystem ingestion, configured origin detection, content extraction,
signals, batch clustering, classification and proposal generation. Configured
rules remain authoritative, including broad defaults. Cluster-domain hints use
the existing correlated cluster channel and never count as independent evidence.
Directory/extension votes no longer contaminate typed cluster root consensus.

Plan items expose confidence, numeric score, evidence, cluster ID/name and source
identity snapshots. Plans/previews expose detected cluster count and warnings;
all appended fields have defaults, preserving existing positional constructors.
Counts retain their existing meaning: planned moves, excluding no-ops/rejections.
No GUI confidence/evidence display or download-watcher integration is added.

Failed extraction/classification falls back per file to a fixed extension
category with UNKNOWN confidence. Origin errors preserve content classification;
clustering errors or the 2,000-profile graph limit preserve individual analysis.
Unsafe proposals/rules are excluded rather than silently rerouted. Source and
policy snapshots prevent mixing changed files or mid-batch rule edits into a
plan. Origin opt-out prevents xattr/history probing in this pipeline.

Before writes, execution rechecks root/source/target after progress callbacks,
rejecting stale identities and current symlink escapes. Directory-creation
errors are isolated per file. The collision/copy/size/hash/cleanup/delete block
is unchanged, and `FileUtils` is unchanged. These are additional preconditions,
not a rewrite of the six-stage protocol or a claim of kernel-enforced race-free
execution. Cancellation retains the existing worker/transfer boundaries.

Validation:

- Baseline: **1,186 passed, 1 skipped**, actual exit code 0.
- Added **46 integration tests** for real academic/archive-project hierarchies,
  sparse inheritance, rule precedence/updates, dry-run source/tree/config
  preservation, origin settings, isolated failures, graph budgets, exclusions,
  stale plans, unsafe destinations, collisions, duplicates, cancellation and
  fresh-process Qt-free imports.
- All **28 existing directory-organizer tests pass unchanged**.
- Full suite: **1,232 passed, 1 skipped** in 19.85 s, genuine pytest exit code
  **0** preserved before the existing Qt teardown exit-zero hook.
- Source compilation and whitespace checks pass. Direct source/hash comparisons
  confirm the original transfer block and `FileUtils` are unchanged.

Local 100-file preview timings with origin history detection disabled:

| Fixture | Seconds | Clusters | Warnings |
| --- | --- | ---: | ---: |
| Markdown intelligence, three runs | 0.0541 / 0.0576 / 0.0526 | 1 | 0 |
| Matched custom policy, three runs | 0.0139 / 0.0157 / 0.0137 | 0 | 0 |
| PDF intelligence, one run | 23.3076 | 1 | 0 |

All runs planned 100 files without moving them. The **universal one-second target
remains outstanding**, particularly for PDF worker/backend startup and parsing
(a known Phase 04 limitation). Enabled browser snapshots and larger/slower
inputs can add latency. This phase introduces no persistent cache, parallel
worker pool or global analysis deadline.

See [directory-integration.md](../directory-integration.md) for exact behavior and
boundaries. Next: **Phase 14 — Download Organizer Integration & Real-Time Profiling**.
