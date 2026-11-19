# Phase 11: Multi-Signal Domain Classification & Confidence Scoring

## Objective
Implement `src/core/file_intelligence/classifier.py` (`MultiSignalClassifier`) to evaluate multi-signal evidence, determine domain classifications and subcategory hierarchies, calculate epistemic confidence scores, and generate transparent evidence lists.

## Why This Phase Exists
This is the core cognitive layer of the File Intelligence Engine. It synthesizes signals from content extractors, origin provenance, and relationship clusters to answer "What domain and subcategory does this file belong to?" with clear, verifiable confidence and evidence reasons.

## Inputs
- `FileContext` enriched with metadata, origin info, signals, and optional cluster reference.

## Outputs
- `src/core/file_intelligence/classifier.py` (`MultiSignalClassifier`).
- Tests in `tests/test_file_intelligence/test_classifier.py`.

## Files To Create
- `src/core/file_intelligence/classifier.py`
- `tests/test_file_intelligence/test_classifier.py`

## Files To Modify
- `src/core/file_intelligence/__init__.py`: Export `MultiSignalClassifier`.

## Existing Components To Reuse
- `src/core/file_intelligence/context.py`: Uses `ConfidenceLevel`, `EvidenceItem`, `SignalType`.

## APIs / Interfaces
```python
# src/core/file_intelligence/classifier.py
class MultiSignalClassifier:
    def __init__(self, config: Optional[ConfigManager] = None):
        self.config = config

    def classify(self, context: FileContext) -> None:
        """
        Evaluates signals, populates classification_domain, subcategories,
        confidence, confidence_score, and evidence_list directly on context.
        """
        ...

    def evaluate_domain_scores(self, context: FileContext) -> Dict[str, float]:
        """Calculates normalized affinity scores across all domains."""
        ...
```

## Data Structures
- Updates `FileContext.classification_domain`, `FileContext.subcategories`, `FileContext.confidence`, `FileContext.confidence_score`, `FileContext.evidence_list`.

## Algorithms
- **Multi-Channel Evidence Aggregation**:
  - Evaluates weighted evidence across Title (0.25), Origin (0.20), Content (0.20), Filename (0.15), Cluster (0.15), Archive (0.05).
- **Subcategory Extraction**:
  - Extracts subject/course name (e.g. `DBMS`, `OS`, `Machine_Learning`).
  - Identifies subtype (`Lectures`, `Assignments`, `Labs`, `Exams`, `Documentation`, `Source`).
- **Epistemic Confidence Formula**:
  - Score $\ge 0.85$ with $\ge 2$ corroborating channels $\rightarrow$ `ConfidenceLevel.CONFIRMED`.
  - Score $\ge 0.60 \rightarrow$ `ConfidenceLevel.PROBABLE`.
  - Score $\ge 0.35 \rightarrow$ `ConfidenceLevel.UNCERTAIN`.
  - Score $< 0.35 \rightarrow$ `ConfidenceLevel.UNKNOWN` (falls back to `Others`).
- **Evidence List Construction**: Creates human-readable `EvidenceItem` records for every contributing signal.

## Error Handling
- Contexts with missing or empty metadata default cleanly to `classification_domain="Others"`, `confidence=ConfidenceLevel.UNKNOWN`.

## Security Considerations
- Pure computation on internal dataclass fields.

