# SmartSort File Intelligence Engine: Directory Organizer Integration

## Implementation status

Phase 13 connects Phases 01–12 to `DirectoryOrganizer.plan()` and `preview()`.
The existing directory worker receives intelligent destinations through its API.
Phase 15 now displays confidence, evidence, clusters and warnings and executes a
frozen reviewed plan after explicit confirmation. Phase 16 preserves that plan’s
confidence, evidence and cluster metadata in every execution record and enriches
the atomic, offline arrangement report with destination and cluster navigation.
See the [Phase 15 implementation notes](phases/phase-15-gui-preview-explanation.md)
and [Phase 16 audit notes](phases/phase-16-arrangement-index-enhancement.md).

## Batch pipeline

1. Validate and canonicalize the selected root; protected-root symlink aliases
   are rejected. Snapshot configured rules for this batch.
2. Revalidate supplied sources as regular, nonexcluded files inside that root.
   Hidden/temp/report/symlink files, unavailable files and external sources are
   skipped with warnings. Canonical duplicates are analyzed only once.
3. Evaluate configured rules first. A matching rule bypasses content, origin,
   signal and cluster analysis. A minimal filesystem context still feeds the
   Phase 12 planner, preserving rule priority, size conditions and full-target
   `{filename}` semantics.
4. For unmatched files, build filesystem contexts without the builder's legacy
   xattr probe. Delegate provenance solely to the configured `OriginDetector`,
   then run the extractor registry and signal extractor. The optional new
   `read_origin_xattrs=False` builder keyword avoids duplicate origin reads and
   ensures `enable_origin_detection=False` is respected. Its default remains
   `True`, preserving other builder callers.
5. Cluster successfully profiled contexts together, before classifying any of
   them. A known inferred cluster root becomes a bounded `CLUSTER_CONTEXT` hint,
   weighted `0.30 × cluster_confidence`, with source `cluster.inferred_domain`.
   These hints do not count as independent file observations in the classifier.
   They are omitted if the existing signal budget is full.
6. Classify each profiled context and generate proposals with the Phase 12
   planner. Failed profiling/classification uses an extension-category fallback;
   unsafe proposals are excluded, not rerouted silently.
7. Recheck source identity after analysis, omit already-organized no-ops and
   return source-sorted plan items and category counts. No transfer is scheduled
   for sources changed during analysis.

All configured rules, including broad default extension rules, are authoritative.
To exercise semantic hierarchies, the selected files must not match such a rule.
Rule edits during analysis apply to the next batch, avoiding mixed policy within
one plan. No new global intelligence toggle or config persistence is introduced.

Phase 15 adds the shared `enable_deep_content_extraction` setting (default true).
When false, this pipeline skips registry dispatch and retains filesystem/MIME,
filename and optional origin signals. The core algorithms are unchanged.

## Failure isolation and fallback

Origin failures retain content/filename classification with unknown provenance.
Extraction `SUCCESS`, `PARTIAL` and `UNSUPPORTED` results can still supply signals;
failed, corrupted, encrypted, timed-out or inaccessible content uses a fixed
extension-category fallback such as `Documents/file.pdf`. This fallback carries
`UNKNOWN` confidence and an explanation, not semantic certainty. Registry,
ingestion, signal or classification exceptions affect only the corresponding
file. Rule evaluation failures exclude the file rather than bypassing policy.

Clustering failure preserves individual classification. Batches exceeding the
relationship engine's 2,000-profile limit skip clustering and retain all
individually plannable files; they are not truncated or split into misleading
independent components. Per-file extractor/signal budgets remain in force.
Phase 13 introduced no persistent cache, global analysis deadline or parallel
extraction pool. Phase 17 now adds persistent metadata/origin caching below these
organizer APIs; see the [cache implementation notes](phases/phase-17-caching-performance.md).

