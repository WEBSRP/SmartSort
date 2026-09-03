# SmartSort File Intelligence Engine: Directory Organizer Integration

## 1. Overview & Batch Workflow

The **Directory Organizer** operates on entire directory trees in **batch mode**. Unlike single-file download processing, batch mode has the distinct advantage of analyzing sibling files simultaneously to discover multi-file clusters, project structures, and course groupings.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ DIRECTORY ORGANIZER BATCH PIPELINE                                          │
│                                                                             │
│  [Target Directory Selected]                                                │
│         │                                                                   │
│         ▼                                                                   │
│  1. Snapshot Scan (Shallow or Recursive, exclusions applied)                │
│         │                                                                   │
│         ▼                                                                   │
│  2. Batch Ingestion & Parallel/Sequential Metadata Extraction               │
│     $\rightarrow$ Generates List[FileContext]                                │
│         │                                                                   │
│         ▼                                                                   │
│  3. Relationship & Community Discovery Clustering                           │
│     $\rightarrow$ Groups related files into FileClusters                    │
│         │                                                                   │
│         ▼                                                                   │
│  4. Multi-Signal Classification & Confidence Assignment                     │
│     $\rightarrow$ Enriches FileContext with Domain, Subcategories, Evidence │
│         │                                                                   │
│         ▼                                                                   │
│  5. Organization Planning                                                   │
│     $\rightarrow$ Generates OrganizePlan (PlanItems + Confidence + Evidence)│
│         │                                                                   │
│         ├────────────────────────────────────────┐                          │
│         ▼ (Preview Mode)                         ▼ (Organize Mode)          │
│  6A. Return Preview Summary               6B. Safe 6-Stage Execution        │
│      (Zero filesystem changes)                - Dynamic unique collisions   │
│                                               - Duplicate preservation      │
│                                               - SHA-256 copy-verify-delete  │
│                                                  │                          │
│                                                  ▼                          │
│                                           7. Generate Enhanced              │
│                                              Arrangement Index MD           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. DirectoryOrganizer Class Interface Enhancement

The existing `DirectoryOrganizer` in `src/core/directory_organizer.py` is extended to integrate the intelligence pipeline while preserving 100% backward compatibility:

```python
class DirectoryOrganizer:
    def __init__(self, config: ConfigManager, logger: SmartSortLogger):
        self.config = config
        self.logger = logger
        self.rule_manager = RuleManager(config)
        self.extractor_registry = ExtractorRegistry()
        self.origin_detector = OriginDetector(config)
        self.relationship_engine = RelationshipEngine()
        self.classifier = MultiSignalClassifier(config)
        self.planner = OrganizationPlanner(self.rule_manager, config)

    def preview(self, root_dir: str, recursive: bool = False) -> DirectoryPreviewSummary:
        """Runs the complete intelligence pipeline in dry-run mode."""
        self._validate_root(root_dir)
        file_paths = self.scan(root_dir, recursive=recursive)
        plan = self.plan(root_dir, file_paths)
        return DirectoryPreviewSummary(
            total_files=plan.total_files,
            category_counts=plan.category_counts,
            items=plan.items
        )

    def plan(self, root_dir: str, file_paths: List[str]) -> OrganizePlan:
        """Builds an intelligent, cluster-aware organization plan."""
        # 1. Extract FileContext for every file
        contexts = []
        for path in file_paths:
            ctx = self._build_file_context(path)
            contexts.append(ctx)

        # 2. Cluster related files
        clusters = self.relationship_engine.cluster_files(contexts)

        # 3. Classify each context with cluster consensus
        for ctx in contexts:
            self.classifier.classify(ctx)

        # 4. Generate organization proposals
        plan_items = []
        category_counts = {}
        for ctx in contexts:
            proposal = self.planner.plan_file(ctx, root_dir)
            item = OrganizePlanItem(
                source_path=proposal.source_path,
                target_path=proposal.target_path,
                category=proposal.domain,
                rule_name=proposal.rule_name or "Intelligence",
                confidence=proposal.confidence_level.value,
                evidence=[e.description for e in proposal.evidence]
            )
            plan_items.append(item)
            category_counts[proposal.domain] = category_counts.get(proposal.domain, 0) + 1

        return OrganizePlan(
            items=plan_items,
            root_dir=root_dir,
            total_files=len(file_paths),
            category_counts=category_counts
        )
```

---

## 3. UI Display & Explanation

The GUI results and preview summaries in `src/gui/main_window.py` present both destination proposals and evidence justifications:

```text
=== DRY-RUN PREVIEW SUMMARY ===
Total Files Found: 4
Clusters Detected: 1 (DBMS Course Material)

Category Breakdown:
  • College/DBMS/Lectures: 3 file(s)
  • Images: 1 file(s)

Planned Moves:
  Lecture_1_DBMS.pdf -> College/DBMS/Lectures/Lecture_1_DBMS.pdf [CONFIRMED (92%)]
    └ Evidence: Title match ("DBMS Normalization"), Canvas LMS Origin, Sibling Cluster
  Lecture_3_DBMS.zip -> College/DBMS/Lectures/Lecture_3_DBMS.zip [CONFIRMED (88%)]
    └ Evidence: Archive contains PPTX/PDF, Canvas LMS Origin, Sibling Cluster
  logo.png           -> Images/logo.png                          [PROBABLE (65%)]
```
