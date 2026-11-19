# SmartSort File Intelligence Engine: Origin & Provenance Detection


Phase 17 adds private XDG SQLite caching of successful extraction and corroborated
origins, with identity and provenance invalidation. See the
[cache implementation notes](phases/phase-17-caching-performance.md) for API,
privacy, retention and performance limits.

## 1. Overview & Objectives

Origin detection resolves where a file came from using **only local machine evidence**. A corroborated origin such as `canvas.university.edu` or `github.com` provides useful context for later categorization even when the filename is cryptic. Metadata matching is evidence, not cryptographic proof of a download's identity.

The origin detector operates under strict constraints:
1. **100% Offline**: No network requests, DNS lookups, or HTTP queries.
2. **Read-Only / Lock-Safe**: SQLite queries private, bounded main/WAL snapshots, never live browser paths. Original histories are read only as regular files and receive no application writes.
3. **No Speculation**: If no local trace exists, origin is explicitly marked as `Confidence.UNKNOWN`.
4. **Privacy-Preserving**: Returned URLs are validated HTTP(S) URLs with credentials, queries, fragments, and matrix/session parameters removed. Hostnames and friendly site names are resolved locally. Generic evidence descriptions contain no raw SQL diagnostics or source paths.

---

## 2. Evidence Sources & Extraction Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. EXTENDED ATTRIBUTES (xattrs)                                             │
│    - Read `user.xdg.origin.url` and `user.xdg.referrer.url`                 │
│    - Set natively by Chrome, Chromium, Firefox on Linux                     │
│    - Speed: < 0.1 ms per file                                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (If not found or incomplete)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. LOCAL BROWSER DOWNLOAD DATABASES (SQLite Read-Only)                      │
│    - Chromium-based: Chrome, Chromium, Brave, Edge (`History` SQLite DB)    │
│    - Gecko-based: Firefox (`places.sqlite` SQLite DB)                       │
│    - Matched by target path, filename, file size, and download timestamp    │
│    - Speed: ~ 2-5 ms query                                                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (If not found)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. INTERNAL DOCUMENT EMBEDDED URLS                                          │
│    - PDF URI action links, Word metadata source links                       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (If not found)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. SIBLING BATCH INHERITANCE (Directory Mode Only)                          │
│    - If 5 files in a subfolder share an origin, remaining siblings inherit  │
│      origin with `Confidence.PROBABLE`                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Browser Database Integration

### 3.1 Chromium / Chrome / Brave Discovery
- **Database Paths**:
  - `~/.config/google-chrome/Default/History`
  - `~/.config/chromium/Default/History`
  - `~/.config/BraveSoftware/Brave-Browser/Default/History`
- **Tables & Query**:
  ```sql
  SELECT target_path, tab_url, tab_referrer_url, start_time, total_bytes
  FROM downloads
  WHERE target_path = ? OR target_path LIKE ?
  ORDER BY start_time DESC LIMIT 1;
  ```

The Phase 08 implementation first queries exact paths, then an escaped filename
fallback if no exact rows exist. It also reads `downloads_url_chains`, preferring
the last valid redirect URL over tab/referrer URLs. Chromium timestamps are
microseconds since 1601 (legacy Unix-second schemas are also supported). Known
incomplete states and contradictory size/time metadata are rejected. Default
and `Profile *` directories are discovered for Chrome, Chromium, Brave, and Edge
under `XDG_CONFIG_HOME`; browser locations are bounded rather than searched
across the filesystem.

### 3.2 Firefox Discovery
- **Database Paths**:
  - `~/.mozilla/firefox/*.default*/places.sqlite`
- **Tables & Query**:
  ```sql
  SELECT p.url, a.content, a.dateAdded
  FROM moz_places p
  JOIN moz_annos a ON p.id = a.place_id
  WHERE a.content LIKE ?
  ORDER BY a.dateAdded DESC LIMIT 1;
  ```

Current Firefox inspection selects destination-file annotations by attribute
name and joins them to `moz_places` source URLs. `downloads/metaData` supplies
state, file size, and millisecond end time; annotation `dateAdded` uses Unix
microseconds. Reduced schemas without full metadata receive less corroboration.
Standard, Snap, and Flatpak Firefox roots and declared `profiles.ini` profiles
are supported. The SQL examples above describe the evidence; actual queries
use bound exact-path parameters, escaped LIKE patterns, and bounded fields/rows.

