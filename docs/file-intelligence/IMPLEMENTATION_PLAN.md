# SmartSort File Intelligence Engine: Master Implementation Plan

**Target Feature:** SmartSort File Intelligence Engine  
**Target Codebase:** SmartSort (Linux / PyQt6 / Python 3.8+)  
**Author:** Senior Software Architect  
**Audience:** Implementation Engineers & Claude Opus  

---

## 1. Vision & Objectives

The File Intelligence Engine evolves SmartSort from an extension-based rule router into an **intelligent, offline, multi-signal file understanding and hierarchical organization system**.

It operates across diverse domains—including Academic Materials (`College`), Software Engineering (`Projects`), Cybersecurity (`Cybersecurity`), Finance/Legal (`Work`), Media collections (`Media`), and Archives—without requiring cloud connections, network telemetry, or heavyweight machine learning models.

---

## 2. Current Architecture vs. Target Architecture

### 2.1 Current Architecture (v1.1.6)
- **Categorization Model**: Extension matching (`.pdf` $\rightarrow$ `Documents`, `.zip` $\rightarrow$ `Archives`) with regex/size/keyword rules.
- **Scope**: Single-file download monitoring (`FileOrganizer`) and batch directory snapshot traversal (`DirectoryOrganizer`).
- **Safety**: 6-stage copy-verify-delete protocol (`FileUtils` / `DirectoryOrganizer`).

### 2.2 Target Architecture
- **Categorization Model**: Deep multi-signal contextual profiling (`FileContext`), combining content extractors, local browser origin history, token stemming, deterministic relationship clustering, and weighted evidence scoring.
- **Hierarchical Paths**: Dynamic subcategory generation (e.g. `College/DBMS/Lectures/`, `Projects/SmartSort/Source/`).
- **Safety Invariant**: Preserves the existing, verified 6-stage transfer engine completely untouched.

---

## 3. End-to-End Data Flow

```
RAW FILE PATH
     │
     ▼
[Metadata & Ingestion] ───► [Format-Specific Extractor] (Text, PDF, Office, Media, Code, Archive)
     │                                │
     ├────────────────────────────────┘
     ▼
[Origin Provenance Detector] (Local Browser History SQLite & xattrs)
     │
     ▼
[FileContext Profile Initialized]
     │
     ▼
[Signal Extraction & Token Normalization] (Domain Affinities & Feature Vectors)
     │
     ▼
[Relationship Discovery & Clustering Engine] (Deterministic Sibling Graph Analysis)
     │
     ▼
[Multi-Signal Domain Classifier] (Scoring, Domain Taxonomy, Evidence Aggregator)
     │
     ▼
[Confidence Estimator] (CONFIRMED >= 0.85, PROBABLE >= 0.60, UNCERTAIN, UNKNOWN)
     │
     ▼
[Organization Planner] (User Rule Precedence, Canonical Path Containment)
     │
     ▼
[OrganizationProposal] ───► [Dry-Run Preview UI] OR [Safe 6-Stage Transfer Execution]
                                                                │
                                                                ▼
                                                   [SmartSort_Arrangement.md]
```

---

## 4. Module Structure

```text
src/core/file_intelligence/
├── __init__.py                # Module exports
├── context.py                 # FileContext, ExtractedMetadata, OriginInfo, Enums
├── metadata.py                # Filesystem stat and xattr inspection
├── mime.py                    # Deterministic MIME and extension heuristics
├── origin.py                  # Local browser SQLite and provenance engine
├── signals.py                 # Lexical tokenization, stemming, and signal vectors
├── relationships.py           # Deterministic multi-file clustering and similarity
├── classifier.py              # Domain taxonomy, evidence aggregator, scoring
├── planner.py                 # Hierarchical proposal generation and safety
├── cache.py                   # XDG persistent SQLite metadata cache
└── extractors/                # Pluggable extractors
    ├── __init__.py            # Extractor registry
    ├── base.py                # BaseExtractor interface
    ├── text.py                # Text, Markdown, CSV, Log
    ├── pdf.py                 # PDF metadata and text (pypdf/fallback)
    ├── docx.py                # Word documents (python-docx/XML)
    ├── pptx.py                # PowerPoint presentations (XML)
    ├── xlsx.py                # Excel spreadsheets (openpyxl/XML)
    ├── image.py               # Images & EXIF (Pillow/headers)
    ├── media.py               # Audio & Video (mutagen/atoms)
    ├── code.py                # Code tokens and symbols
    └── archive.py             # Archive table-of-contents (zip/tar)
```

---

## 5. Architectural Boundaries

1. **Qt & GUI Boundary**: `src/core/file_intelligence/` contains **ZERO Qt imports**. All GUI interactions, progress displays, and modals live exclusively in `src/gui/main_window.py`.
2. **Safety Boundary**: The intelligence engine outputs `OrganizationProposal` objects. Physical file movement is strictly executed by `FileUtils.safe_copy()` and `DirectoryOrganizer.execute()`.
3. **Network Boundary**: Zero external HTTP/API connections. All operations are 100% offline.
4. **Privacy Boundary**: EXIF GPS coordinates and URL authorization tokens are stripped immediately and never stored.

---

## 6. Phased Implementation Roadmap

The implementation is partitioned into **21 independent, sequential phases**:

```
PHASE 00: Architecture Audit & Extractor Environment Verification
   │
   ▼
PHASE 01: FileContext and FileProfile Data Model Foundation
   │
   ▼
PHASE 02: Filesystem & Extended Attribute Metadata Extractor
   │
   ▼
PHASE 03: Text, Markdown, and Plain Document Extractor
   │
   ▼
PHASE 04: PDF Content & Metadata Extractor
   │
   ▼
PHASE 05: Office Document Extractors (DOCX, PPTX, XLSX)
   │
   ▼
PHASE 06: Image (EXIF) & Media Metadata Extractor
   │
   ▼
PHASE 07: Source Code & Archive Inspection Extractor
   │
   ▼
PHASE 08: Local Browser Download History & Origin Resolution
   │
   ▼
PHASE 09: Normalized Signal Processing & Feature Extraction
   │
   ▼
PHASE 10: File Relationship Discovery & Cluster Analysis
   │
   ▼
PHASE 11: Multi-Signal Domain Classification & Confidence Scoring
   │
   ▼
PHASE 12: Intelligent Organization Planner & Hierarchy Generation
   │
   ▼
PHASE 13: Directory Organizer Integration & Batch Profiling
   │
   ▼
PHASE 14: Download Organizer Integration & Real-Time Profiling
   │
   ▼
PHASE 15: GUI Preview, Evidence Display, & Review Workflow
   │
   ▼
PHASE 16: Enhanced Arrangement Index Report & Searchable Audit
   │
   ▼
PHASE 17: XDG Caching Layer & Performance Optimization
   │
   ▼
PHASE 18: Full Integration Testing & Multi-Domain Verification
   │
   ▼
PHASE 19: Debian Packaging Updates & Dependency Integration
   │
   ▼
PHASE 20: Headless CI Validation & Release Certification
```

---

## 7. Definition of Done (DoD)

A phase is considered **Complete and Certified** only when:
1. All specified files for that phase are created/modified cleanly.
2. Unit and component tests for that phase pass 100% under `pytest`.
3. The existing SmartSort test suite (116 tests) continues to pass 100% with zero regressions.
4. Code compilation (`python3 -m compileall src main.py`) succeeds with code 0.
5. No memory leaks, dangling threads, or unmocked blocking calls are introduced.
6. Execution terminates cleanly in headless test runs (`QT_QPA_PLATFORM=offscreen`).
