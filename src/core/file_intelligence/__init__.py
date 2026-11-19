"""File Intelligence Engine for SmartSort.

Provides multi-signal contextual file profiling, classification,
and organization planning. All modules in this package are pure Python
with zero Qt dependencies.
"""

from src.core.file_intelligence.context import (
    ConfidenceLevel,
    OriginSource,
    SignalType,
    Signal,
    SignalSet,
    FileRelationship,
    FileCluster,
    OrganizationProposal,
    EvidenceItem,
    OriginInfo,
    ExtractedMetadata,
    FileContext,
)
from src.core.file_intelligence.metadata import FileContextBuilder, FileMetadataExtractor
from src.core.file_intelligence.mime import DeterministicMime
from src.core.file_intelligence.origin import OriginDetector
from src.core.file_intelligence.signals import LexicalTokenizer, SignalExtractor
from src.core.file_intelligence.relationships import RelationshipEngine
from src.core.file_intelligence.classifier import MultiSignalClassifier
from src.core.file_intelligence.planner import OrganizationPlanner
from src.core.file_intelligence.cache import MetadataCache

__all__ = [
    "ConfidenceLevel",
    "OriginSource",
    "SignalType",
    "Signal",
    "SignalSet",
    "FileRelationship",
    "FileCluster",
    "OrganizationProposal",
    "EvidenceItem",
    "OriginInfo",
    "ExtractedMetadata",
    "FileContext",
    "FileContextBuilder",
    "FileMetadataExtractor",
    "DeterministicMime",
    "OriginDetector",
    "LexicalTokenizer",
    "SignalExtractor",
    "RelationshipEngine",
    "MultiSignalClassifier",
    "OrganizationPlanner",
    "MetadataCache",
]
