# Downloads sorting validation — SmartSort 1.2.3

Ran on 2026-11-18 using real watchdog events and the FileMonitor → FileOrganizer
pipeline, with a copied snapshot of the saved user rules. The saved mode is
Rules first. Both Rules first and Content intelligence were exercised without
changing the user's active mode or config. Test folders were inside the actual
configured Downloads directory; sorted destinations and private application
state were contained inside each generated test folder. Existing personal files
were not inputs to this test.

## Findings and fixes

1. `.tar.gz` missed the configured Archives extension rule and reached Others.
   Extension conditions now compare a normalized suffix against the basename,
   supporting compound extensions and uppercase filenames while rejecting
   misleading suffixes such as `.tar.gz.exe`.
2. The generated big-video rule contained `2684354560GB` instead of a 2.5 GB
   boundary. Migration had appended GB after ConfigManager normalized the setting
   to bytes. New migrations emit the correct unit. Existing rules are repaired
   only when the generated rule identity, condition structure, operator and
   double-conversion value match the known bug; edited/custom rules are retained.
   Normal RuleManager startup persists the repair with a config backup. The user's
   live configuration was not modified during validation.
3. A replacement download could reuse both filename and inode/device immediately
   after deletion, causing the watcher to treat it as already processed. Watcher
   deduplication now also compares size and nanosecond modification/change times.
   Stability checks use these timestamps too, catching same-size writes. An old
   worker no longer clears a newer replacement's pending state.

## Results

- Initial live run: 50 recorded scenarios; reproduced compound archive routing,
  video threshold routing and reused-path failures in both sorting modes.
- Fixed run: 50 scenarios passed. Extended run: **70 scenarios passed**.
- Ordinary files ranged from empty through 8,388,600 bytes. Valid PNG files at
  1 MB ± 1 byte and 5 MB ± 1 byte followed the expected Low/Medium/High image rules.
  JPEG, WebP, GIF and BMP encodings were also tested.
- Included text/Markdown, source code, JSON, blank PDF, malformed PDF/video,
  ZIP/tar.gz, WAV, Unicode names, extensionless/unknown files, and synthetic Office
  XML packages for DOCX/PPTX/XLSX/ODT/ODP/ODS.
- Every successful transfer was checked against its original SHA-256 and source
  removal. Partial and hidden files remained untouched. A `.part` download renamed
  to its completed name sorted successfully. Chunked writes were preserved.
- Identical duplicates retained the incoming copy; different data at the same
  filename sorted under a collision-safe name. Original destinations remained
  byte-identical after collisions.
- A sparse 2,684,354,560-byte video checked size-rule routing and approval in each
  mode. It was **not copied or hashed**; the test confirmed AWAIT_APPROVAL and then
  removed only the generated sparse sample.
- **Full suite: 1,531 passed, 1 existing skip in 34.08 seconds; exit 0.**
  No Python threads, running QThreads, active QTimers or child processes remained.
  Eighteen new regression cases cover extension matching, unit migration/repair,
  preservation of custom rules, persistence/backup, inode reuse and pending-worker
  ownership. The earlier baseline run confirmed six new cases failed before fixes.
- Debian package archive/source parity, root ownership, executable modes, desktop
  validation and extracted system-Python sorting/report smoke checks passed.
  Source parity includes the watcher and both changed rules modules.

## Artifacts and scope

Latest inspectable sample folder: `/home/websrp/Downloads/SmartSort-QA-1795015224287933280`.
Baseline folder: `/home/websrp/Downloads/SmartSort-QA-1795014303279106482`. These contain generated QA samples only.
Detailed outcomes: `build/validation/downloads/before.json`, `after.json`,
`extended.json`, `full-final.log`, `full-result.json`, `liveness.json`.

Package: `build/deb/smartsort_1.2.3_all.deb` (13,670,804 bytes).
SHA-256: `2cb35213ad2eaefad4d0cdb73002b619d23a71742fbf0a388a27032069f16a84`.

The live harness tested the revised source pipeline, not the currently installed
GUI process. The packaged source was verified byte-for-byte. Install 1.2.3 and
restart SmartSort to use these fixes; existing files are not automatically
reorganized by the new-download watcher.

```sh
sudo apt install /home/websrp/SmartSort/build/deb/smartsort_1.2.3_all.deb
```

Community cross-check: [Build a File Sync Tool with Python and Watchdog](https://dev.to/qingluan/build-a-file-sync-tool-with-python-and-watchdog-4db0)
by [@qingluan](https://dev.to/qingluan) notes multiple events while files are being
written and recommends stability checks. Our live write/reuse tests provided the
project-specific evidence; this one article is not a community consensus. The
comments endpoint was unavailable.
