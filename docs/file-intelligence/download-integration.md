# SmartSort File Intelligence Engine: Download Organizer Integration

## Implementation status

Phase 14 integrates file intelligence into `FileOrganizer` without changing
`src/monitor.py`, watchdog handling, GUI workers or `FileUtils.safe_copy()`.
The existing file worker calls the synchronous `process_file()` API off the GUI
thread. Direct callers of analysis/category APIs must also arrange background
execution if they need a responsive UI; these methods do not start GUI threads.

`analyze_download(file_path, override_filename=None)` returns a read-only
`OrganizationProposal`. `get_category()` and `get_destination_path()` retain their
public APIs and use the same analysis for unmatched existing files. The legacy
`category` destination argument remains accepted and does not override policy.
Missing-file category lookups retain the old rule-or-`Others` behavior.

## Processing and rule precedence

1. Validate a regular, non-symlink source and capture device, inode, size, mtime
   and ctime. Reserve the physical identity for the duration of this call.
2. Snapshot rules and the canonical destination base. Evaluate the existing
   filename-cleanup component, if enabled, to obtain a target-only override.
3. Check configured rules first. Matching rules bypass metadata, content and
   history profiling; every configured rule, including broad default extension
   rules, remains authoritative. The existing engine retains priority, condition
   and variable-expansion behavior.
4. For unmatched files, build the filesystem context with
   `read_origin_xattrs=False`, delegate origin to the configured detector, extract
   content in the bounded child process, then run signals and classification.
   This single-download path does not scan siblings or invent batch clusters.
5. Plan inside `destination_base` using the Phase 12 planner. Failed profiling
   uses a fixed extension-category fallback with `UNKNOWN` confidence and zero
   score. Unknown semantic matches also use the shared file-type fallback; only
   unrecognized formats go to `Others` (1.2.4).
6. Recheck source identity and target containment. Check the large-video approval
   threshold, then serialize collision/copy decisions within this organizer
   instance and call the existing safe-copy/delete protocol.
7. Notify only after successful copy verification and source deletion. Notification
   errors do not turn a completed move into a failed transfer.

A thread-local, per-`process_file()` request shares one proposal between the
existing category/destination hooks. It is cleared on every return/error and is
not a persistent filename cache. Separate workers have independent request
state. Rule edits affect the next request; a later file reusing an old path is
profiled again. Phase 17 allows unchanged successful extraction to be reused from
the identity-keyed persistent cache; classification and policy evaluation still
run for each new request. Concurrent calls for the same physical download return `SKIPPED`
while the first is active. Parsing can run concurrently, while collision/transfer
selection is serialized per organizer instance so competing same-name downloads
can use the existing rename/duplicate policy safely.

## Filenames and provenance

The source path/basename stays original for rule conditions, history matching,
content extraction and classification. The new optional
`OrganizationPlanner.plan_file(..., override_filename=...)` changes only the target
filename, preserving source-basename validation. Full-file `{filename}` templates
substitute the override at actual placeholder positions; identical literal folder
names are not accidentally rewritten. `{extension}` still comes from the source.

Overrides must be valid bounded filename components. Invalid names, traversal,
absolute escapes, controls, invalid target types and symlink escapes are rejected.
Canonical root selection, internal aliases and containment follow the Phase 12
contract. Configured origin opt-out prevents the profiling pipeline from probing
xattrs/history. Independently enabled legacy filename cleanup can still inspect
its own source-website xattrs, as before.

Origin errors preserve content/filename classification with unknown provenance.
Ingestion, extraction, signal and classifier failures fall back without copying
raw exception strings, parser diagnostics or private URLs into evidence. Typed
`SUCCESS`, `PARTIAL` and `UNSUPPORTED` extraction results remain usable; timeout,
corruption, encryption and other failures produce the fallback proposal. A changed
source is rejected rather than moved under a stale classification.

## Enforced extraction boundary

Phase 15 adds the shared `enable_deep_content_extraction` setting (default true),
available in the GUI's File intelligence preferences. When false, download
profiling skips registry dispatch and classifies filesystem/filename plus optional
origin evidence. MIME inspection and independently enabled filename cleanup
retain their previous behavior. Configured rules still take priority.

