# SmartSort File Intelligence Engine: Performance & Caching

## 1. Overview & Resource Boundaries

The File Intelligence Engine is engineered to be lightweight, deterministic, and bounded in resource utilization. It operates on systems ranging from modest single-board computers to high-end workstations without causing memory bloat or CPU starvation.

---

## 2. Resource & Extraction Boundaries

To guarantee bounded execution under all conditions:

| Parameter | Limit | Rationale |
|---|---|---|
| **Max Text Extraction** | `64 KB` | Sufficient to capture titles, abstracts, headings, and keywords while bounding RAM. |
| **Max PDF Pages Scanned** | `5 Pages` | First 5 pages contain 98% of relevant academic/title/abstract metadata. |
| **Max Slide Presentations** | `5 Slides` | Slide titles on first 5 slides capture topic and course information. |
| **Max Archive Member Scans** | `500 Entries` | Prevents denial-of-service on massive multi-gigabyte source archives. |
| **Extractor Execution Timeout** | `3.0 Seconds` | Prevents corrupted or pathological files from stalling batch scans. |
| **Max File Preview Snippet** | `1,024 Chars` | Keeps `FileContext` objects lightweight (< 4 KB memory per file). |

---

## 3. XDG Persistent Metadata Cache (`cache.py`)

To prevent re-extracting metadata on repeated scans or large directory reorganizations, an optional lightweight SQLite cache is maintained under `$XDG_CACHE_HOME/smartsort/metadata_cache.db` (`~/.cache/smartsort/`):

### 3.1 Cache Keying
Cache entries are indexed by a compound key:
$$\text{CacheKey} = (\text{CanonicalPath}, \text{inode}, \text{device}, \text{mtime}, \text{size\_bytes})$$

If `mtime` or `size_bytes` changes, the cache entry is automatically invalidated and recomputed.

### 3.2 Cache Schema
```sql
CREATE TABLE IF NOT EXISTS file_metadata_cache (
    file_path TEXT NOT NULL,
    inode INTEGER NOT NULL,
    device INTEGER NOT NULL,
    mtime REAL NOT NULL,
    size_bytes INTEGER NOT NULL,
    title TEXT,
    author TEXT,
    domain TEXT,
    keywords_json TEXT,
    headings_json TEXT,
    text_preview TEXT,
    origin_url TEXT,
    origin_domain TEXT,
    cached_at REAL NOT NULL,
    PRIMARY KEY (file_path, inode, mtime)
);
CREATE INDEX IF NOT EXISTS idx_cache_lookup ON file_metadata_cache(file_path, mtime, size_bytes);
```

### 3.3 Cache Invalidation & Expiry
- Maximum cache entries: 10,000 files (~5 MB disk space).
- Entries older than 30 days are purged automatically on startup.
- Cache can be cleared via **Settings → Clear Analysis Cache** or by deleting `~/.cache/smartsort/metadata_cache.db`.

---

## 4. Future Optimization Opportunities

1. **Parallel Batch Extraction**: In Directory Organizer mode, files can be extracted concurrently using `concurrent.futures.ThreadPoolExecutor` (bounded to CPU count).
2. **Lazy Deep Extraction**: Extract shallow filesystem metadata first; only trigger deep content extraction if filename and origin signals yield low confidence (< 0.60).
3. **Persistent Deduplication Index**: Maintain SHA-256 hashes across sessions to accelerate duplicate detection on re-scans.
