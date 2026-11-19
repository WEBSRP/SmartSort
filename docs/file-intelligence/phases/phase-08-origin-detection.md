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
- `src/core/file_intelligence/metadata.py`: Share URL sanitization with the
  existing xattr foundation helper, including credential removal.
- `src/utils/config.py` and `config/config.default.json`: Persist and validate
  the `enable_origin_detection` boolean, including loading older settings.

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

    def detect_origin(self, file_path: str, file_size: Optional[int] = None,
                      *, file_timestamp: Optional[float] = None) -> OriginInfo:
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
  - Checks Chrome, Chromium, Brave, and Edge Default/Profile directories under
    `XDG_CONFIG_HOME`, plus Firefox standard/Snap/Flatpak roots and `profiles.ini`.
  - Matches by file path, filename, and download timestamp window.
  - Copies bounded, stable main/WAL files into a private temporary directory.
    SQLite opens only these copies, never the live browser path. Copies without
    WAL use `mode=ro&immutable=1`; copies with WAL use `mode=ro` to preserve
    committed WAL-only records. All snapshots are cleaned before returning.
- 3. **URL Sanitization**: Strips query strings, auth tokens, session IDs, and fragments.
- 4. **Domain Resolution**: Resolves clean domain and friendly site name using expanded `_CDN_TO_SITE` map.

## Error Handling
- Locked live databases do not need a live SQLite connection: queries operate
  on private snapshots. Corrupt/inaccessible/changing histories, rollback
  journals, exceeded budgets, unsupported schemas, and ambiguous results
  degrade to unknown without backend diagnostics or raw URL logging.

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
- [x] `OriginDetector` resolves provenance from both xattrs and browser DBs.
- [x] Query strings and auth tokens stripped from all recorded URLs.
- [x] 100% test pass on `test_origin.py`.

## Dependencies
- Standard library `sqlite3`, `urllib.parse`, `os`.

## What This Phase MUST NOT Change
- Must NOT modify existing file organizing or move logic.

## Completion Checklist
- [x] `origin.py` implemented.
- [x] Unit tests passing.

## Implementation State — 2026-11-15

Phase 08 is complete in the local working tree. No new dependencies were added;
all browser fixtures and profile discovery tests use temporary synthetic homes.
Real user browser profiles were not accessed during implementation or testing.

Implemented behavior:

- Xattr origin URL takes precedence, followed by a valid referrer. Invalid
  metadata is skipped. The shared sanitizer accepts HTTP(S) only, removes URL
  userinfo, query strings, fragments, and path matrix/session parameters,
  normalizes hosts locally (including IDNA/IPv6), and rejects invalid ports,
  control characters, malformed URLs, and URLs over 4,096 characters.
- Friendly names reuse a copy of `_CDN_TO_SITE` with explicit source/LMS,
  academic, and media mappings. Suffix matches respect DNS label boundaries;
  unknown hosts retain their full hostname rather than guessing a registrable
  domain from the last two labels. No DNS or network resolution takes place.
- Chromium uses the final valid redirect-chain URL before legacy `url`,
  `tab_url`, referrer fields. Current `target_path` and legacy `full_path`
  schemas are supported, with Chromium microseconds-since-1601 and legacy
  Unix-second timestamps. Known incomplete/failed states are rejected.
- Firefox reads `downloads/destinationFileURI` and `downloads/metaData`
  annotations joined to source URLs in `moz_places`; destination URIs are
  decoded locally. Metadata supplies state, file size, and millisecond end
  time, with microsecond annotation time as fallback. Reduced annotation
  schemas are supported with less corroboration.
- Exact paths take precedence over filename fallbacks. Known size/time
  contradictions are rejected. Filename fallback requires size equality and
  a timestamp within 24 hours. Default timestamps come from target mtime/ctime;
  callers may supply a Unix-second `file_timestamp`. Exact path + size + time
  yields `CONFIRMED`; weaker supported matches yield `PROBABLE`. Equally
  strong conflicting URLs within one second of the best match yield unknown.
- Queries use bound parameters and escaped LIKE metacharacters. Excessive
  matching rows return unknown. Oversized source URLs are rejected, not
  silently truncated into different URLs. Evidence text contains only generic
  match descriptions, not source paths, SQL errors, or raw browser values.
- `enable_origin_detection` defaults to true and survives config save/reload.
  When false, `OriginDetector` returns before xattr, target-stat, or history
  reads. Changing the supplied config is honored on subsequent calls.

