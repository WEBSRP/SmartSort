# SmartSort 1.2.1: sorting-mode visibility and behavior

## Cause

The installed 1.2.0 files matched the new package. Broad enabled legacy rules such
as Documents and Archives still matched first, intentionally bypassing semantic
profiling. This hid the new sorting behavior for most common files.

A read-only synthetic lecture preview using the saved rules produced
`Documents/College/Lecture_DBMS.md`; content intelligence produced
`College/DBMS/Lectures/Lecture_DBMS.md`. Personal configuration was not modified
and no user files were moved during diagnosis.

## Change

- Settings → File intelligence now exposes Rules first / Content intelligence.
- The default preserves existing policy. The explicit intelligence choice profiles
  files without applying stored routing rules; saved rules remain intact.
- Dashboard and Organize folder show the current saved mode and a Change mode
  shortcut. Configured rules are marked Not applied in intelligence mode.
- Selection takes effect after Save settings, for new requests/previews. The UI
  explains that a separately running background service needs Restart to reload.
- Reviewed plans are invalidated on mode changes. Queued previews and active
  download requests retain their selected mode/policy snapshot.
- Transfer functions and their safety checks are unchanged (AST comparisons).

## Verification

- 29 new backend/config cases and five GUI cases; focused run **90 passed**.
- Final GUI run, including service-reload guidance: **61 passed** in 5.79 s.
- Final full suite: **1,481 passed, 1 skipped** in 32.54 s, actual exit **0**.
- Final inventories: no remaining Python threads, running QThreads, active QTimers
  or child processes. Compilation and whitespace checks pass.
- Minimum-size (860×620) Dashboard, folder and Settings captures were inspected
  in light/dark themes; controls remain reachable with native scrolling.
- An initial full-run command had a missing temporary parent directory. That
  harness setup error was corrected. A subsequent interrupted attempt was not
  counted; the bounded verbose final run above completed normally.

## Package

`build/deb/smartsort_1.2.1_all.deb`, 13,667,148 bytes.
SHA-256: `ace7f9608b2e5d4595d82f2653cf7572dfe6a0e887096e40a0daef833ec6d90e`.

App/control versions match 1.2.1. Archive source checks include the new GUI,
configuration and both organizers, as well as all intelligence modules. Root
ownership, executable scripts, bytecode/icon exclusions, desktop validation and
system-Python extracted-package smoke checks pass. The smoke test confirms an
identical input routes through the saved broad rule in Rules first and through
intelligence when explicitly selected, then verifies transfer/report generation.

No installed application/configuration/service was modified automatically. After
installing, fully exit/reopen SmartSort, choose Content intelligence and save.
Restart a running separate Background Monitoring service. Synthetic preview files
are available locally at `build/smartsort-1.2-demo/`.

This patch does not resolve the earlier hosted-CI or performance certification
limits documented in the final implementation report.
