# SmartSort File Intelligence Engine: Data Model

## 1. Overview

The Data Model provides the single source of truth across all intelligence, extraction, clustering, and planning layers. All data structures are defined using standard Python `dataclasses` and `Enum`s to guarantee type safety, immutability, zero external serialization baggage, and zero Qt dependencies.

---

## 2. Core Enums

```python
from enum import Enum, auto

class ConfidenceLevel(Enum):
    """Represents explicit epistemic confidence based on verifiable local evidence."""
    CONFIRMED = "CONFIRMED"        # >= 0.85: Direct, unambiguous multi-signal corroboration
    PROBABLE = "PROBABLE"          # >= 0.60: Strong evidence from content, origin, or clustering
    UNCERTAIN = "UNCERTAIN"        # >= 0.35: Weak or single-signal heuristic match
    UNKNOWN = "UNKNOWN"            # < 0.35:  No meaningful evidence discovered
    NOT_AVAILABLE = "NOT_AVAILABLE"# Format or extractor unsupported/disabled

class OriginSource(Enum):
    """Source from which origin provenance was recovered."""
    BROWSER_SQLITE = "BROWSER_SQLITE"            # Direct match in local browser download history DB
    EXTENDED_ATTRIBUTE = "EXTENDED_ATTRIBUTE"    # File xattr (`user.xdg.origin.url` / `referrer`)
    METADATA_HEADER = "METADATA_HEADER"          # Internal document metadata (e.g. PDF/DOCX URL)
    PARENT_DIRECTORY = "PARENT_DIRECTORY"        # Inherited from parent folder hierarchy
    UNKNOWN = "UNKNOWN"                          # No origin provenance recovered

class SignalType(Enum):
    """Categorization of individual evidence signals."""
    FILENAME_TOKEN = "FILENAME_TOKEN"
    DOCUMENT_TITLE = "DOCUMENT_TITLE"
    DOCUMENT_HEADING = "DOCUMENT_HEADING"
    CONTENT_KEYWORD = "CONTENT_KEYWORD"
    ORIGIN_DOMAIN = "ORIGIN_DOMAIN"
    ARCHIVE_CONTENT = "ARCHIVE_CONTENT"
    CODE_SYNTAX = "CODE_SYNTAX"
    MEDIA_METADATA = "MEDIA_METADATA"
    EXIF_CAMERA = "EXIF_CAMERA"
    DIRECTORY_CONTEXT = "DIRECTORY_CONTEXT"
    CLUSTER_CONTEXT = "CLUSTER_CONTEXT"
```

---

## 3. Data Structures

### 3.1 `EvidenceItem`
```python
@dataclass(frozen=True)
class EvidenceItem:
    """Individual piece of verifiable evidence used to justify a classification."""
    signal_type: SignalType
    description: str             # Human-readable explanation (e.g. 'Document title mentions DBMS')
    weight: float               # Relative weight in confidence score [0.0 - 1.0]
    source_field: str           # Source field in FileContext where evidence was found
```

### 3.2 `OriginInfo`
```python
@dataclass
class OriginInfo:
    """Local origin and provenance evidence for a file."""
    url: str = ""
    domain: str = ""
    site_name: str = ""
    source: OriginSource = OriginSource.UNKNOWN
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    evidence_detail: str = ""
```

### 3.3 `ExtractedMetadata`
```python
@dataclass
class ExtractedMetadata:
    """Standardized metadata extracted across all supported file formats."""
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    created_date: Optional[str] = None
    modified_date: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    headings: List[str] = field(default_factory=list)
    text_preview: str = ""                       # Bounded text snippet (max 1024 chars)
    toc_entries: List[str] = field(default_factory=list)  # Table of contents or archive file list
    dimensions: Optional[Tuple[int, int]] = None # Width x Height for visual media
    duration_seconds: Optional[float] = None     # Length in seconds for audio/video
    exif_tags: Dict[str, str] = field(default_factory=dict)
    code_language: Optional[str] = None          # Detected programming language
    code_symbols: List[str] = field(default_factory=list) # Classes, functions, imports
    extractor_name: str = "none"
    extraction_status: str = "PENDING"           # SUCCESS, PARTIAL, SKIPPED, FAILED
    error_message: str = ""
```