`ExtractorRegistry.extract_metadata(path, timeout_seconds=2.0)` selects a new
Linux child-process path in `extractors/isolated.py`. The default no-timeout call
retains existing dispatch behavior, including custom registry instances and the
Phase 13 directory pipeline. Bounded dispatch instantiates the built-in registry
in a clean interpreter; runtime-registered custom extractor instances are not
serialized into that interpreter.

The parent enforces a maximum two-second extraction deadline, including waiting
for one of two process slots. It uses bounded pipe reads, accepts at most 1 MiB
of JSON, and kills/reaps the process group on timeout, invalid output, overflow
or failure. There is no thread left parsing after a timeout and no persistent
process pool. The child applies 512 MiB address-space and CPU limits, preserves
existing per-format byte/metadata bounds, and suppresses parser diagnostics.
PDF parsing reuses the existing bounded parser directly inside this worker to
avoid a second nested interpreter.

This deadline bounds extraction work, not every stage of the operation. Origin
lookup has its own cooperative budget; filesystem metadata queries, legacy
filename cleanup, OS process scheduling/cleanup, transfer size and notifications
can add time. It is not a whole-download two-second or 50 ms guarantee, nor an
OS sandbox against arbitrary code. Source contents are never executed.

## Approval and execution safeguards

Large-video approval checks still return `AWAIT_APPROVAL` before any destination
is created or source removed. Both legacy GB thresholds and byte thresholds are
preserved. Known video extensions (including 3GP), detected video MIME types and
legacy `Videos` categories trigger this check, so a semantic `Media`, `College`
or custom rule label cannot bypass it. Approved retries run fresh analysis.

Before copying and again before deleting, the organizer validates the captured
source identity, canonical destination base and target. Same-source/target and
hard-link aliases are no-ops. Configuration/base changes, replaced sources and
current escaping symlinks fail without deleting the source. On failed copies,
changed sources after copying, delete failures or unsafe paths, the original
remains available. Existing duplicates and collisions retain rename/overwrite/
skip behavior; overwrite is still an explicit configured policy.

These checks narrow stale-plan exposure but do not make the existing path-based
transfer kernel-atomic. Other processes/organizer instances, concurrent mounts
or filesystem changes after the last check remain race assumptions. This phase
adds no persistent dedup state, watcher changes or new review GUI.

## Verification and performance — 2026-11-18

- Baseline: **1,232 passed, 1 skipped**.
- Added **48 download integration cases** covering real PDF/LMS and archive/GitHub
  routing, target-only cleanup, rule priority/snapshots, fallbacks, origin settings,
  video approval, copy/notification failures, source/path changes, concurrent
  downloads, process timeout/reaping/output bounds, and Qt-free imports.
- Full suite: **1,280 passed, 1 skipped** in 20.12 s, preserved pytest exit code 0.
- Existing download/duplicate/cleanup/notification regressions pass unchanged.
- Source compilation and whitespace checks pass. Hash comparisons confirm
  `src/monitor.py` and `FileUtils` are unchanged.

Local end-to-end `process_file()` timings (three small files per case, in ms),
including analysis, verified copy and source removal, with desktop notifications
and real browser-history lookups disabled. PDF/ZIP provenance was simulated:

| Fixture | Run 1 | Run 2 | Run 3 |
| --- | ---: | ---: | ---: |
| Markdown invoice | 89.968 | 98.129 | 92.236 |
| Academic PDF | 165.327 | 164.605 | 165.350 |
| GitHub ZIP | 98.992 | 95.232 | 98.934 |
| Matched configured rule | 0.613 | 0.499 | 0.483 |

The **50 ms universal target remains outstanding**. Interpreter/parser startup
is visible even for small unmatched text files; matched-rule fast paths meet the
target on these fixtures. Large copies and real history snapshots add latency.
The enforced extraction deadline is retained rather than replacing it with an
uncancellable background thread to reduce startup cost.

Next: **Phase 15 — GUI Preview, Evidence Display, & Review Workflow**.


## Sorting mode (1.2.1)

`sorting_mode` is either `rules_first` (default/legacy behavior) or `intelligence`
(explicitly bypass configured routing rules). Saved RuleManager entries are never
deleted or disabled by changing modes. Intelligence classification, confidence,
unknown/extension fallbacks and transfer checks otherwise retain their contracts.
The rule precedence described above applies in Rules first mode.

Each directory plan/download request snapshots its selected policy. The GUI shows
the saved mode on Dashboard and Organize folder and exposes the selector in
Settings → File intelligence. Mode changes invalidate reviewed folder plans; a
queued preview retains its selected mode/rules. A separate running daemon loads
configuration at startup and must be restarted to consume saved changes.

