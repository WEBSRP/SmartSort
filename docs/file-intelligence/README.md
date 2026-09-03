# SmartSort File Intelligence Engine

## Overview

The **File Intelligence Engine** evolves SmartSort from a file-extension and name-matching organizer into an **intelligent, offline, multi-signal file understanding and hierarchical organization system**.

Instead of relying solely on file extensions (e.g. routing every `.zip` to `Archives/` or every `.pdf` to `Documents/`), the File Intelligence Engine examines all available local evidence to understand:
1. **What is this file?** (Extracted metadata, text sample, author, title, origin, keywords)
2. **How does this file relate to other files?** (Shared clusters, courses, projects, topics, timestamps)
3. **Where should this file go?** (Contextual hierarchical path proposal with confidence and evidence)
4. **How do we safely move it?** (Strict 6-stage copy-verify-delete protocol)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SMARTSORT FILE INTELLIGENCE                       │
│                                                                             │
│   ┌──────────────┐      ┌─────────────────────────┐      ┌──────────────┐   │
│   │ Raw File On  │ ───► │ 1. Metadata & Extractor │ ───► │  FileContext │   │
│   │  Filesystem  │      │    Pipeline (Offline)   │      │  (Profile)   │   │
│   └──────────────┘      └─────────────────────────┘      └──────┬───────┘   │
│                                                                 │           │
│   ┌──────────────┐      ┌─────────────────────────┐             │           │
│   │ Local Origin │ ───► │ 2. Origin & Provenance  │ ────────────┤           │
│   │ (xattr/DB)   │      │    Detection Engine     │             │           │
│   └──────────────┘      └─────────────────────────┘             ▼           │
│                                                          ┌──────────────┐   │
│   ┌──────────────┐      ┌─────────────────────────┐      │ 3. Signal    │   │
│   │ Sibling & Dir│ ───► │ 4. Relationship & Cluster│ ◄───┤    Extract   │   │
│   │  Context     │      │    Discovery Engine     │      │   & Weights  │   │
│   └──────────────┘      └────────────┬────────────┘      └──────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│                         ┌─────────────────────────┐                         │
│                         │ 5. Multi-Signal Domain  │                         │
│                         │    Classifier Engine    │                         │
│                         └────────────┬────────────┘                         │
│                                      │                                      │
│                                      ▼                                      │
│                         ┌─────────────────────────┐                         │
│                         │ 6. Organization Planner │                         │
│                         │    & Hierarchy Proposer │                         │
│                         └────────────┬────────────┘                         │
│                                      │                                      │
│                     ┌────────────────┴────────────────┐                     │
│                     ▼                                 ▼                     │
│        ┌─────────────────────────┐       ┌─────────────────────────┐        │
│        │  Directory Organizer    │       │   Download Organizer    │        │
│        │  (Batch / Relationship) │       │   (Real-Time / Provenance)│      │
│        └────────────┬────────────┘       └────────────┬────────────┘        │
│                     │                                 │                     │
│                     └────────────────┬────────────────┘                     │
│                                      ▼                                      │
│                         ┌─────────────────────────┐                         │
│                         │ 7. Safe 6-Stage Transfer│                         │
│                         │    (Copy-Verify-Delete) │                         │
│                         └────────────┬────────────┘                         │
│                                      ▼                                      │
│                         ┌─────────────────────────┐                         │
│                         │ 8. Arrangement Index MD │                         │
│                         │    & Monospace Summary  │                         │
│                         └─────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Tenets

1. **100% Offline & Private**: Zero external network calls, zero cloud telemetry, zero remote LLMs. All analysis is performed locally on the machine.
2. **Domain Agnostic**: Works equally well for academic materials, software engineering projects, cybersecurity toolkits, financial documents, media collections, and general downloads.
3. **Evidence-Based Transparent Confidence**: Every classification produces an explicit confidence score and a human-readable list of evidence reasons.
4. **Decoupled Architecture**: Extraction, origin detection, classification, planning, and file movement are strictly isolated modules.
5. **Inviolable Data Safety**: File movement is never performed by the intelligence engine. Files are only moved by the existing, verified 6-stage copy-verify-delete protocol.
6. **Zero Qt in Core**: All intelligence logic is pure Python with zero GUI dependencies, ensuring headless CI safety and preventing application hangs.

---

## Documentation Index

- [Master Implementation Plan](IMPLEMENTATION_PLAN.md) — Comprehensive master plan for engineering implementation.
- [Claude Handoff Instructions](CLAUDE_HANDOFF.md) — Rules of engagement and execution guide for implementation agents.
- [System Architecture](architecture.md) — Architectural layers, module hierarchy, and data flow.
- [Data Model](data-model.md) — `FileContext`, `FileProfile`, `Signal`, `Relationship`, and `OrganizationProposal` schema.
- [Extractors Specification](extractors.md) — Pluggable format extractors (PDF, Office, Images, Audio/Video, Code, Archives).
- [Origin Detection](origin-detection.md) — Local browser database and extended attribute provenance resolver.
- [Signal Processing](signals.md) — Signal extraction, normalization, tokenization, and weighting.
- [Relationship Engine](relationships.md) — Deterministic file clustering, shared context discovery, and sibling analysis.
- [Classification & Scoring](classification.md) — Domain taxonomy, multi-signal scoring, and confidence calculation.
- [Organization Planner](organization-planner.md) — Dynamic hierarchy generation and fallback resolution.
- [Directory Organizer Integration](directory-integration.md) — Batch profiling, multi-file relationship discovery, and dry-run preview.
- [Download Organizer Integration](download-integration.md) — Real-time event profiling, single-file provenance, and daemon integration.
- [Performance & Caching](performance.md) — XDG caching, bounded memory extraction, and incremental analysis.
- [Security & Path Safety](security.md) — Archive bomb protection, path containment, and file sanitization.
- [Testing Strategy](testing.md) — Headless test fixtures, mock data, and regression test plan.
- [CI & Headless Constraints](ci-headless.md) — Headless process safety, Qt decoupling, and execution rules.
- [Dependencies Audit](dependencies.md) — Debian packaging compatibility, licensing, and fallback policies.
- [Phased Execution Roadmap](phases/) — 21 standalone, sequential implementation phase documents (`phase-00` to `phase-20`).