Integration exposed weak directory/extension votes contaminating cluster root
consensus, for example a project inside a folder called `Archives`. Typed
relationship domain aggregation now excludes those channels and inherited hints.
This changes domain consensus only; identity edges and witness scores are intact.
Legacy unweighted relationship inputs retain their previous behavior.

## Plan and preview models

`OrganizePlanItem` retains its four original required fields, followed by defaults:

```python
confidence: str = "CONFIRMED"
evidence: List[str] = field(default_factory=list)
confidence_score: float = 1.0
cluster_id: Optional[str] = None
cluster_name: str = ""
source_identity: Optional[Tuple[int, int, int, int, int]] = None
```

The identity tuple stores device, inode, size, mtime-nanoseconds and
ctime-nanoseconds. Generated plans always include it; older/manual items default
to `None`. Identity checks detect stale plans rather than rereading all source
contents for preview hashes.

`OrganizePlan` and `DirectoryPreviewSummary` append `cluster_count=0` and an
independent `warnings=[]` list. Existing positional constructors remain valid.
`total_files` remains the number of planned moves, and category counts sum to
that number. Cluster count describes detected profiled groups, which may include
members later omitted as no-ops or rejected sources. Warnings distinguish source,
origin, profiling, clustering, classification and planning failures without
copying raw exception text or private browser values.

Preview creates no organized directories, destination files or report in the
selected tree. It does read metadata/content and can update normal access times.
Enabled origin lookup may create and remove private temporary browser-history
snapshots outside that tree. It does not edit live browser databases, config or
source contents. Tests use disabled or mocked origin lookup, never real user
browser profiles.

## Execution boundary

`execute()` validates its root and checks each source/target after progress
callbacks and immediately before destination directory creation. It rejects
out-of-root targets, stale source identities, substituted symlinks, special file
targets and no-op/source-target aliases. Invalid items produce isolated failure
records and preserve their sources. Destination-directory creation errors also
produce per-file failures rather than aborting the batch.

The existing collision, duplicate, copy, size/hash verification, cleanup and
source-delete block is unchanged, as is `FileUtils`. Cancellation and transfer
progress retain their existing loop behavior. Generated plans use canonical
paths; a destination alias changed after planning is rejected rather than
reinterpreted. Planning itself has no new cancellation callback; the existing
worker observes cancellation between its scan/plan/execute stages.

These checks narrow stale-plan exposure but do not provide kernel-enforced
race-free path resolution. Filesystem changes after the final check, mounts,
or source changes during the legacy transfer remain execution assumptions.
This phase does not rewrite that protocol or claim to eliminate all TOCTOU races.

## Validation and performance — 2026-11-18

- Added 46 integration cases covering real course/archive-project batches,
  sparse inheritance, rule short-circuits/snapshots, dry-run tree preservation,
  origin opt-out, failure isolation, exclusions, stale plans, symlink escapes,
  collisions, duplicate preservation, cancellation and headless imports.
- All 28 existing directory-organizer tests pass without modification.
- Full suite: **1,232 passed, 1 skipped**, actual exit code 0.
- Source compilation and whitespace checks pass. A direct comparison confirmed
  the original collision/copy/verify/delete block and `FileUtils` are unchanged.

Local 100-file preview measurements with browser-origin detection disabled and
no persistent cache (historical Phase 13 measurements):

| Fixture | Elapsed seconds | Planned files | Clusters |
| --- | --- | ---: | ---: |
| Markdown intelligence, three runs | 0.0541 / 0.0576 / 0.0526 | 100 | 1 |
| Matched custom policy, three runs | 0.0139 / 0.0157 / 0.0137 | 100 | 0 |
| PDF intelligence, one run | 23.3076 | 100 | 1 |

The Markdown and rule fixtures meet the one-second target; the PDF batch does
not. PDF worker startup/backend parsing remains a known Phase 04 cost. Enabled
history snapshots, larger inputs and slower storage can add latency. These are
local observations, not a universal batch deadline.

Next: **Phase 14 — Download Organizer Integration & Real-Time Profiling**.


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