## Duplicate source removal (1.2.5)

With `enable_duplicate_detection` enabled, an incoming file whose SHA-256 matches
its existing planned destination is removed after verification; the destination
is retained. Both regular files are hashed again before deletion, with identity
and boundary checks. Read errors, detected changes or deletion failures report
an error instead of a successful duplicate removal. Different hashes continue
through the configured collision policy. Disabling detection retains normal
collision handling. This compares a source with its planned destination; it does
not scan arbitrary filenames or delete unrelated duplicates elsewhere. Preview
remains read-only; removal occurs only during execution. Dashboard counters and
arrangement links describe the retained destination and removed source copy.

## Recursive Content intelligence (1.2.6)

Content intelligence now includes subfolders by default. `intelligence_recursive`
controls folder scans/previews when no explicit recursive argument is supplied;
the Organize folder checkbox saves that preference. The existing
`dir_organizer_recursive` preference remains independent for Rules first mode.
Explicit `recursive=False` still requests a top-level scan. Proposed destinations
remain beneath the selected root, using content hierarchy or known-type fallback.
Already-correct destinations are omitted; previews remain read-only.

`downloads_recursive` controls nested automatic Downloads monitoring in Content
intelligence mode. Its default is true; the Settings checkbox can disable it.
Rules first monitoring retains top-level behavior. Saving a changed scope restarts
the GUI watcher; a separately running daemon/service needs restarting to reload
settings. Monitoring handles newly arriving/changed files, including populated
directories moved into the tree; it does not sort all existing files on startup.
Use Organize folder and review a recursive preview for an existing tree.

Hidden/temporary paths and symlinked files/ancestors are excluded. A bounded
process-local record of recent organizer outputs suppresses unchanged self-written
files, including outputs from folder batches running alongside the watcher.
Later edits invalidate the record and can be processed normally.

## Keep application/project bundles intact (1.2.7)

Recursive sorting now prunes recognizable application bundles and project folders
instead of treating their internal logos, resources, libraries or sources as
independent downloads. Such folders are left in place as a whole; their contents
are not proposed for individual movement. Ordinary mixed-file folders still
participate in recursive sorting.

Recognition includes `.app`/`.AppDir` directories, AppRun layouts, Electron
`resources/app.asar`, common project manifests and portable executable/resource
layouts. Detection reads bounded directory names and, where needed, four-byte
executable headers; it does not execute the app or inspect image contents.

For a custom/unrecognized bundle, place an empty `.smartsort-ignore` file inside
its folder. That folder and its contents are then excluded. The same protection
applies to folder scans, manually supplied plan inputs, queued watcher events and
execution revalidation, so adding a marker invalidates an older unsafe proposal.
An application still being extracted can emit early events; queued files are
checked again before processing. If assets arrive and are processed before any
recognizable bundle structure exists, automatic recognition cannot infer future
files; create the ignore marker first or extract into a marked folder.

This prevents subsequent asset moves. It does not reconstruct applications whose
files were separated by an earlier release.

## Loose code and complete projects (1.2.9)

Standalone source files now receive fixed language folders. A filename-only
`fix_click.sh` test yields `Code/Shell/fix_click.sh`; Python, JavaScript,
TypeScript, C/C++, Java, Rust, Go and other recognized suffixes have analogous
folders. This identifies a source type without claiming to know the script's
purpose. File-type-only tester results say the type is recognized while content
confidence remains UNKNOWN. Use Existing file to inspect actual code metadata.

When actual source metadata classifies a loose file as `Projects/Source`, its
language is appended, e.g. `Projects/Source/Python/helper.py`. Explicitly named
project hierarchies, custom rules and strong academic/other semantic routes
retain precedence. Language folder names come from a fixed vocabulary; arbitrary
metadata strings cannot become path components. No source code is executed.

Projects remain intact. Common Python/build/package markers now include
requirements.txt, setup.py/setup.cfg, __init__.py, Makefile, Dockerfile and the
previous project manifests. Selecting a project's src/assets subfolder or
selecting an internal file in the tester does not bypass a detected enclosing
project boundary. Parent detection is bounded and stops at home, system and
common collection roots. Recognition remains heuristic: put an empty
`.smartsort-ignore` in any custom project that lacks a recognized structure.
