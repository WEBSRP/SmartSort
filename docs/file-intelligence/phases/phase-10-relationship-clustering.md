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
- **Graph Clustering**: Builds adjacency graph with edges $\ge 0.60$; extracts connected components using Breadth-First Search (BFS).
- **Cluster Name Synthesis**: Finds the most frequent shared canonical tokens across the cluster (e.g. `['dbms', 'lecture']` $\rightarrow$ `DBMS_Lectures`).

## Error Handling
- Handles single-file lists, disjoint graphs, and empty token sets gracefully.

## Security Considerations
- Graph traversal complexity is bounded ($O(N^2)$ for typical directory batches of $N \le 2000$ files).

## Performance Considerations
- Clustering 500 files executes in < 25 ms.

## CI / Headless Requirements
- Pure Python standard library. Zero Qt imports. 100% headless.

## Tests
- `tests/test_file_intelligence/test_relationships.py`:
  - Test course lecture cluster (`Lecture_1_DBMS.pdf`, `Lecture_2_DBMS.pptx`, `Lecture_3_DBMS.zip`).
  - Test project cluster (`SmartSort_Report.docx`, `SmartSort_Code.zip`).
  - Test unrelated files forming disjoint clusters or remaining unclustered.
  - Test context propagation and confidence boosting on sparse files.

## Acceptance Criteria
- [ ] `RelationshipEngine` accurately clusters related files.
- [ ] Cluster context and names correctly synthesized.
- [ ] 100% test pass on `test_relationships.py`.

## Dependencies
- Standard library (`collections`, `typing`).

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [ ] `relationships.py` implemented.
- [ ] Unit tests passing.
