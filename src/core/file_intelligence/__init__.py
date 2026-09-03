"""File Intelligence Engine for SmartSort.

Provides multi-signal contextual file profiling, classification,
and organization planning. All modules in this package are pure Python
with zero Qt dependencies.
"""

from src.core.file_intelligence.context import (
    ConfidenceLevel,
    OriginSource,
    SignalType,
    EvidenceItem,
    OriginInfo,
    ExtractedMetadata,
    FileContext,
)
from src.core.file_intelligence.metadata import FileContextBuilder
from src.core.file_intelligence.mime import DeterministicMime

__all__ = [
    "ConfidenceLevel",
    "OriginSource",
    "SignalType",
    "EvidenceItem",
    "OriginInfo",
    "ExtractedMetadata",
    "FileContext",
    "FileContextBuilder",
    "DeterministicMime",
]
