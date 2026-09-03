# SmartSort File Intelligence Engine: Classification & Confidence

## 1. Overview & Objectives

The Multi-Signal Classification Engine determines:
1. **Primary Domain**: What broad domain does this file belong to? (`College`, `Projects`, `Cybersecurity`, `Work`, `Media`, `Archives`, `Others`)
2. **Subcategory Hierarchy**: What subfolders describe its specific topic? (e.g. `DBMS/Lectures`, `SmartSort/Documentation`)
3. **Epistemic Confidence**: How certain is the classification based on verifiable evidence? (`CONFIRMED`, `PROBABLE`, `UNCERTAIN`, `UNKNOWN`)
4. **Evidence Justification**: An explicit, human-readable list of reasons explaining *why* the destination was chosen.

---

## 2. General-Purpose Domain Taxonomy

The taxonomy is extensible and domain-agnostic:

```
├── College/
│   └── {Course_Name}/          (e.g. DBMS, OS, Machine_Learning, CS101)
│       ├── Lectures/           (Slides, lecture notes, textbook chapters)
│       ├── Assignments/        (Homework, problem sets, solutions)
│       ├── Labs/               (Lab manuals, code submissions, data)
│       └── Exams/              (Midterms, finals, quizzes, study guides)
│
├── Projects/
│   └── {Project_Name}/         (e.g. SmartSort, LinuxKernel, PortfolioApp)
│       ├── Source/             (Code archives, repositories, scripts)
│       ├── Documentation/      (Architecture docs, specs, guides)
│       ├── Design/             (Figma exports, mockups, UI assets)
│       └── Releases/           (Compiled binaries, deb packages, releases)
│
├── Cybersecurity/
│   ├── Tools/                  (Security tools, custom scripts)
│   ├── Reports/                (Audit reports, vulnerability scans)
│   ├── Captures/               (PCAP files, network logs)
│   ├── Wordlists/              (Dictionaries, password lists)
│   └── Exploits/               (PoC code, CVE advisories)
│
├── Work/
│   ├── Invoices/               (Billing, client invoices)
│   ├── Contracts/              (Agreements, NDAs, legal documents)
│   ├── Receipts/               (Expense receipts, payment confirmations)
│   └── Reports/                (Quarterly reviews, status decks)
│
├── Media/
│   ├── Images/                 (Photos, graphics, wallpapers)
│   ├── Videos/                 (Screen recordings, movies, clips)
│   └── Audio/                  (Podcasts, music tracks, voice notes)
│
├── Archives/                   (Generic compressed backups, system snapshots)
└── Others/                     (Unclassified fallback files)
```

---

## 3. Classification Scoring Algorithm

The classifier evaluates evidence across multiple independent channels:

$$\text{TotalScore}(D) = \sum_{k} W_k \cdot S_k(D)$$

Where the scoring channels $S_k$ and weights $W_k$ are:

| Channel $k$ | Weight $W_k$ | Evidence Evaluated |
|---|---|---|
| **Document Title** | $0.25$ | High-precision title matches in PDF/DOCX metadata |
| **Origin Domain** | $0.20$ | Known LMS domain, repository host, or security portal |
| **Content Text** | $0.20$ | Domain keyword density in extracted text snippet |
| **Filename Tokens** | $0.15$ | Sanitized tokens matching domain keywords |
| **Cluster Bonus** | $0.15$ | Sibling file consensus from Relationship Engine |
| **Archive Content** | $0.05$ | Internal file types found within archives |

---

## 4. Transparent Confidence System

Confidence is not an arbitrary black-box percentage. It maps directly to verifiable corroborating signals:

```python
def compute_confidence(scores: Dict[str, float], evidence: List[EvidenceItem]) -> Tuple[ConfidenceLevel, float]:
    """
    Computes normalized confidence score and assigns explicit ConfidenceLevel enum.
    """
    if not scores:
        return ConfidenceLevel.UNKNOWN, 0.0

    best_domain, top_score = max(scores.items(), key=lambda x: x[1])
    
    # Count independent corroborating evidence channels
    signal_types = {item.signal_type for item in evidence}
    corroboration_count = len(signal_types)

    # Multi-signal corroboration boost
    if corroboration_count >= 3:
        adjusted_score = min(1.0, top_score * 1.15)
    elif corroboration_count == 1:
        adjusted_score = min(0.60, top_score * 0.85) # Cap single-signal confidence
    else:
        adjusted_score = top_score

    # Assign Epistemic Level
    if adjusted_score >= 0.85 and corroboration_count >= 2:
        level = ConfidenceLevel.CONFIRMED
    elif adjusted_score >= 0.60:
        level = ConfidenceLevel.PROBABLE
    elif adjusted_score >= 0.35:
        level = ConfidenceLevel.UNCERTAIN
    else:
        level = ConfidenceLevel.UNKNOWN

    return level, round(adjusted_score, 2)
```

---

## 5. Evidence Item Formulation

Every proposal generates a structured list of human-readable `EvidenceItem` records:

```python
# Example generated for Lecture_3_DBMS.zip:
evidence = [
    EvidenceItem(
        signal_type=SignalType.ORIGIN_DOMAIN,
        description="Downloaded from University Canvas LMS (canvas.stanford.edu)",
        weight=0.85,
        source_field="origin.domain"
    ),
    EvidenceItem(
        signal_type=SignalType.ARCHIVE_CONTENT,
        description="Archive contains PowerPoint presentation (.pptx) and PDF slides",
        weight=0.70,
        source_field="metadata.toc_entries"
    ),
    EvidenceItem(
        signal_type=SignalType.FILENAME_TOKEN,
        description="Filename contains course keywords 'DBMS' and 'Lecture'",
        weight=0.65,
        source_field="filename"
    ),
    EvidenceItem(
        signal_type=SignalType.CLUSTER_CONTEXT,
        description="Grouped with sibling files: Lecture_1_DBMS.pdf, Lecture_2_DBMS.pptx",
        weight=0.60,
        source_field="cluster_id"
    )
]
```
