# SmartSort File Intelligence Engine: Relationship Discovery & Clustering

## 1. Overview & Objectives

In real-world environments, files rarely exist in isolation. Course notes, project source code, presentations, and datasets arrive in related clusters:

- `Lecture_1_DBMS.pdf`, `Lecture_2_DBMS.pptx`, `Lecture_3_DBMS.zip`
- `SmartSort_Report.docx`, `SmartSort_Presentation.pptx`, `smartsort_v1.0.tar.gz`
- `scan_results_192.168.1.1.xml`, `nmap_report.txt`, `exploit_notes.md`

The **Relationship & Clustering Engine** discovers these relationships deterministically without using an LLM. It clusters related files so they can be placed into cohesive, common directory hierarchies (e.g. `College/DBMS/Lectures/` or `Projects/SmartSort/`).

---

## 2. Deterministic Clustering Heuristics

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. SERIES & SEQUENTIAL PATTERN MATCHING                                     │
│    - Detects numbered series: `Prefix_[0-9]+_Suffix`                        │
│    - E.g. `Lecture_01_OS.pdf`, `Lecture_02_OS.pdf` $\rightarrow$ `OS_Lectures`      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. TOKEN JACCARD & STEM SIMILARITY                                          │
│    - Computes token overlap across normalized filename & title tokens       │
│    - $J(A, B) = \frac{|Tokens(A) \cap Tokens(B)|}{|Tokens(A) \cup Tokens(B)|}$ │
│    - Threshold: $J(A, B) \ge 0.60$ forms a strong cluster edge               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. PROVENANCE & TEMPORAL CORRELATION                                        │
│    - Files from identical origin domain downloaded within a 15-minute window │
│    - E.g. 6 assignment files downloaded from Canvas in one browser session   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. ARCHIVE CONTENT OVERLAP                                                  │
│    - Matches standalone files against the internal TOC of sibling archives  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Clustering Algorithm

The engine uses a deterministic **Connected-Components / Community Detection** algorithm on a similarity graph:

```python
class RelationshipEngine:
    def cluster_files(self, file_contexts: List[FileContext]) -> List[FileCluster]:
        """Groups FileContexts into cohesive clusters based on multi-signal similarity."""
        n = len(file_contexts)
        adj_matrix = [[] for _ in range(n)]

        # 1. Build Similarity Graph
        for i in range(n):
            for j in range(i + 1, n):
                score, shared_tokens = self.calculate_similarity(file_contexts[i], file_contexts[j])
                if score >= 0.60:
                    adj_matrix[i].append((j, score, shared_tokens))
                    adj_matrix[j].append((i, score, shared_tokens))

        # 2. Extract Connected Components
        visited = set()
        clusters = []
        for i in range(n):
            if i not in visited:
                component = []
                queue = [i]
                visited.add(i)
                while queue:
                    curr = queue.pop(0)
                    component.append(curr)
                    for neighbor, _, _ in adj_matrix[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                
                if len(component) > 1:
                    cluster = self._build_cluster(component, file_contexts, adj_matrix)
                    clusters.append(cluster)

        return clusters

    def calculate_similarity(self, ctx_a: FileContext, ctx_b: FileContext) -> Tuple[float, Set[str]]:
        """Calculates multi-dimensional similarity between two files."""
        # 1. Token Similarity (Jaccard)
        tokens_a = ctx_a.signals.tokens
        tokens_b = ctx_b.signals.tokens
        if not tokens_a or not tokens_b:
            jaccard = 0.0
            shared = set()
        else:
            shared = tokens_a.intersection(tokens_b)
            jaccard = len(shared) / len(tokens_a.union(tokens_b))

        # 2. Origin Match Bonus
        origin_bonus = 0.0
        if ctx_a.origin.domain and ctx_a.origin.domain == ctx_b.origin.domain:
            origin_bonus = 0.20

        # 3. Temporal Window Bonus (Downloaded within 15 mins)
        time_bonus = 0.0
        if abs(ctx_a.created_timestamp - ctx_b.created_timestamp) < 900:
            time_bonus = 0.15

        total_score = min(1.0, jaccard * 0.65 + origin_bonus + time_bonus)
        return total_score, shared
```

---

## 4. Context Propagation & Confidence Boosting

When a file belongs to a strong cluster:
1. **Context Inheritance**: If `Lecture_3.zip` has no internal text or metadata, but belongs to a cluster with `Lecture_1_DBMS.pdf` and `Lecture_2_DBMS.pptx`, it inherits the `DBMS` and `College` context.
2. **Confidence Boosting**:
   $$\text{Confidence}_{\text{boosted}} = \text{Confidence}_{\text{individual}} + 0.30 \times (1.0 - \text{Confidence}_{\text{individual}}) \times \text{ClusterConfidence}$$
3. **Cluster Hierarchy Synthesis**: The common tokens across the cluster form the intermediate folder name (e.g. `College/DBMS/`).
