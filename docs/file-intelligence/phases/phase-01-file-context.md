# Phase 01: FileContext and FileProfile Data Model Foundation

## Objective
Implement the comprehensive, immutable `FileContext` / `FileProfile` data model along with supporting enums, evidence structures, and proposal dataclasses in `src/core/file_intelligence/context.py`.

## Why This Phase Exists
`FileContext` serves as the universal contract across all intelligence, extraction, clustering, and planning layers. Establishing this typed foundation first ensures zero data model drift across subsequent extractor and classifier phases.

## Inputs
- File path strings and raw filesystem stat attributes.

## Outputs
- `src/core/file_intelligence/context.py` containing complete, typed dataclasses and enums.
- Unit tests validating instantiations, immutability, serialization, and default states.

## Files To Create
- `src/core/file_intelligence/context.py`
- `tests/test_file_intelligence/test_context.py`

## Files To Modify
- `src/core/file_intelligence/__init__.py`: Export key context classes and enums.

## Existing Components To Reuse
- None (pure dataclass implementation).

## APIs / Interfaces
```python
# src/core/file_intelligence/context.py
class ConfidenceLevel(Enum):
    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    UNCERTAIN = "UNCERTAIN"
    UNKNOWN = "UNKNOWN"
    NOT_AVAILABLE = "NOT_AVAILABLE"

class OriginSource(Enum):
    BROWSER_SQLITE = "BROWSER_SQLITE"
    EXTENDED_ATTRIBUTE = "EXTENDED_ATTRIBUTE"
    METADATA_HEADER = "METADATA_HEADER"
    PARENT_DIRECTORY = "PARENT_DIRECTORY"
    UNKNOWN = "UNKNOWN"

class SignalType(Enum):
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

@dataclass(frozen=True)
class EvidenceItem:
    signal_type: SignalType
    description: str
    weight: float
    source_field: str

@dataclass
class OriginInfo:
    url: str = ""
    domain: str = ""
    site_name: str = ""
    source: OriginSource = OriginSource.UNKNOWN
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    evidence_detail: str = ""

@dataclass
class ExtractedMetadata:
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    created_date: Optional[str] = None
    modified_date: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    headings: List[str] = field(default_factory=list)
    text_preview: str = ""
    toc_entries: List[str] = field(default_factory=list)
    dimensions: Optional[Tuple[int, int]] = None
    duration_seconds: Optional[float] = None
    exif_tags: Dict[str, str] = field(default_factory=dict)
    code_language: Optional[str] = None
    code_symbols: List[str] = field(default_factory=list)
    extractor_name: str = "none"
    extraction_status: str = "PENDING"
    error_message: str = ""

@dataclass
class FileContext:
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
    metadata: ExtractedMetadata = field(default_factory=ExtractedMetadata)
    origin: OriginInfo = field(default_factory=OriginInfo)
    signals: Any = None # Populated in Phase 09
    cluster_id: Optional[str] = None
    related_file_paths: List[str] = field(default_factory=list)
    classification_domain: str = "Others"
    subcategories: List[str] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    confidence_score: float = 0.0
    evidence_list: List[EvidenceItem] = field(default_factory=list)
    proposed_destination: str = ""
```

## Data Structures
- All structures detailed above.

## Algorithms
- `to_dict()` and `from_dict()` serialization helpers.

## Error Handling
- Default values prevent `NoneType` attribute errors during downstream pipeline processing.

## Security Considerations
- Ensure string fields are sanitized and do not store raw binary payloads.

## Performance Considerations
- Lightweight memory overhead (< 4 KB per `FileContext` instance).

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_context.py`:
  - Test default field values across all dataclasses.
  - Test enum equality and membership.
  - Test `EvidenceItem` immutability (`frozen=True`).
  - Test `FileContext` serialization and round-trip consistency.

## Acceptance Criteria
- [ ] All dataclasses defined with precise type annotations.
- [ ] 100% test pass on `test_context.py`.
- [ ] Zero regressions on existing test suite.

## Dependencies
- Standard library `dataclasses`, `enum`, `typing`.

## What This Phase MUST NOT Change
- Must NOT alter existing SmartSort runtime classes.

## Completion Checklist
- [ ] `src/core/file_intelligence/context.py` created.
- [ ] Tests written and passing.
