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
- Classification executes in < 0.1 ms per file.

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
- [ ] `MultiSignalClassifier` accurately classifies files across all domains.
- [ ] Confidence levels and evidence lists correctly populated.
- [ ] 100% test pass on `test_classifier.py`.

## Dependencies
- Standard library (`typing`, `math`).

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [ ] `classifier.py` implemented.
- [ ] Unit tests passing.
