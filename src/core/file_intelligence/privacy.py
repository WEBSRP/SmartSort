"""Idempotent URL/EXIF filtering before feature derivation and persistence.

This handles HTTP(S) URL credentials, queries, fragments and matrix parameters;
it is not a general secret detector for ordinary document text or file names.
"""

import re

from src.core.file_intelligence.context import ExtractedMetadata


_URL = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)
_EXIF_ALLOWLIST = {'Make', 'Model', 'Software', 'DateTime', 'DateTimeOriginal', 'LensModel'}


def redact_url_text(value):
    """Strip private URL components without changing non-URL text."""
    if '://' not in value:
        return value
    from src.core.file_intelligence.origin import origin_from_url
    def replace(match):
        raw = match.group()
        # Keep trailing list separators outside the filtered URL. Internal
        # semicolons/commas remain part of URL parsing and cannot expose tokens.
        url = raw
        pairs = {')': '(', ']': '[', '}': '{'}
        while url:
            tail = url[-1]
            if tail in ',;' or (tail in pairs and url.count(tail) > url.count(pairs[tail])):
                url = url[:-1]
            else:
                break
        suffix = raw[len(url):]
        return (origin_from_url(url).url or '[redacted URL]') + suffix
    return _URL.sub(replace, value)


def redact_values(value):
    """Return a filtered copy of JSON-shaped values."""
    if isinstance(value, str):
        return redact_url_text(value)
    if isinstance(value, list):
        return [redact_values(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_values(item) for key, item in value.items()}
    return value


def normalize_metadata(metadata):
    """Give cold, disabled-cache and cached callers the same independent profile.

    Extractors must additionally filter text before deriving keywords: token-only
    data cannot in general be traced back to a private URL at this boundary.
    """
    data = metadata.to_dict()
    data['exif_tags'] = {key: value for key, value in data['exif_tags'].items()
                         if key in _EXIF_ALLOWLIST}
    return ExtractedMetadata.from_dict(redact_values(data))
