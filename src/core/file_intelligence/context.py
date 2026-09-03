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
from typing import Any, Dict, List, Optional, Tuple


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
# FileContext
# ---------------------------------------------------------------------------

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
    signals: Any = None

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
            "signals": self.signals,
            "cluster_id": self.cluster_id,
            "related_file_paths": list(self.related_file_paths),
            "classification_domain": self.classification_domain,
            "subcategories": list(self.subcategories),
            "confidence": self.confidence.value,
            "confidence_score": self.confidence_score,
            "evidence_list": [e.to_dict() for e in self.evidence_list],
            "proposed_destination": self.proposed_destination,
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
            signals=data.get("signals"),
            cluster_id=data.get("cluster_id"),
            related_file_paths=list(data.get("related_file_paths", [])),
            classification_domain=data.get("classification_domain", "Others"),
            subcategories=list(data.get("subcategories", [])),
            confidence=ConfidenceLevel(data.get("confidence", "UNKNOWN")),
            confidence_score=data.get("confidence_score", 0.0),
            evidence_list=evidence_list,
            proposed_destination=data.get("proposed_destination", ""),
        )
