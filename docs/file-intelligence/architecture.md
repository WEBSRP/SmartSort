# SmartSort File Intelligence Engine: Architecture

## 1. Architectural Philosophy

SmartSort File Intelligence Engine follows a strict **unidirectional pipeline architecture** designed around the separation of four fundamental questions:

1. **What is this file?** $\rightarrow$ Handled by the **Metadata & Content Extraction Layer** and **Origin Detection Layer**.
2. **What context does this file share?** $\rightarrow$ Handled by the **Signal Extraction** and **Relationship Discovery Layer**.
3. **Where should this file go?** $\rightarrow$ Handled by the **Classification** and **Organization Planning Layer**.
4. **How do we safely move it?** $\rightarrow$ Handled by the **Existing SmartSort Safe Transfer Engine** (`FileUtils` / `DirectoryOrganizer`).

Under no circumstances does intelligence or classification code execute file transfers or delete files.

---

## 2. Layered Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. INGESTION LAYER                                                          │
│    - File Path Validation, Inode/Device Verification, Boundary Checks       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. METADATA & EXTRACTOR PIPELINE (Pure Python, Zero Qt)                     │
│    - Basic Filesystem / Stat (Size, Times, Inode, Permissions)              │
│    - Pluggable Format Extractors (Text, PDF, Office, Media, Code, Archives)  │
│    - Local Origin Detector (xattrs, Local Browser SQLite DBs)               │
│    - Output: Immutable `FileContext` / `FileProfile` Data Object            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. SIGNAL EXTRACTION LAYER                                                  │
│    - Tokenization, Stemming, Keyword Extraction                             │
│    - Weighted Signal Generation (Filename, Headers, Text, Metadata, Origin) │
│    - Output: Normalized `SignalSet`                                         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. RELATIONSHIP & CLUSTER ENGINE                                            │
│    - Single-file mode: Parent/Directory Context Evaluation                  │
│    - Batch mode: Deterministic Lexical & Semantic Clustering                │
│    - Shared Context Discovery (Common Courses, Projects, Sibling Clusters)  │
│    - Output: `FileCluster` & `ClusterContext`                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. MULTI-SIGNAL CLASSIFIER & CONFIDENCE ENGINE                             │
│    - Domain Taxonomy Evaluator (Academic, Development, Security, Work, etc) │
│    - Multi-Signal Evidence Aggregator & Weighted Scoring                    │
│    - Confidence Estimator (CONFIRMED, PROBABLE, LOW, UNKNOWN)               │
│    - Explicit Evidence Formulation                                          │
│    - Output: `ClassificationResult`                                         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. ORGANIZATION PLANNER                                                     │
│    - Dynamic Hierarchical Path Generation (`Domain/Subject/Category/...`)   │
│    - User Rule Engine Precedence & Fallback Arbitration                     │
│    - Sanitization & Path Containment Validation                             │
│    - Output: `OrganizationProposal`                                         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                  ┌────────────────────┴────────────────────┐
                  ▼                                         ▼
┌───────────────────────────────────┐     ┌───────────────────────────────────┐
│ 7A. DIRECTORY ORGANIZER           │     │ 7B. DOWNLOAD MONITOR (DAEMON)     │
│     - Batch Execution Plan        │     │     - Single File Event Handling  │
│     - Preview Dry-Run Modal       │     │     - Real-Time Proposal Review   │
│     - User Approval Workflow      │     │     - Notification Integration    │
└─────────────────┬─────────────────┘     └─────────────────┬─────────────────┘
                  │                                         │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 8. INVIOLABLE 6-STAGE SAFE TRANSFER ENGINE                                  │
│    1. Destination Pre-Check & Dynamic Unique Collision Path Resolution     │
│    2. Duplicate Check (Identical SHA-256 -> Source Preserved, Dest Untouched)│
│    3. `shutil.copy2` Transfer                                               │
│    4. Destination Verification (Existence, Regular File, Size, SHA-256)     │
│    5. Source Removal (`os.remove`)                                          │
│    6. Source Deletion Verification                                          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 9. AUDIT & REPORTING                                                        │
│    - Atomic `SmartSort_Arrangement.md` Generation                           │
│    - Clickable `file:///` Local URIs                                        │
│    - Monospace UI Summary                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Module Layout (`src/core/file_intelligence/`)

The File Intelligence Engine is encapsulated inside `src/core/file_intelligence/`:

```text
src/core/file_intelligence/
├── __init__.py                # Package exports and public interface
├── context.py                 # FileContext, FileProfile, Evidence, Confidence Enums
├── metadata.py                # Filesystem stat and extended attribute extraction
├── mime.py                    # Deterministic MIME type and extension categorization
├── origin.py                  # Local browser SQLite and xattr origin provenance
├── signals.py                 # Tokenization, keyword extraction, and signal weights
├── relationships.py           # Deterministic multi-file clustering and relationship graph
├── classifier.py              # Domain taxonomy, evidence aggregator, and scoring
├── planner.py                 # Hierarchical organization proposal generator
├── cache.py                   # XDG-compliant disk and memory caching layer
└── extractors/                # Pluggable format extractors
    ├── __init__.py            # Extractor registry and dispatch
    ├── base.py                # BaseExtractor abstract base class
    ├── text.py                # Plaintext, Markdown, CSV, Log extractor
    ├── pdf.py                 # PDF metadata and text extractor (pypdf/fallback)
    ├── docx.py                # Word document extractor (python-docx/XML)
    ├── pptx.py                # PowerPoint presentation extractor (python-pptx/XML)
    ├── xlsx.py                # Excel spreadsheet extractor (openpyxl/XML)
    ├── image.py               # Image EXIF and metadata extractor (Pillow)
    ├── media.py               # Audio and video metadata extractor (mutagen/headers)
    ├── code.py                # Source code and script token extractor
    └── archive.py             # Archive table-of-contents extractor (zip/tar/gz/7z)
```

---

## 4. Architectural Invariants

### Invariant 1: Zero Qt Dependencies in Core
All files in `src/core/file_intelligence/` must have **zero imports** of PyQt6, Qt widgets, Qt signals, or Qt threads. Intelligence operations run in pure Python data pipelines, enabling 100% headless testability without display servers or GUI event loops.

### Invariant 2: Inviolability of Transfer Engine
The File Intelligence Engine outputs `OrganizationProposal` objects. It is strictly forbidden for any classifier, extractor, or planner to call `shutil.move`, `shutil.copy2`, `os.remove`, or `os.rename`. All physical modifications are delegated to the tested 6-stage transfer engine in `DirectoryOrganizer` and `FileUtils`.

### Invariant 3: Zero Network / Zero Cloud
Every extractor and origin detector functions entirely locally. No HTTP requests, socket connections, or external cloud API calls are made. If local evidence is absent, the state is explicitly marked as `Confidence.UNKNOWN` rather than queried from the internet.

### Invariant 4: Graceful Degradation on Missing Dependencies
If an optional third-party library (e.g. `pypdf`, `python-docx`, `mutagen`, `Pillow`) is missing from the environment:
- The system must not crash or fail to initialize.
- The corresponding extractor falls back to lightweight pure-Python parsing (e.g. XML inspection for OOXML) or gracefully reports `NOT_AVAILABLE`.
- Classification continues using available signals (filename, origin, filesystem stats).