Snapshot and resource boundaries:

- SQLite receives only private temporary copies. Main and non-empty WAL data
  are copied together; private copies with WAL use read-only WAL-aware SQLite,
  while stable no-WAL copies use immutable read-only mode. SQLite is not asked
  to treat an active, changing original database as immutable.
- Snapshot directories are private (0700), copied files are 0600, inputs must
  be regular files, and symlink database/profile-registry inputs are skipped.
  Input identities/sizes/mtime/ctime are checked before and after copying;
  one retry is allowed. Rollback-journal histories are conservatively skipped.
- Each detection has a **64 MiB cumulative snapshot budget**, including WAL
  and retries, at most **32 profiles**, **128 child directories per root**,
  **64 matching records per history**, and a **two-second cooperative deadline**.
  Copying uses at most 64 KiB per read. SQLite uses a progress callback,
  read-only/query-only connections, trusted-schema restrictions, a small page
  cache, and bounded selected fields. Snapshots are removed before return.

Validation on Python 3.13.5:

- **107 Phase 08 tests passed**, no failures or skips.
- **835 full-suite tests passed, 1 existing skip**, genuine pytest exit code
  **0**. Baseline: **728 passed, 1 skipped**. The existing skip remains the
  Phase 02 permission test under a privileged user.
- Tests cover both browser families and schema variants, profile discovery,
  xattr priority, URL redaction/host mapping, size/time/state corroboration,
  ambiguity, filename collisions/escaping, WAL-only committed records, empty
  WALs, exclusive locks, rollback journals, snapshot retries/cleanup/permissions,
  oversized inputs, symlinks/FIFOs, config persistence, source database hashes,
  concurrent calls, and Qt-free fresh-process imports.
- Compilation and whitespace checks pass. Tests preserve pytest's actual
  return value before the existing Qt teardown exit-zero hook; test state and
  bytecode output are directed to temporary locations.

Performance observations (20 warm detections per small synthetic fixture):

| Evidence path | First observed call | Warm median | Warm maximum |
|---|---:|---:|---:|
| Mocked xattr read + sanitization | 0.821 ms | 0.018 ms | 0.045 ms |
| Chromium snapshot + lookup | 0.768 ms | 0.549 ms | 1.032 ms |
| Firefox snapshot + lookup | 0.725 ms | 0.607 ms | 0.781 ms |

These observations meet the browser 5 ms target for these fixtures. The mocked
xattr warm path meets 0.1 ms; its first call does not. This does not establish
real filesystem xattr latency or performance on large histories. Copying real
histories can exceed 5 ms; the budgeted snapshot strategy prioritizes avoiding
live-profile writes and retaining committed WAL records.

Remaining boundaries:

- Stable-copy checks are best effort, not SQLite's coordinated backup API or
  an atomic filesystem snapshot. Rapidly changing or large histories can yield
  unknown. Reads/syscalls are cooperatively bounded, not process-isolated;
  there is no universal hard memory or wall-clock cap.
- Supported history schemas are inspected locally; removed/private history,
  missing annotations, uncommon schemas/profile locations, moved/renamed files,
  changed timestamps, or an exhausted discovery/query budget can prevent a
  match. No broad browser-history cache or arbitrary filesystem search is added.
- Confidence expresses metadata corroboration, not cryptographic proof of
  download identity. Friendly site mappings are local heuristics. Arbitrary
  opaque identifiers in retained URL paths cannot be generically recognized
  as secrets; known URL credential/query/fragment/session carriers are removed.
- No embedded-document URL inference, sibling inheritance, signal extraction,
  classifier, GUI toggles, report output, or live organizer integration is added.
  The foundation xattr helper shares sanitization but does not start browser
  discovery. Runtime integration remains in its later designated phases.
- Existing GUI, Debian packaging, organizing/transfer logic, and earlier
  pending changes remain intact. Changes are uncommitted.

References: [Chromium download database](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/components/history/core/browser/download_database.cc),
[Mozilla DownloadHistory](https://raw.githubusercontent.com/mozilla/gecko-dev/master/toolkit/components/downloads/DownloadHistory.sys.mjs),
[SQLite URI/immutable semantics](https://www.sqlite.org/uri.html), and
[SQLite WAL behavior](https://www.sqlite.org/wal.html).

Next implementation phase: **09 — Normalized Signal Processing & Feature Extraction**.