### 3.3 Concurrency & Lock Safety
The detector creates private temporary copies before making a SQLite connection.
It copies main/WAL data with before/after identity, size, mtime, and ctime checks,
allowing one retry if the source changes. Rollback journals are conservatively
skipped. Snapshot directories are 0700 and files 0600; all are removed before
the call returns.

Stable copies without WAL use `mode=ro&immutable=1`. Copies with a non-empty WAL
use `mode=ro` so committed WAL-only records remain visible. SQLite's immutable
flag is not used on an actively changing original: it disables locking and
change detection and can produce incorrect results if that assumption is false.
See [SQLite URI semantics](https://www.sqlite.org/uri.html).

Limits per detection: 64 MiB copied in total (including retries/WAL), 32
profiles, 64 matching rows per history, and a two-second cooperative deadline.
SQLite uses query-only/trusted-schema settings, bounded selected fields, and a
progress callback. Snapshot checks are best effort, not an atomic filesystem
snapshot or a coordinated SQLite backup; hot or oversized histories can yield
unknown. Real-history latency can exceed the small-fixture 5 ms target.

### 3.4 Corroboration and Confidence

- Valid xattrs take precedence and return `CONFIRMED`.
- Exact browser path + matching size + timestamp within 24 hours returns
  `CONFIRMED`; supported weaker exact-path matches return `PROBABLE`.
- Filename fallback requires both size equality and matching time, and returns
  `PROBABLE`. Default file timestamps use mtime/ctime; callers may supply an
  explicit Unix-second `file_timestamp`.
- Known contradictions, failed downloads, too many matching records, and
  equally strong conflicting URLs near the best timestamp return unknown.

---

## 4. URL Sanitization & Domain Categorization

To maintain user privacy and generate clean classification signals, URLs are sanitized:

1. **Query & Fragment Stripping**:
   `https://canvas.stanford.edu/courses/102/files/302?download_frd=1&token=xyz`
   $\rightarrow$ Clean Origin: `https://canvas.stanford.edu/courses/102/files/302`
   $\rightarrow$ Domain: `canvas.stanford.edu`
   $\rightarrow$ Site Name: `lms`

2. **CDN & Hostname Resolution**:
   Reuses and expands the existing `_CDN_TO_SITE` dictionary from `filename_cleanup.py`:
   - `github.com` / `raw.githubusercontent.com` $\rightarrow$ `github` (Domain affinity: `Projects`, `Code`)
   - `*.instructure.com` / `canvas.*` / `moodle.*` / `*.blackboard.com` $\rightarrow$ `lms` (Domain affinity: `College`)
   - `arxiv.org` / `ieee.org` / `acm.org` $\rightarrow$ `academic_paper` (Domain affinity: `College`, `Research`)
   - `kaggle.com` $\rightarrow$ `kaggle` (Domain affinity: `Projects`, `Data`)
   - `wallpaperflare.com` / `unsplash.com` $\rightarrow$ `wallpaper` (Domain affinity: `Images`)

---

## 5. Privacy & User Control

- **Configuration Toggle**: `enable_origin_detection: bool` in `config.json` (defaults to `true`). When set to `false`, zero browser databases or xattrs are scanned.
- **Local Isolation**: Returned evidence remains in memory. Temporary history copies contain private browser data, have restricted permissions, and are deleted before return. No data is sent off-device or included in backend exception logs.
- **Current Phase Boundary**: The toggle governs `OriginDetector`; existing standalone xattr helpers share URL sanitization. Live organizer/GUI/report integration is deferred to its designated phases. Embedded-document URL inference and sibling inheritance in the overview are also deferred.
- **Sanitization Limits**: URLs over 4,096 characters and unsupported schemes are rejected. Known credential/query/fragment/session carriers are removed; opaque identifiers in retained URL paths cannot be generically identified as secrets. Unknown hostnames remain intact instead of guessing public suffixes.

For completion status, tests, timing observations, and remaining boundaries, see
[Phase 08](phases/phase-08-origin-detection.md).
