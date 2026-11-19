# Phase 10: File Relationship Discovery & Cluster Analysis

## Objective
Implement `src/core/file_intelligence/relationships.py` (`RelationshipEngine`) to detect relationships between files, discover shared project/course clusters deterministically, and propagate cluster context across sibling files.

## Why This Phase Exists
Files frequently belong to cohesive clusters (e.g. `Lecture_1_DBMS.pdf`, `Lecture_2_DBMS.pptx`, `Lecture_3_DBMS.zip`). Discovering these relationships allows the system to place all related files into a common directory hierarchy (e.g. `College/DBMS/Lectures/`) and allows files with sparse metadata to inherit confidence from their siblings.

## Inputs
- List of `FileContext` instances (in Directory Organizer batch mode or sibling scan).

## Outputs
- `src/core/file_intelligence/relationships.py` (`RelationshipEngine`).
- Tests in `tests/test_file_intelligence/test_relationships.py`.

## Files To Create
- `src/core/file_intelligence/relationships.py`
- `tests/test_file_intelligence/test_relationships.py`

## Files To Modify
- `src/core/file_intelligence/__init__.py`: Export `RelationshipEngine`.
- `src/core/file_intelligence/context.py`: Implement the relationship models and
  serialize reversible relationship confidence bookkeeping on `FileContext`.

## Existing Components To Reuse
- `src/core/file_intelligence/context.py`: Uses `FileCluster`, `FileRelationship`.

## APIs / Interfaces
```python
# src/core/file_intelligence/relationships.py
class RelationshipEngine:
    SIMILARITY_THRESHOLD: float = 0.60

    def cluster_files(self, contexts: List[FileContext]) -> List[FileCluster]:
        """Discovers clusters and links FileContexts to their respective FileCluster."""
        ...

    def calculate_similarity(self, ctx_a: FileContext, ctx_b: FileContext) -> Tuple[float, Set[str]]:
        """Calculates multi-dimensional similarity score between two FileContexts."""
        ...
```

## Data Structures
- Consumes `FileContext` list; produces `FileCluster` objects and updates `context.cluster_id`.

## Algorithms
- **Multi-Dimensional Similarity Metric**:
  - Token Jaccard Similarity: $J = \frac{|T_A \cap T_B|}{|T_A \cup T_B|} \times 0.65$
  - Shared Origin Bonus: $+0.20$ if domains match.
  - Temporal Proximity Bonus: $+0.15$ if created/downloaded within 15 minutes.
  - Series Numbering Match: $+0.25$ for sequential patterns (`Lecture_01`, `Lecture_02`).
- **Graph Clustering**: Builds guarded connected components with edges $\ge 0.60$;
  union-find retains spanning witnesses and BFS extracts the components. Ambiguous
  sparse members cannot bridge separate core components.
- **Cluster Name Synthesis**: Finds the most frequent shared canonical tokens across the cluster (e.g. `['dbms', 'lecture']` $\rightarrow$ `DBMS_Lectures`).

## Error Handling
- Handles single-file lists, disjoint graphs, and empty token sets gracefully.

## Security Considerations
- Graph traversal complexity is bounded ($O(N^2)$ for typical directory batches of $N \le 2000$ files).

## Performance Considerations
- Target: clustering 500 files executes in < 25 ms. Measured fixtures meet this
  target; it is not a hard deadline for every input (see implementation notes).

## CI / Headless Requirements
- Pure Python standard library. Zero Qt imports. 100% headless.

## Tests
- `tests/test_file_intelligence/test_relationships.py`:
  - Test course lecture cluster (`Lecture_1_DBMS.pdf`, `Lecture_2_DBMS.pptx`, `Lecture_3_DBMS.zip`).
  - Test project cluster (`SmartSort_Report.docx`, `SmartSort_Code.zip`).
  - Test unrelated files forming disjoint clusters or remaining unclustered.
  - Test context propagation and confidence boosting on sparse files.

## Acceptance Criteria
- [x] `RelationshipEngine` accurately clusters related files.
- [x] Cluster context and names correctly synthesized.
- [x] 100% test pass on `test_relationships.py`.

## Dependencies
- Standard library (`collections`, `typing`).

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [x] `relationships.py` implemented.
- [x] Unit tests passing.

## Implementation State — 2026-11-15

Implemented and exported `RelationshipEngine`, `FileRelationship`, and
`FileCluster`. The models include JSON helpers and finite score validation.
Cluster IDs and names are deterministic across batch permutations; retained
relationships are bounded spanning witnesses. Numbered series allow gaps,
same-origin/time evidence supplements canonical identity overlap, and safe
archive TOC matches provide filename evidence. Weak channels and generic role
words do not establish identity. Sparse ambiguity guards prevent an unnamed
lecture from joining different course clusters.

Content-sparse files inherit supported keywords through `CLUSTER_CONTEXT`.
Confidence bookkeeping makes boosts reversible and repeat-safe, including JSON
round-trips. This phase populates cluster-level domain/hierarchy hints but does
not select per-file classification or destinations. Only the supplied batch is
updated; no filesystem, network, GUI or organizer integration is introduced.

Validation:

- Baseline: **952 passed, 1 skipped**.
- Added **66 relationship test cases** covering scoring, graphs, serialization,
  ambiguity, idempotence, input bounds, deterministic output and headless/no-I/O
  execution.
- Full suite: **1,018 passed, 1 skipped** in 16.84 s; actual pytest exit code 0
  preserved despite the existing test teardown's forced process exit.
- Source compilation and `git diff --check` pass.
- Isolated 500-file median timings: lectures **21.542 ms**, disjoint identities
  **11.605 ms**, overlapping near misses **14.345 ms**. Maximum measured subsequent
  runs: 22.872, 17.160 and 16.012 ms respectively, with precomputed signals.

Limits: 2,000 contexts, 256 identity tokens per file, 32,768 vocabulary entries,
bounded signal/TOC inputs and a batch-local normalization cache. Worst-case
candidate comparisons and related-path output remain quadratic. Cluster
confidence is a mean spanning-witness score, not a calibrated classification
probability. Connected components are transitive; archive name matches do not
prove content identity. See [relationships.md](../relationships.md) for details.

Next: **Phase 11 — Multi-Signal Domain Classification & Confidence Scoring**.
