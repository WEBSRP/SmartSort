# Verified duplicate source removal — SmartSort 1.2.5

Implemented and verified on 2026-11-19 at the user's request.

## Behavior

With duplicate detection enabled, automatic downloads and folder execution
compare an incoming regular file with its existing planned destination by
SHA-256. If both comparisons match, remove the incoming source copy and retain
the existing destination. DUPLICATE now means a successfully removed duplicate
source, counted separately from ordinary moves. Same-name files with different
content continue through rename/skip/overwrite policy; disabling duplicate
detection retains ordinary collision handling. Previews remain read-only.

Verification rejects same-physical-file/symlink inputs, unavailable hashes,
detected changes during reading, changed planning boundaries and deletion
failures. It checks file identities and content hashes again before removal.
Repeated content reads are necessary because this test filesystem can retain the
same timestamps for very rapid same-size writes. Hashing streams 1 MiB chunks.
These checks reduce ordinary filesystem races; they are not an atomic transaction
with unrelated programs writing the files concurrently.

Read/verification/removal failures report ERROR/FAILED instead of a successful
duplicate action. Existing destinations are never overwritten by deduplication.
The directory copy path also now rejects two unavailable hashes as verification
success, preventing that error condition from authorizing source removal.

Dashboard counters, settings, batch summaries and activity logs say source copies
were removed. Successful duplicate actions no longer trigger a blocking modal.
Arrangement reports link to the retained destination and no longer offer Open
Source for a successfully removed duplicate.

## Validation

- 26 new cases cover empty, small and multi-megabyte matches; same-size different
  bytes; source/target/both hash read failures; final-pass read failures; mutation
  while hashing; deletion denial; symlinks/same-path safety; failed validation;
  and both organizer workflows with disabled detection and filename collisions.
- Full suite: **1,601 passed, 1 existing skip**, natural exit 0. Teardown inventory
  had no Python threads, running QThreads, active QTimers or child processes.
- 80 live cases passed in the contained generated Downloads folder, including
  source deletion on hash-matched duplicates, retained destination integrity,
  safely renamed different-content collisions, file-type routing and partials.
- Extracted Debian package checks with system Python verified source duplicate
  removal in both workflows and the resulting report links, alongside transfer,
  file-type fallback, ownership, script mode, desktop and icon checks.

Evidence: `build/validation/duplicate-removal/`,
`build/validation/downloads/duplicate-removal.json`, and
`build/validation/version-1.2.5/`.

Package: `build/deb/smartsort_1.2.5_all.deb` (13,671,800 bytes).
SHA-256: `b52e7d800c44d39077d940e161dfb350f8b47d680ee9b69401d0ab84eed65c7e`.

Install and restart SmartSort to use the change. No personal duplicates were
bulk-deleted during validation: only generated test copies were removed. This
compares each source to its planned destination; arbitrary filenames and folders
are not globally searched for matching hashes.

```sh
sudo apt install /home/websrp/SmartSort/build/deb/smartsort_1.2.5_all.deb
```
