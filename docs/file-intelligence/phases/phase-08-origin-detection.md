# Phase 08: Local Browser Download History & Origin Resolution

## Objective
Implement `src/core/file_intelligence/origin.py` (`OriginDetector`) to recover local origin provenance (URL, source domain, site name) from file extended attributes (`xattrs`) and local browser SQLite download history databases without performing network requests.

## Why This Phase Exists
A file's origin is often the single most definitive signal for categorization. Knowing a `.zip` or `.pdf` originated from `canvas.university.edu` or `github.com` establishes domain context (`College` vs `Projects`) even if the filename is opaque.

## Inputs
- Target file path string and optional file size / timestamp.

## Outputs
- `src/core/file_intelligence/origin.py` (`OriginDetector`).
- Tests in `tests/test_file_intelligence/test_origin.py`.

## Files To Create
- `src/core/file_intelligence/origin.py`
- `tests/test_file_intelligence/test_origin.py`

## Files To Modify
- `src/core/file_intelligence/__init__.py`: Export `OriginDetector`.

## Existing Components To Reuse
- `src/core/filename_cleanup.py`: Reuse and expand `_CDN_TO_SITE` dictionary.
- `src/core/file_intelligence/context.py`: Populates `OriginInfo`.

## APIs / Interfaces
```python
# src/core/file_intelligence/origin.py
class OriginDetector:
    def __init__(self, config: Optional[ConfigManager] = None):
        self.config = config
        self.enabled = config.get("enable_origin_detection", True) if config else True

    def detect_origin(self, file_path: str, file_size: Optional[int] = None) -> OriginInfo:
        """
        Resolves origin provenance for a file from xattrs and browser SQLite history.
        Returns OriginInfo with sanitized domain, source type, and confidence.
        """
        ...
```

## Data Structures
- Consumes and populates `OriginInfo` from `src.core.file_intelligence.context`.

## Algorithms
- 1. **Extended Attribute Inspection**: Read `user.xdg.origin.url` and `user.xdg.referrer.url`. If present, source is `OriginSource.EXTENDED_ATTRIBUTE`, `confidence=CONFIRMED`.
- 2. **Local Browser SQLite Query**:
  - Checks Chrome, Chromium, Brave (`~/.config/*/Default/History`) and Firefox (`~/.mozilla/firefox/*.default*/places.sqlite`).
  - Matches by file path, filename, and download timestamp window.
  - Opens databases with `sqlite3.connect('file:' + path + '?mode=ro&immutable=1', uri=True)`.
- 3. **URL Sanitization**: Strips query strings, auth tokens, session IDs, and fragments.
- 4. **Domain Resolution**: Resolves clean domain and friendly site name using expanded `_CDN_TO_SITE` map.

## Error Handling
- Database locked by running browser: Catch `sqlite3.OperationalError`, create temporary memory/shadow copy in `/tmp`, or fall back to xattrs.

## Security & Privacy Considerations
- **NO NETWORK CALLS**: Zero external DNS lookups or HTTP requests.
- URL query parameters (`?auth=...`, `?token=...`) are **strictly stripped** before storage.

## Performance Considerations
- Xattr read: < 0.1 ms. Browser SQLite indexed lookup: < 5 ms.

## CI / Headless Requirements
- Test fixtures mock browser SQLite databases in `tmp_path`; tests must never access real user profile folders.

## Tests
- `tests/test_file_intelligence/test_origin.py`:
  - Test xattr extraction on simulated file.
  - Test mock Chromium SQLite database resolution.
  - Test mock Firefox SQLite database resolution.
  - Test URL query parameter stripping and domain sanitization.
  - Test graceful behavior when browser DB is locked or absent.

## Acceptance Criteria
- [ ] `OriginDetector` resolves provenance from both xattrs and browser DBs.
- [ ] Query strings and auth tokens stripped from all recorded URLs.
- [ ] 100% test pass on `test_origin.py`.

## Dependencies
- Standard library `sqlite3`, `urllib.parse`, `os`.

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [ ] `origin.py` implemented.
- [ ] Unit tests passing.
