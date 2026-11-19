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
- `src/core/file_intelligence/origin.py`: Cache redacted origins with provenance-source invalidation.

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
- SQLite schema: `file_metadata_cache` table with composite primary key `(file_path, inode, mtime, namespace)`. Device, size, nanosecond mtime/ctime and creation time are stored alongside JSON. Namespaces separate extraction modes, policy versions and provenance fingerprints.

## Algorithms
- Invalidation check: `SELECT metadata_json FROM file_metadata_cache WHERE file_path=? AND inode=? AND mtime=? AND size_bytes=?`.
- Cache size pruning: Retains max 10,000 entries; purges records older than 30 days on startup.

## Error Handling
- Corrupted cache DB: Automatically rebuilds schema without throwing fatal exceptions.

## Security Considerations
- Redacted fields (GPS tags, URL auth tokens) are never saved to cache.

## Performance Considerations
- Targets: cache lookup < 0.05 ms; repeat scan speedup 10x–20x. Small metadata meets the lookup target locally; full 64 KB metadata does not. See measurements below.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_cache.py`:
  - Test store and retrieve `ExtractedMetadata`.
  - Test cache invalidation when file `mtime` or `size` changes.
  - Test automatic schema creation and recovery from corrupted SQLite files.
  - Test `clear()` operation.

## Acceptance Criteria
- [x] `MetadataCache` stores and retrieves metadata with composite key invalidation.
- [x] Cache located inside standard `$XDG_CACHE_HOME/smartsort/`.
- [x] 100% test pass on `test_cache.py`.

## Dependencies
- Standard library `sqlite3`, `json`, `os`.

## What This Phase MUST NOT Change
- Must NOT alter file organizing or transfer safety logic.

## Completion Checklist
- [x] `cache.py` implemented.
- [x] Unit tests passing.


## Implementation State — 2026-11-18

Functional implementation is complete in the working tree. `MetadataCache` is
exported and defaults to `AppPaths.cache_dir() / "metadata_cache.db"`. The database
is private (0600), uses WAL, a 20 ms SQLite busy timeout and one explicitly locked
connection per instance. It has `close()` and context-manager support and closes
on destruction; it creates no threads or pools. Registry/detector default caches
are created lazily. `cache=False` or `cache=None` disables persistence, and callers
can inject a cache instance for tests or an explicit database location.

### Reuse and invalidation

Registry lookup occurs before MIME/content inspection and rechecks identity after
lookup and extraction. Normal and bounded download dispatch use separate versioned
namespaces. Only `SUCCESS` is stored: partial/unsupported/failed/timed-out work is
retried, so temporary failures and missing optional backends do not become sticky.
Custom runtime registrations bypass persistence. The download worker's original
process limit/kill/reap implementation is unchanged. Source symlinks and nonregular
files bypass the registry cache and retain the original extractor behavior.

Production registry callers compare path, inode, device, size, floating mtime,
nanosecond mtime and ctime. The original public four-argument `get` API remains
available; direct callers should supply the optional device/nanosecond identity
keywords for equivalent checks. These stat fields are freshness heuristics, not
checksums: an edit preserving every tracked field (including on coarse timestamp
filesystems) can remain undetected. Clearing the cache forces fresh extraction.

Origin caching is integrated at `OriginDetector` because origins depend on sources
outside the extractor registry. It additionally fingerprints current xattr values,
matching inputs, discovered browser databases, and main/WAL/journal stat identities.
Fingerprints store hashes rather than raw xattrs. A valid xattr still bypasses all
browser discovery. File and provenance state are rechecked before accepting hits
or writing entries. Browser changes, new/disappearing profiles, and xattr changes
invalidate reuse; unknown results are not stored. Origin opt-out takes precedence
over any cached data. Browser snapshot/query/retry code is unchanged.

### Recovery, privacy and limits

Each JSON payload is capped at 256 KiB. Reads validate shapes and reconstruct
independent metadata objects. EXIF uses the existing six-field camera allowlist;
GPS fields are removed. URL credentials, query strings, fragments and matrix/session
parameters are stripped throughout serialized metadata and origins. Filtering does
not modify caller-owned objects. This is URL/EXIF redaction, not a general detector
for arbitrary secrets embedded in document text. Filenames and bounded document
previews remain local cache content, so database permissions matter.

Startup prunes entries older than 30 days; reads reject expired entries and writes
also prune age and enforce the global 10,000-entry limit. Each extraction namespace
keeps the newest identity for a path. Origin provenance variants share the same
global retention limit. The row cap is not a fixed database-byte quota. `clear()`
removes all logical records but does not promise secure erasure from storage.

Recognized corruption is rebuilt at initialization; an incompatible owned schema
is recreated. Busy/read-only/full/unavailable caches produce misses or skipped
writes without preventing extraction or deleting the database. Malformed JSON is
a miss. Cache-file symlinks and nonregular files are refused. Corruption arising
after initialization fails open and is rebuilt when a new cache instance opens.
SQLite waits are bounded, but filesystem calls have no hard wall-clock guarantee.

### Validation and performance

- Baseline **1,334 passed, 1 skipped**; **53 new tests** cover round trips and
  process restarts, identity/policy/provenance invalidation, retention, privacy,
  malformed/corrupt/locked/unavailable caches, thread sharing, custom/disabled
  registries, bounded extraction, partial retries and source mutation during hits.
- Full suite **1,387 passed, 1 skipped** in 27.47 s with preserved pytest exit code
  **0**, despite the existing Qt teardown's forced-exit-zero backstop.
- Full source compilation, whitespace checks and Qt import-boundary checks pass.
  SHA-256 comparisons confirm `DirectoryOrganizer`, `FileUtils` and `FileOrganizer`
  are unchanged; no organizing/transfer decisions were changed.
- 2,000 direct successful gets: small metadata median **0.0282 ms**, p95 **0.0311
  ms**; approximately 64 KB metadata median **0.2006 ms**, p95 **0.2200 ms**.
  The large-record lookup target of **0.05 ms remains unmet**.
- Synthetic 100-PDF preview, origin detection disabled: cold **21.3547 s**, warm
  median **0.0542 s**, range **0.0478–0.0691 s** across five runs (**393.9x** local
  speedup), with identical destinations/confidence/evidence. Cold parsing still
  misses the earlier ten-second PDF preview target. A separate earlier run was
  17.9136 s cold / 0.0542 s warm; shared-machine load affects these observations.
- Caching does not improve Phase 16's report-writing latency; its 2 ms target
  remains outstanding. These measurements are fixtures, not portable guarantees.

Next: Phase 18 — Full Integration Testing & Multi-Domain Verification.


## Follow-up repair after Phase 18 verification

The initial cache implementation had two confirmed defects: the first extraction
returned unfiltered metadata while cached reads returned filtered metadata, and
private URL parts could already have become standalone keywords before cache
serialization. Both are repaired in the follow-up preceding Phase 19.

`privacy.py` now supplies one idempotent, copying metadata normalizer used for
fresh, partial, custom, disabled-cache and cached registry results, and defensively
for cache reads/writes. Text is filtered before keyword derivation (including the
shared helper used by code, PDF and Office). Explicit PDF/Office keyword fields
are filtered before delimiter splitting. Markdown delimiters and balanced URL
parentheses/IPv6 brackets are retained. Source paths and original file bytes are
unchanged. Statuses and byte/worker budgets are preserved.

Schema version 2 and `extractors-v2` namespaces invalidate active legacy cache
records; previously derived token-only data cannot be reliably repaired in place.
This is logical cache invalidation, not a promise of forensic erasure of old
SQLite/WAL pages, backups, or records written by an older still-running process.

The former two expected failures are now ordinary passing regression tests, with
36 additional privacy/normalization cases. See the Phase 18 follow-up verification
report for final full-suite results. Existing performance limitations remain.
