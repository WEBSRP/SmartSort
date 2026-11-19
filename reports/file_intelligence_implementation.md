# SmartSort File Intelligence: Final Implementation and Validation Report

Date: 2026-11-18  
Artifact: `smartsort_1.1.6+intelligence.20261118.1_all.deb`  
Base application version: 1.1.6

Latest numbered build: **1.2.1**, packaged after the validation above. See the
versioned-build appendix below; the original Phase 20 measurements describe the
prior feature preview.

## Decision

**Local validation passed. Public production-release certification remains
conditional.** The intelligence implementation and Debian preview passed the
checks below. The exact hosted Ubuntu/Python 3.12 workflow has not been run for
this uncommitted working tree, and documented performance targets remain unmet.
No release tag, push, publication, package installation or service activation was
performed. This report does not describe a published 1.2.0 release.

Phase 20 changed test infrastructure and documentation only. Production source
hashes were captured before validation and compared afterward with no changes.
The package contains the production cache/privacy repairs verified in Phase 18.

## What is implemented

- Filesystem/MIME context plus bounded text/Markdown, PDF, Office/OpenDocument,
  image/media, source-code and archive-table inspection.
- Local xattr/browser-history provenance, normalized signals, inspectable
  relationships, domain classification, confidence estimates and hierarchy plans.
- Directory and download integration with configured-rule precedence and the
  existing copy/verify/delete transfer protocol.
- Native light/dark GUI review with confidence, evidence, cluster and warning
  details, followed by execution of the reviewed snapshot.
- Arrangement reports with destination/cluster navigation and safe local links.
- Private XDG SQLite caching with identity/provenance invalidation and uniform
  privacy normalization before feature derivation and persistence.

Confidence estimates are heuristic scores, not calibrated probabilities. A
confirmed configured rule describes policy adherence, not semantic certainty.

## Final test execution

Compilation: `python3 -m compileall src main.py` passed; bytecode was redirected
to a temporary cache prefix. `git diff --check` passed.

| Stage | Pytest result | Actual exit | Process elapsed |
| --- | --- | ---: | ---: |
| intelligence | 1242 passed, 1 skipped in 13.31s | 0 | 13.69 s |
| full1 | 1447 passed, 1 skipped in 24.56s | 0 | 25.08 s |
| full2 | 1447 passed, 1 skipped in 29.59s | 0 | 30.03 s |
| full3 | 1447 passed, 1 skipped in 28.98s | 0 | 29.44 s |

There were **no expected failures**. The existing skip is the filesystem
permission/stat test: successful `stat()` does not demonstrate content-read
permission, so this skip is not evidence of real permission-denial coverage.
Separate injected unreadability integration tests verify source preservation.

Each stage ran in fresh private XDG directories under `QT_QPA_PLATFORM=offscreen`
and `PYTHONUNBUFFERED=1`, with a 180-second external timeout. Full run 1 used the
workflow-style `xvfb-run -a python -m pytest -vv -s --durations=20
--durations-min=1 tests/` command. A validation-only `liveness` pytest plugin was
added to record final state and fail on observed leftover work. Runs 2 and 3
used the ordinary quiet pytest CLI without DISPLAY/WAYLAND_DISPLAY.

### Failure propagation and shutdown repair

The old Qt fixture registered `atexit.register(os._exit, 0)`. A controlled failing
Qt test reported failure but its process returned zero, which could falsely pass
the existing Actions command even with shell `pipefail`. That workaround also
could not establish that threads were cleaned up.

`tests/conftest.py` now retains the existing Qt event draining and permits normal
pytest/Python termination. `tests/test_ci_exit.py` adds two real subprocess
canaries using that fixture: a passing case must exit **0**, and a deliberately
failing case must exit **1**. Both passed. No forced-exit runner was used for the
final certification runs.

A separate natural-shutdown diagnostic also completed successfully. At the end
of each final stage, inventories showed:

| Observation | Result |
| --- | --- |
| Non-main Python threads | 0 |
| Tracked running QThreads | 0 |
| Tracked active QTimers | 0 |
| Child processes reported by Linux task child lists | 0 |
| Timeout terminations in final sequence | 0 |

The Qt inventory examines live Python wrappers discovered by garbage collection;
it is not a count of every internal Qt/native resource. These are observed end-of-
suite states, not a universal guarantee against future hangs or leaks.

The first sandboxed Xvfb attempt returned **1** despite all tests passing because
the virtual X server could not bind local display sockets. Validation halted as
required. After approval to run outside that restriction, the complete final
sequence above passed, including Xvfb. The failed infrastructure attempt is
retained separately rather than counted as a successful run.

## Environment and CI equivalence

Local validation: Debian 13, Python 3.13.5. Installed pinned core dependencies
match `requirements.txt`: pytest 8.2.2, PyQt6 6.7.0, watchdog 4.0.1 and notify2
0.3.1. Local extractor backends: pypdf 6.15.0, Pillow 11.1.0 and mutagen 1.47.0.

The checked-in workflow uses `ubuntu-latest`, `actions/setup-python` with Python
3.12, and installs `requirements.txt` plus typeguard. Those requirements omit the
optional extractor backends now required by the Debian package. Tests include
fallback/import-isolation cases, but this local run is not proof of a clean hosted
job with its different OS, interpreter and dependency set. No matching Ubuntu
image or Python 3.12 interpreter was available locally; no remote run was started.

The existing workflow's command now receives truthful pytest status because the
fixture no longer overrides it. Hosted CI against the eventual release commit
remains a release gate. The moving `ubuntu-latest` image is not certified by this
local observation.

## Domain and safety verification