## Performance Considerations
- Target: classification executes in < 0.1 ms per file. This is not yet met by
  the validated academic/project fixtures; see implementation measurements below.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_classifier.py`:
  - Test Academic file (`Lecture_3_DBMS.zip` $\rightarrow$ `College/DBMS/Lectures/` with `CONFIRMED`).
  - Test Project file (`SmartSort_Source.zip` $\rightarrow$ `Projects/SmartSort/Source/`).
  - Test Cybersecurity file (`nmap_scan.xml` $\rightarrow$ `Cybersecurity/Reports/`).
  - Test ambiguous file (`random.zip` $\rightarrow$ `Archives/` or `Others/` with `UNKNOWN`).
  - Test evidence list completeness and accuracy.

## Acceptance Criteria
- [x] `MultiSignalClassifier` accurately classifies files across all domains.
- [x] Confidence levels and evidence lists correctly populated.
- [x] 100% test pass on `test_classifier.py`.

## Dependencies
- Standard library (`typing`, `math`).

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [x] `classifier.py` implemented.
- [x] Unit tests passing.

## Implementation State — 2026-11-17

Functional implementation is complete in the local working tree. Added and
exported `MultiSignalClassifier`, with no new dependencies or Qt imports. The
constructor accepts the reserved config argument without creating or accessing
a configuration manager. Classification and score evaluation perform no I/O.

The classifier reuses Phase 09 affinities and rolls aliases up to the seven
taxonomy roots without double-counting Code/Projects or Personal/Work votes.
Available semantic channel weights are normalized to handle missing evidence;
signal weights scale reliability relative to their Phase 09 base weights.
Repeated tokens are deduplicated within channels. Headings, body text, code and
media metadata share the content channel. Origin features must match validated
context provenance. Directory/extension hints are capped fallback evidence and
do not corroborate or dilute semantic evidence.

Confidence uses the documented thresholds, single-channel cap and three-channel
boost. Only channels uniquely favoring the winner count as corroboration;
inherited cluster hints do not count as independent observations. Near-tied
domains are capped below PROBABLE. Scores are deterministic heuristics, not
calibrated probabilities. Counterevidence is retained in the evidence list.

Hierarchies recognize supported course names/codes, explicit project prefixes
and taxonomy subtypes. Filename subtype evidence precedes title and signal
fallbacks. Context-specific code language handling covers every Phase 07
language, including lexical splitting of TypeScript/JavaScript and SQL alias
folding. Unrecognized naming patterns may yield a subtype without a topic or
project name; this phase does not implement general entity recognition.

Repeated, permuted and JSON-reloaded classifications replace stale outputs and
remain stable. Classification recomputes confidence from signals and clears old
relationship confidence bookkeeping, preventing cumulative boosts across
cluster/classifier cycles. Signals, cluster links, metadata, provenance and
proposed destinations are otherwise preserved. No organizer, planner, GUI or
transfer code was modified.

Validation:

- Baseline: **1,018 passed, 1 skipped**.
- Added **73 classifier test cases**, including all taxonomy roots, exact
  scoring/thresholds, conflicts, weak hints, duplicate channels, code languages,
  origin validation, safe evidence/hierarchy fields, JSON/idempotence, hash-seed
  determinism, signal bounds, no-I/O execution and Qt-free fresh imports.
- Full suite: **1,091 passed, 1 skipped** in 18.92 s; actual pytest exit code
  **0**, preserved before the existing Qt teardown's forced exit-zero hook.
- Source compilation and `git diff --check` pass.

Isolated local timings with precomputed signals (101 runs per case; first call,
then median and maximum of 100 subsequent calls, milliseconds):

| Fixture | First | Warm median | Warm maximum |
| --- | ---: | ---: | ---: |
| Academic lecture with LMS origin | 0.2629 | 0.1135 | 0.1720 |
| Project source with repository origin | 0.7371 | 0.1157 | 0.1814 |
| Work invoice | 0.0690 | 0.0537 | 0.1092 |

The **universal 0.1 ms target remains outstanding**. These are local observations,
not deadlines; fallback signal extraction and larger signal sets add work.
Input is bounded to 2,080 signal records/tokens, bounded lexical fields and
validated safe token/source forms. There is no persistent cache or worker.

See [classification.md](../classification.md) for the exact scoring, confidence,
hierarchy and evidence contracts. Next: **Phase 12 — Intelligent Organization
Planner & Hierarchy Generation**.
