# SmartSort File Intelligence Engine: Security & Privacy

## 1. Threat Model & Security Boundaries

SmartSort operates directly on untrusted user downloads and filesystem directories. The File Intelligence Engine enforces strict defensive boundaries against common attack vectors.

---

## 2. Security Safeguards

### 2.1 Path Traversal & Escape Prevention
- **Attack Vector**: A file with crafted metadata or rule destination (e.g. `../../../../etc/shadow` or relative escape) attempting to write outside the target root.
- **Defense**: Canonical common path validation:
  ```python
  root_abs = os.path.abspath(root_dir)
  target_abs = os.path.abspath(target_path)
  if os.path.commonpath([root_abs, target_abs]) != root_abs:
      raise ValueError(f"Path Traversal Blocked: {target_abs} escapes root {root_abs}")
  ```
- **System Roots Blocklist**: Rejects protected system roots (`/`, `/etc`, `/usr`, `/bin`, `/var`, `/boot`, `/sys`, `/proc`, `/dev`).

### 2.2 Zip Bomb & Decompression Attacks
- **Attack Vector**: Nested or highly compressed archives designed to exhaust disk space or RAM during extraction.
- **Defense**:
  1. Archive extractors **never decompress files to disk** during analysis.
  2. Inspection is limited to reading the central directory table-of-contents header in memory.
  3. Header inspection is bounded to a maximum of 500 entries.

### 2.3 Malformed File & Parser Exploits
- **Attack Vector**: Corrupted PDF, Image, or Office files triggering parser crashes or memory leaks in third-party libraries.
- **Defense**:
  1. All extraction calls are wrapped in generic exception isolation blocks (`try ... except Exception as e`).
  2. Hard execution timeout per file (3.0s in batch, 2.0s in daemon).
  3. Pure-Python fallback extractors available if native libraries encounter segfaults or parsing errors.

### 2.4 Symlink & Link Hijacking
- **Attack Vector**: Symlinks pointing to sensitive files (`/etc/passwd`) or circular directory links.
- **Defense**: `scan()` ignores all symlinks (`os.path.islink(path) == True` $\rightarrow$ skipped). `shutil.copy2` and `os.walk(followlinks=False)` guarantee symlink targets are never recursively traversed or overwritten.

---

## 3. Privacy Policy & Data Retention

### 3.1 Zero Network Egress
SmartSort contains zero network client code, telemetry reporters, or cloud API integrations. All analysis is executed locally on CPU.

### 3.2 URL Parameter & Token Sanitization
When extracting download URLs from browser databases or xattrs:
- Authentication tokens, API keys, session IDs, and query parameters (`?token=...`, `?auth=...`) are stripped immediately.
- Only the clean scheme, domain, and file path are retained (e.g. `https://canvas.stanford.edu/files/102`).

### 3.3 EXIF Location Redaction
- EXIF `GPSInfo` tags (latitude, longitude, altitude) are **explicitly filtered out** during image extraction.
- GPS coordinates are never stored in `FileContext`, never cached, and never rendered into `SmartSort_Arrangement.md`.

### 3.4 User Privacy Controls
Users maintain full control over metadata collection via Settings:
- `enable_origin_detection: false` $\rightarrow$ Completely disables browser database and xattr queries.
- `enable_deep_content_extraction: false` $\rightarrow$ Disables text parsing inside PDFs/DOCX/Archives, using only filename and filesystem stats.
- `clear_analysis_cache()` $\rightarrow$ Deletes all cached metadata and origin records.
