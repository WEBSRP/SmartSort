# Recursive Content intelligence — SmartSort 1.2.6

Implemented 2026-11-19. The user explicitly selected both automatic Downloads
monitoring and Organize folder for recursive sorting.

## Behavior

- Content intelligence folder scans/previews include nested files by default.
  The Include subfolders checkbox saves a separate `intelligence_recursive`
  preference. Explicit `recursive=False` remains available to backend callers.
- Content intelligence monitors new/changed files in Downloads subfolders by
  default, controlled independently by `downloads_recursive` in Settings.
  Populated folders moved into the watched tree are also discovered.
- Rules first retains its existing top-level watcher and independent
  `dir_organizer_recursive` folder preference. Switching modes restores the
  appropriate folder checkbox state.
- Changing the saved watch scope stops/restarts the GUI monitor. A separate
  background service/daemon must be restarted to reload changed settings.
- Hidden and temporary files/directories, symlinked files/ancestors, arrangement
  reports and paths outside the watched root are excluded.
- Unchanged recent files written by either organizer are suppressed by a shared
  process-local output registry, including batch outputs observed by the live
  watcher. This prevents immediate feedback that could erase a batch hierarchy.
  The registry holds at most 2,048 entries for five minutes; changed identities
  invalidate entries so later edits can be sorted again.
- Files already at their proposed destination are omitted from folder plans;
  repeating a preview does not create nested category folders.

Automatic monitoring reacts to events; it does not silently sort existing trees
on launch. Use Organize folder with Include subfolders, Preview, then Review moves
for existing files. Outputs are organized beneath the selected root using the
intelligent hierarchy and file-type fallback. Empty input folders are retained.

## Validation

Full suite: **1,614 passed, 1 existing skip in 48.01 seconds**, natural exit 0.
No Python threads, running QThreads, active QTimers or child processes remained.
Thirteen new cases cover nested discovery/exclusions, explicit non-recursive
preferences, nested duplicates and stable second previews, watch scheduling,
live self-output suppression and later edits, populated-folder moves, unsafe
paths, output invalidation, per-mode GUI preferences and live watcher restart.
Focused recursive + GUI suite: 74 passed.

Real contained Downloads test: `/home/websrp/Downloads/SmartSort-Recursive-QA-1795061105386873059`.
The recursive batch found three nested inputs, moved two unique files and removed
one verified duplicate source. A second preview proposed zero moves. The live
watcher then sorted three nested inputs (text, real generated MP4 and invoice),
with zero callbacks caused by the batch's or watcher's own outputs. Byte integrity
passed; hidden/incomplete samples remained in place. Existing personal files
were not used as test inputs.

Package checks passed for production source parity, ownership, executable modes,
desktop entry and icon safety. Extracted system-Python smoke checks additionally
verify recursive scan defaults, successful nested movement, an empty second
preview, recursive watcher configuration and the packaged output tracker.
Prior file-type fallback and duplicate-removal smoke checks also passed.

Evidence: `build/validation/recursive/` and `build/validation/version-1.2.6/`.
Package: `build/deb/smartsort_1.2.6_all.deb` (13,672,708 bytes).
SHA-256: `a804f8c180c5b2af1fef6fdbd71c1fbea2d29d71e5b22f9c66722c9d55de7fa2`.

## Installation

This package has been built and checked, but not installed automatically. Install
and fully restart SmartSort; keep Content intelligence selected.

```sh
sudo apt install /home/websrp/SmartSort/build/deb/smartsort_1.2.6_all.deb
```
