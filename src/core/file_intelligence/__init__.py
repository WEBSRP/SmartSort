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

__all__ = [
    "ConfidenceLevel",
    "OriginSource",
    "SignalType",
    "EvidenceItem",
    "OriginInfo",
    "ExtractedMetadata",
    "FileContext",
]
