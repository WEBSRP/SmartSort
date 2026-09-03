# SmartSort File Intelligence Engine: Origin & Provenance Detection

## 1. Overview & Objectives

Origin detection resolves where a file came from using **only local machine evidence**. Knowing that a file originated from `canvas.university.edu` or `github.com` provides unambiguous evidence for categorization (e.g. `College` vs `Projects`), even when the filename is cryptic (e.g. `download_392.zip`).

The origin detector operates under strict constraints:
1. **100% Offline**: No network requests, DNS lookups, or HTTP queries.
2. **Read-Only / Lock-Safe**: Accesses browser databases using immutable read-only flags or in-memory shadow copies to ensure active browser sessions are never locked or corrupted.
3. **No Speculation**: If no local trace exists, origin is explicitly marked as `Confidence.UNKNOWN`.
4. **Privacy-Preserving**: Only top-level domains and clean site names are exposed in classification justifications. Sensitive URL query parameters (tokens, auth tickets, session IDs) are stripped immediately.

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

### 3.3 Concurrency & Lock Safety
Opening an active SQLite database locked by a running browser can result in `sqlite3.OperationalError: database is locked`. The Origin Detector guarantees safety by:
1. Connecting with immutable read-only URI: `sqlite3.connect('file:' + db_path + '?mode=ro&immutable=1', uri=True)`.
2. Setting busy timeout: `pragma busy_timeout = 1000`.
3. If database is exclusively locked, creating a temporary shadow copy in `/tmp` using atomic file descriptors.

---

## 4. URL Sanitization & Domain Categorization

To maintain user privacy and generate clean classification signals, URLs are sanitized:

1. **Query & Fragment Stripping**:
   `https://canvas.stanford.edu/courses/102/files/302?download_frd=1&token=xyz`
   $\rightarrow$ Clean Origin: `https://canvas.stanford.edu/courses/102/files/302`
   $\rightarrow$ Domain: `canvas.stanford.edu`
   $\rightarrow$ Site Name: `canvas`

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
- **Local Isolation**: Extracted URLs and domains are stored strictly in-memory during execution and included in the local `SmartSort_Arrangement.md` index. No data is sent off-device.
