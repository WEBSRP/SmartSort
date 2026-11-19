"""FileContext and supporting data model for the File Intelligence Engine.

This module defines the core data structures used across all intelligence,
extraction, clustering, and planning layers. Every class is a pure Python
dataclass or enum with zero Qt dependencies, ensuring headless CI safety.

Serialization helpers (to_dict / from_dict) produce and consume plain
dictionaries suitable for JSON round-tripping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConfidenceLevel(Enum):
    """Confidence level for classification and origin detection results."""

    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    UNCERTAIN = "UNCERTAIN"
    UNKNOWN = "UNKNOWN"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class OriginSource(Enum):
    """Source of origin / provenance information for a file."""

    BROWSER_SQLITE = "BROWSER_SQLITE"
    EXTENDED_ATTRIBUTE = "EXTENDED_ATTRIBUTE"
    METADATA_HEADER = "METADATA_HEADER"
    PARENT_DIRECTORY = "PARENT_DIRECTORY"
    UNKNOWN = "UNKNOWN"


class SignalType(Enum):
    """Type of signal extracted from a file for classification evidence."""

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
    EXTENSION_HINT = "EXTENSION_HINT"


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceItem:
    """A single piece of evidence supporting a classification decision.

    Immutable (frozen) to ensure evidence integrity once recorded.
    """

    signal_type: SignalType
    description: str
    weight: float
    source_field: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "signal_type": self.signal_type.value,
            "description": self.description,
            "weight": self.weight,
            "source_field": self.source_field,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvidenceItem:
        """Reconstruct an EvidenceItem from a dictionary."""
        return cls(
            signal_type=SignalType(data["signal_type"]),
            description=data["description"],
            weight=data["weight"],
            source_field=data["source_field"],
        )


# ---------------------------------------------------------------------------
# Origin
# ---------------------------------------------------------------------------

@dataclass
class OriginInfo:
    """Origin / provenance information for a file.

    All fields default to safe empty values. Populated by later phases.
    """

    url: str = ""
    domain: str = ""
    site_name: str = ""
    source: OriginSource = OriginSource.UNKNOWN
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    evidence_detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "url": self.url,
            "domain": self.domain,
            "site_name": self.site_name,
            "source": self.source.value,
            "confidence": self.confidence.value,
            "evidence_detail": self.evidence_detail,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OriginInfo:
        """Reconstruct an OriginInfo from a dictionary."""
        return cls(
            url=data.get("url", ""),
            domain=data.get("domain", ""),
            site_name=data.get("site_name", ""),
            source=OriginSource(data.get("source", "UNKNOWN")),
            confidence=ConfidenceLevel(data.get("confidence", "UNKNOWN")),
            evidence_detail=data.get("evidence_detail", ""),
        )


# ---------------------------------------------------------------------------
# Extracted Metadata
# ---------------------------------------------------------------------------

@dataclass
class ExtractedMetadata:
    """Metadata extracted from a file by format-specific extractors.

    All fields default to safe empty / None values. Populated by later phases.
    """

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

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "title": self.title,
            "author": self.author,
            "subject": self.subject,
            "created_date": self.created_date,
            "modified_date": self.modified_date,
            "keywords": list(self.keywords),
            "headings": list(self.headings),
            "text_preview": self.text_preview,
            "toc_entries": list(self.toc_entries),
            "dimensions": list(self.dimensions) if self.dimensions is not None else None,
            "duration_seconds": self.duration_seconds,
            "exif_tags": dict(self.exif_tags),
            "code_language": self.code_language,
            "code_symbols": list(self.code_symbols),
            "extractor_name": self.extractor_name,
            "extraction_status": self.extraction_status,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractedMetadata:
        """Reconstruct an ExtractedMetadata from a dictionary."""
        dims = data.get("dimensions")
        if dims is not None:
            dims = tuple(dims)
        return cls(
            title=data.get("title"),
            author=data.get("author"),
            subject=data.get("subject"),
            created_date=data.get("created_date"),
            modified_date=data.get("modified_date"),
            keywords=list(data.get("keywords", [])),
            headings=list(data.get("headings", [])),
            text_preview=data.get("text_preview", ""),
            toc_entries=list(data.get("toc_entries", [])),
            dimensions=dims,
            duration_seconds=data.get("duration_seconds"),
            exif_tags=dict(data.get("exif_tags", {})),
            code_language=data.get("code_language"),
            code_symbols=list(data.get("code_symbols", [])),
            extractor_name=data.get("extractor_name", "none"),
            extraction_status=data.get("extraction_status", "PENDING"),
            error_message=data.get("error_message", ""),
        )


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Signal:
    """A normalized token with its evidence channel, base weight and field."""

    token: str
    signal_type: SignalType
    weight: float
    source: str

    def __post_init__(self):
        if not isinstance(self.token, str) or not self.token.strip():
            raise ValueError("Signal token must be a non-empty string")
        if not isinstance(self.signal_type, SignalType):
            raise ValueError("Signal type must be a SignalType")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("Signal source must be a non-empty field name")
        if (isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)) or
                not 0 <= self.weight <= 1):
            raise ValueError("Signal weight must be finite and in [0, 1]")

    def to_dict(self) -> Dict[str, Any]:
        return {"token": self.token, "signal_type": self.signal_type.value,
                "weight": self.weight, "source": self.source}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Signal:
        return cls(data["token"], SignalType(data["signal_type"]), data["weight"], data["source"])


@dataclass
class SignalSet:
    """Weighted features and relative domain affinities, not a classification."""

    tokens: Set[str] = field(default_factory=set)
    weighted_signals: List[Signal] = field(default_factory=list)
    domain_affinities: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.tokens, set) or any(not isinstance(t, str) or not t.strip() for t in self.tokens):
            raise ValueError("Signal tokens must be a set of non-empty strings")
        if not isinstance(self.weighted_signals, list) or any(not isinstance(s, Signal) for s in self.weighted_signals):
            raise ValueError("Weighted signals must be a list of Signal objects")
        if not isinstance(self.domain_affinities, dict) or any(
                not isinstance(domain, str) or not domain.strip() or isinstance(score, bool) or
                not isinstance(score, (int, float)) or not 0 <= score <= 1
                for domain, score in self.domain_affinities.items()):
            raise ValueError("Domain affinities must be finite values in [0, 1]")

    def to_dict(self) -> Dict[str, Any]:
        return {"tokens": sorted(self.tokens),
                "weighted_signals": [signal.to_dict() for signal in self.weighted_signals],
                "domain_affinities": dict(sorted(self.domain_affinities.items()))}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SignalSet:
        tokens = data.get("tokens", [])
        if not isinstance(tokens, (list, tuple, set)) or not all(isinstance(t, str) for t in tokens):
            raise ValueError("Signal tokens must be a collection of strings")
        affinities = dict(data.get("domain_affinities", {}))
        if any(not isinstance(domain, str) or isinstance(score, bool) or
               not isinstance(score, (int, float)) or not 0 <= score <= 1
               for domain, score in affinities.items()):
            raise ValueError("Domain affinities must be finite values in [0, 1]")
        return cls(set(tokens), [Signal.from_dict(item) for item in data.get("weighted_signals", [])], affinities)


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

@dataclass
class FileRelationship:
    """A qualifying, inspectable edge between two logical file paths."""

    source_path: str
    target_path: str
    relationship_type: str
    similarity_score: float
    shared_tokens: Set[str] = field(default_factory=set)

    def __post_init__(self):
        if isinstance(self.similarity_score, bool) or not isinstance(self.similarity_score, (int, float)) or not 0 <= self.similarity_score <= 1:
            raise ValueError("Relationship similarity must be finite and in [0, 1]")

    def to_dict(self) -> Dict[str, Any]:
        return {"source_path": self.source_path, "target_path": self.target_path,
                "relationship_type": self.relationship_type, "similarity_score": self.similarity_score,
                "shared_tokens": sorted(self.shared_tokens)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FileRelationship:
        return cls(data["source_path"], data["target_path"], data["relationship_type"],
                   data["similarity_score"], set(data.get("shared_tokens", [])))


@dataclass
class FileCluster:
    """A connected group and a bounded spanning witness of its relationships."""

    cluster_id: str
    cluster_name: str
    file_paths: List[str] = field(default_factory=list)
    shared_keywords: Set[str] = field(default_factory=set)
    inferred_domain: str = "Others"
    inferred_hierarchy: List[str] = field(default_factory=list)
    cluster_confidence: float = 0.0
    relationships: List[FileRelationship] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.cluster_confidence, bool) or not isinstance(self.cluster_confidence, (int, float)) or not 0 <= self.cluster_confidence <= 1:
            raise ValueError("Cluster confidence must be finite and in [0, 1]")

    def to_dict(self) -> Dict[str, Any]:
        return {"cluster_id": self.cluster_id, "cluster_name": self.cluster_name,
                "file_paths": list(self.file_paths), "shared_keywords": sorted(self.shared_keywords),
                "inferred_domain": self.inferred_domain, "inferred_hierarchy": list(self.inferred_hierarchy),
                "cluster_confidence": self.cluster_confidence,
                "relationships": [edge.to_dict() for edge in self.relationships]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FileCluster:
        return cls(data["cluster_id"], data["cluster_name"], list(data.get("file_paths", [])),
                   set(data.get("shared_keywords", [])), data.get("inferred_domain", "Others"),
                   list(data.get("inferred_hierarchy", [])), data.get("cluster_confidence", 0.0),
                   [FileRelationship.from_dict(item) for item in data.get("relationships", [])])


# ---------------------------------------------------------------------------
# FileContext
# ---------------------------------------------------------------------------

@dataclass
class OrganizationProposal:
    """Planning result only; creation neither reserves nor transfers a file."""

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

    def __post_init__(self):
        if (isinstance(self.confidence_score, bool) or
                not isinstance(self.confidence_score, (int, float)) or
                not 0 <= self.confidence_score <= 1):
            raise ValueError("Proposal confidence must be finite and in [0, 1]")
        if not isinstance(self.confidence_level, ConfidenceLevel):
            raise ValueError("Proposal confidence level must be a ConfidenceLevel")
        if not isinstance(self.evidence, list) or any(not isinstance(e, EvidenceItem) for e in self.evidence):
            raise ValueError("Proposal evidence must be a list of EvidenceItems")
        if any(not isinstance(e.signal_type, SignalType) or not isinstance(e.description, str) or
               not isinstance(e.source_field, str) or isinstance(e.weight, bool) or
               not isinstance(e.weight, (int, float)) or not 0 <= e.weight <= 1 for e in self.evidence):
            raise ValueError("Proposal evidence must have typed fields and finite unit weights")
        if not isinstance(self.hierarchy_segments, list) or any(not isinstance(p, str) for p in self.hierarchy_segments):
            raise ValueError("Proposal hierarchy must be a list of strings")
        if any(not isinstance(value, str) for value in (self.source_path, self.target_path,
                   self.relative_target, self.domain, self.rule_name)) or not isinstance(self.is_rule_override, bool):
            raise ValueError("Proposal paths and labels must be strings, with a boolean override flag")

    def to_dict(self) -> Dict[str, Any]:
        return {"source_path": self.source_path, "target_path": self.target_path,
                "relative_target": self.relative_target, "domain": self.domain,
                "hierarchy_segments": list(self.hierarchy_segments),
                "confidence_level": self.confidence_level.value,
                "confidence_score": self.confidence_score,
                "evidence": [item.to_dict() for item in self.evidence],
                "is_rule_override": self.is_rule_override, "rule_name": self.rule_name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OrganizationProposal:
        return cls(data["source_path"], data["target_path"], data["relative_target"],
                   data["domain"], list(data["hierarchy_segments"]),
                   ConfidenceLevel(data["confidence_level"]), data["confidence_score"],
                   [EvidenceItem.from_dict(item) for item in data.get("evidence", [])],
                   data.get("is_rule_override", False), data.get("rule_name", ""))

@dataclass
class FileContext:
    """Universal file context profile for the intelligence pipeline.

    Serves as the common contract across all intelligence, extraction,
    clustering, and planning layers. Required fields capture file identity
    and filesystem attributes; optional fields are populated incrementally
    by later pipeline stages.
    """

    # Identity
    path: str
    filename: str
    stem: str
    extension: str

    # Type
    mime_type: str

    # Filesystem
    size_bytes: int
    created_timestamp: float
    modified_timestamp: float
    inode: int
    device: int

    # Optional identity
    sha256_hash: Optional[str] = None

    # Nested structures — populated by later phases
    metadata: ExtractedMetadata = field(default_factory=ExtractedMetadata)
    origin: OriginInfo = field(default_factory=OriginInfo)

    # Signals — populated in Phase 09
    signals: Optional[SignalSet] = None

    # Relationships — populated in Phase 10
    cluster_id: Optional[str] = None
    related_file_paths: List[str] = field(default_factory=list)

    # Classification — populated in Phase 11
    classification_domain: str = "Others"
    subcategories: List[str] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    confidence_score: float = 0.0
    evidence_list: List[EvidenceItem] = field(default_factory=list)

    # Organization — populated in Phase 12
    proposed_destination: str = ""

    # Reversible bookkeeping prevents repeated cluster runs compounding scores.
    relationship_base_confidence: Optional[float] = None
    relationship_confidence_boost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary suitable for JSON storage."""
        return {
            "path": self.path,
            "filename": self.filename,
            "stem": self.stem,
            "extension": self.extension,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "created_timestamp": self.created_timestamp,
            "modified_timestamp": self.modified_timestamp,
            "inode": self.inode,
            "device": self.device,
            "sha256_hash": self.sha256_hash,
            "metadata": self.metadata.to_dict(),
            "origin": self.origin.to_dict(),
            "signals": self.signals.to_dict() if isinstance(self.signals, SignalSet) else self.signals,
            "cluster_id": self.cluster_id,
            "related_file_paths": list(self.related_file_paths),
            "classification_domain": self.classification_domain,
            "subcategories": list(self.subcategories),
            "confidence": self.confidence.value,
            "confidence_score": self.confidence_score,
            "evidence_list": [e.to_dict() for e in self.evidence_list],
            "proposed_destination": self.proposed_destination,
            "relationship_base_confidence": self.relationship_base_confidence,
            "relationship_confidence_boost": self.relationship_confidence_boost,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FileContext:
        """Reconstruct a FileContext from a dictionary."""
        metadata_data = data.get("metadata")
        metadata = (
            ExtractedMetadata.from_dict(metadata_data)
            if metadata_data
            else ExtractedMetadata()
        )

        origin_data = data.get("origin")
        origin = (
            OriginInfo.from_dict(origin_data)
            if origin_data
            else OriginInfo()
        )

        evidence_data = data.get("evidence_list", [])
        evidence_list = [EvidenceItem.from_dict(e) for e in evidence_data]

        signals = data.get("signals")
        if isinstance(signals, dict) and {"tokens", "weighted_signals", "domain_affinities"}.intersection(signals):
            signals = SignalSet.from_dict(signals)

        return cls(
            path=data["path"],
            filename=data["filename"],
            stem=data["stem"],
            extension=data["extension"],
            mime_type=data["mime_type"],
            size_bytes=data["size_bytes"],
            created_timestamp=data["created_timestamp"],
            modified_timestamp=data["modified_timestamp"],
            inode=data["inode"],
            device=data["device"],
            sha256_hash=data.get("sha256_hash"),
            metadata=metadata,
            origin=origin,
            signals=signals,
            cluster_id=data.get("cluster_id"),
            related_file_paths=list(data.get("related_file_paths", [])),
            classification_domain=data.get("classification_domain", "Others"),
            subcategories=list(data.get("subcategories", [])),
            confidence=ConfidenceLevel(data.get("confidence", "UNKNOWN")),
            confidence_score=data.get("confidence_score", 0.0),
            evidence_list=evidence_list,
            proposed_destination=data.get("proposed_destination", ""),
            relationship_base_confidence=data.get("relationship_base_confidence"),
            relationship_confidence_boost=data.get("relationship_confidence_boost", 0.0),
        )