### 3.4 `Signal` & `SignalSet`
```python
@dataclass(frozen=True)
class Signal:
    """A weighted token or semantic feature extracted from a file."""
    token: str
    signal_type: SignalType
    weight: float                                # [0.0 - 1.0]
    source: str

@dataclass
class SignalSet:
    """Collection of normalized signals extracted from a file."""
    tokens: Set[str] = field(default_factory=set)
    weighted_signals: List[Signal] = field(default_factory=list)
    domain_affinities: Dict[str, float] = field(default_factory=dict) # e.g. {'College': 0.85, 'Cybersecurity': 0.1}
```

### 3.5 `FileContext` / `FileProfile`
The central immutable representation for every analyzed file.

```python
@dataclass
class FileContext:
    """Comprehensive contextual profile of a single file."""
    # Basic Filesystem Attributes
    path: str
    filename: str
    stem: str
    extension: str
    mime_type: str
    size_bytes: int
    created_timestamp: float
    modified_timestamp: float
    inode: int
    device: int
    sha256_hash: Optional[str] = None

    # Extraction & Provenance
    metadata: ExtractedMetadata = field(default_factory=ExtractedMetadata)
    origin: OriginInfo = field(default_factory=OriginInfo)
    signals: SignalSet = field(default_factory=SignalSet)

    # Cluster & Relationship References
    cluster_id: Optional[str] = None
    related_file_paths: List[str] = field(default_factory=list)

    # Intelligence & Planning Output
    classification_domain: str = "Others"
    subcategories: List[str] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    confidence_score: float = 0.0                # [0.0 - 1.0]
    evidence_list: List[EvidenceItem] = field(default_factory=list)
    proposed_destination: str = ""
```

### 3.6 `FileRelationship` & `FileCluster`
```python
@dataclass
class FileRelationship:
    """Verifiable connection between two files."""
    source_path: str
    target_path: str
    relationship_type: str                       # SIBLING_SERIES, ARCHIVE_EXTRACT, PROJECT_COMPONENT, SHARED_ORIGIN
    similarity_score: float                      # [0.0 - 1.0]
    shared_tokens: Set[str] = field(default_factory=set)

@dataclass
class FileCluster:
    """Group of files sharing context (e.g. a course, project, or event)."""
    cluster_id: str
    cluster_name: str                            # e.g. 'DBMS_Course', 'Security_Auditor_Project'
    file_paths: List[str] = field(default_factory=list)
    shared_keywords: Set[str] = field(default_factory=set)
    inferred_domain: str = "Others"
    inferred_hierarchy: List[str] = field(default_factory=list) # e.g. ['College', 'DBMS']
    cluster_confidence: float = 0.0
```

### 3.7 `OrganizationProposal`
```python
@dataclass
class OrganizationProposal:
    """The concrete proposal output by the Organization Planner."""
    source_path: str
    target_path: str
    relative_target: str
    domain: str
    hierarchy_segments: List[str]
    confidence_level: ConfidenceLevel
    confidence_score: float
    evidence: List[EvidenceItem]
    is_rule_override: bool = False
    rule_name: str = ""
```

---

## 4. State Transitions

```
[Raw Path]
    │
    ▼ (Ingest & Stat)
[FileContext Initialized] (Filesystem attributes populated, hash deferred/optional)
    │
    ▼ (Format Extractor & Origin Detector)
[FileContext Profiled] (Metadata, Text Preview, Headings, Origin URL recovered)
    │
    ▼ (Signal Extractor)
[FileContext Signaled] (SignalSet populated with weighted tokens and domain affinities)
    │
    ▼ (Relationship Engine — in batch or sibling context)
[FileContext Clustered] (Cluster ID assigned, related files mapped)
    │
    ▼ (Classifier & Planner)
[OrganizationProposal Generated] (Destination path, confidence score, evidence list)
```