| Scenario | Verified routing/behavior |
| --- | --- |
| Academic PDF/PPTX/ZIP with synthetic Canvas origin | College/DBMS/Lectures, evidence and clusters |
| Named Python/C project sources and Markdown | Projects/SmartSort/Source and Documentation |
| Bare Makefile | Projects/Makefile; automatic project/role inference remains limited |
| Nmap, wordlist, exploit | Cybersecurity/Reports, Wordlists, Exploits |
| Invoice and contract | Work/Invoices and Contracts |
| Audio, named archive, generic input | Media/Audio, Archives, Others |
| Mixed-domain batch | Exact paths and unchanged cold/warm reviews on regression fixtures |
| Duplicate and collision | SHA-256 preservation, preserved duplicate source, unique renamed target |
| Malformed/unreadable input | Explicit fallback or per-file failure without aborting healthy files |
| Stale sources and unsafe paths | Rejection before transfer; source preservation |

All **25** intelligence modules pass a static no-Qt-import check. The integration
suite also blocks Qt imports in a fresh core-only subprocess. No cloud or network
service is required by the intelligence pipeline.

URL credentials, queries, fragments and matrix/session parameters are filtered
before keyword derivation; cache hits, misses and disabled/unavailable caches use
the same metadata normalization. GPS fields are excluded by the EXIF allowlist.
Both previously expected cache failures are now ordinary passing tests. Legacy
schema-1 records are logically invalidated, without claiming forensic erasure of
old database/WAL pages or backups. Arbitrary secrets in ordinary prose or filenames
are outside the URL/EXIF filter's scope.

## Rebuilt Debian artifact

- File: `build/deb/smartsort_1.1.6+intelligence.20261118.1_all.deb`
- Size: **13,665,952 bytes**.
- SHA-256: `fdb02245eca3494fa5c96cc9173cb71047182660b4aba30296dfd384d469bdb2`.
- Build exit: **0**, elapsed **5.066 s**.
- Every packaged intelligence Python module matches current source byte-for-byte.
- Control/data archives use root ownership; wrapper and maintainer scripts are
  0755. Required extractor dependencies and suggested Office SDKs are declared.
- Shared hicolor directories contain only SmartSort-owned icons, without claiming
  the system `index.theme` or icon cache. Bytecode is excluded.
- Desktop validation and shell syntax checks pass.
- The extracted application passes a `/usr/bin/python3` smoke test importing its
  GUI/backends, matching cold/warm plans, verified transfer and report generation.
- The SHA-256 sidecar is refreshed. No package was installed and no maintainer
  script or user service was executed. Phase 19's apt simulation established local
  dependency resolution, not a clean-distribution installation matrix.

## Outstanding targets and release gates

| Gate/target | Evidence or remaining work |
| --- | --- |
| Exact hosted Ubuntu/Python 3.12 CI | Pending against a committed release candidate |
| Whole suite under 1.5 seconds | Not met: final full suites took roughly 25–30 seconds |
| Cold 100-PDF preview under ten seconds | Earlier measured 17.9–21.4 seconds; repeat-cache scans improved to about 54 ms |
| Large metadata cache lookup under 0.05 ms | Earlier 64 KB record median about 0.20 ms |
| 500-record report under 2 ms | Earlier median about 29.6 ms |
| Download and GUI tail-latency targets | Earlier limits remain documented in their phase reports |
| Debian build under five seconds | Current 5.066 seconds; not a portable bound |
| Formal release version/changelog/tag/publication | Not performed; this remains a local feature preview |

PDF has no OCR; Office/media deadlines remain cooperative. The original Makefile
inference and cybersecurity example/taxonomy differences remain documented.
Performance figures above are historical fixture observations except the final
suite/build measurements. No new production-performance benchmark is claimed.

## Evidence and completion status

Local evidence is retained under `build/validation/phase20/`: compilation/test
results, shutdown inventories, controlled exit canaries, environment/source hash
records, sanitized logs, and package checks. Shared reports/logs use relative or
redacted local paths and only synthetic test data. No credentials were printed or
included in this report.

**Completed:** implementation verification, truthful headless CI exit handling,
three consecutive local full-suite passes, package rebuild/audit and this report.

**Not certified by this report:** exact hosted CI, unmet latency thresholds, a
clean-distribution installation matrix, or a published production release. Those
gates must be passed or explicitly accepted before unconditional release sign-off.


## Versioned build: 1.2.0

At the user's request, application and Debian control versions are now **1.2.0**,
with a matching changelog and updated installation/build references. Functional
production logic is unchanged by this numbering step. The package is assembled
from the latest local source, rather than renaming the previous archive.

- Artifact: `build/deb/smartsort_1.2.0_all.deb` (13,666,108 bytes).
- SHA-256: `5a6298b167b30570b5c51c4da8b9d7d347055f23a4b1c05a86cad3d9d694afb1`.
- Build completed with exit 0 in 4.781 s.
- The real packaging test plus both CLI exit canaries: **3 passed** in 5.55 s.
- Package/application version equality, source contents, ownership, script modes,
  desktop metadata, local links, cache consistency and verified transfer/report
  smoke checks passed against the extracted package using system Python.
- A SHA-256 sidecar is retained beside the package. This local numbered build does
  not imply a Git tag, remote upload, actual installation or hosted CI completion.


## Sorting-mode follow-up: 1.2.1

User testing revealed that broad legacy rules hid semantic sorting. Version 1.2.1
adds an explicit saved Rules first / Content intelligence selector, visible mode
summaries and request/preview policy binding. Rules and transfer safety remain
preserved. Full suite: **1,481 passed, 1 skipped**, exit 0; package and extracted
mode-routing smoke checks pass. See [the sorting-mode report](sorting_mode_1.2.1.md)
for the exact artifact/checksum, validation and activation instructions.
