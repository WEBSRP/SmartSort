# Phase 17: XDG Caching Layer & Performance Optimization

## Objective
Implement `src/core/file_intelligence/cache.py` (`MetadataCache`) to persist extracted metadata and origin records across scans in `$XDG_CACHE_HOME/smartsort/metadata_cache.db`, eliminating redundant extraction on unchanged files.

## Why This Phase Exists
Extracting metadata from hundreds of large documents (PDFs, PPTX, Images) on every directory preview consumes unnecessary CPU cycles. Persistent caching keyed by `(inode, mtime, size)` provides sub-millisecond retrieval on repeat scans while automatically invalidating modified files.

## Inputs
- `FileContext` instances and file stat tuples.

## Outputs
- `src/core/file_intelligence/cache.py` (`MetadataCache`).
- Tests in `tests/test_file_intelligence/test_cache.py`.

## Files To Create
- `src/core/file_intelligence/cache.py`
- `tests/test_file_intelligence/test_cache.py`

## Files To Modify
- `src/core/file_intelligence/__init__.py`: Export `MetadataCache`.
- `src/core/file_intelligence/extractors/base.py`: Integrate cache lookup in `ExtractorRegistry`.

## Existing Components To Reuse
- `src/utils/paths.py`: Uses `AppPaths.cache_dir()`.

## APIs / Interfaces
```python
# src/core/file_intelligence/cache.py
class MetadataCache:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(AppPaths.cache_dir() / "metadata_cache.db")
        self._init_db()

    def get(self, file_path: str, inode: int, mtime: float, size_bytes: int) -> Optional[ExtractedMetadata]:
        """Retrieves cached metadata if mtime and size match exactly."""
        ...

    def put(self, file_path: str, inode: int, device: int, mtime: float, size_bytes: int, metadata: ExtractedMetadata) -> None:
        """Saves extracted metadata to persistent cache."""
        ...

    def clear(self) -> None:
        """Clears all cached records."""
        ...
```

## Data Structures
- SQLite schema: `file_metadata_cache` table with composite primary key `(file_path, inode, mtime)`.

## Algorithms
- Invalidation check: `SELECT metadata_json FROM file_metadata_cache WHERE file_path=? AND inode=? AND mtime=? AND size_bytes=?`.
- Cache size pruning: Retains max 10,000 entries; purges records older than 30 days on startup.

## Error Handling
- Corrupted cache DB: Automatically rebuilds schema without throwing fatal exceptions.

## Security Considerations
- Redacted fields (GPS tags, URL auth tokens) are never saved to cache.

## Performance Considerations
- Cache lookup: < 0.05 ms. Repeat scan speedup: 10x - 20x.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_cache.py`:
  - Test store and retrieve `ExtractedMetadata`.
  - Test cache invalidation when file `mtime` or `size` changes.
  - Test automatic schema creation and recovery from corrupted SQLite files.
  - Test `clear()` operation.

## Acceptance Criteria
- [ ] `MetadataCache` stores and retrieves metadata with composite key invalidation.
- [ ] Cache located inside standard `$XDG_CACHE_HOME/smartsort/`.
- [ ] 100% test pass on `test_cache.py`.

## Dependencies
- Standard library `sqlite3`, `json`, `os`.

## What This Phase MUST NOT Change
- Must NOT alter file organizing or transfer safety logic.

## Completion Checklist
- [ ] `cache.py` implemented.
- [ ] Unit tests passing.
