# Phase 18: Full Integration Testing & Multi-Domain Verification

**Status — 2026-11-18:** Integration verification complete after the cache repair
follow-up; three consecutive full-suite runs pass with no expected failures.
Performance and taxonomy limitations below remain separate from correctness checks.

## Objective
Implement comprehensive end-to-end integration tests in `tests/test_file_intelligence/test_integration.py` verifying multi-domain file intelligence, clustering, provenance resolution, and safe execution across all supported domains.

## Why This Phase Exists
Before packaging and releasing, the complete intelligence pipeline must be verified end-to-end against realistic multi-domain directory structures without external network access or GUI dependencies.

## Inputs
- Synthetic multi-domain directory fixtures.

## Outputs
- `tests/test_file_intelligence/test_integration.py`.
- Certified test execution report.

## Files To Create
- `tests/test_file_intelligence/test_integration.py`

## Files To Modify
- None.

## Existing Components To Reuse
- All `src/core/file_intelligence/` modules and `src/core/directory_organizer.py`.

## APIs / Interfaces
- Executes public `DirectoryOrganizer` and `FileOrganizer` APIs.

## Data Structures
- All `FileContext`, `OrganizePlan`, and `OrganizeResult` structures.

## Algorithms
- Synthetic multi-domain scenario tests:
  1. **Academic Scenario**: `College/` containing `.pdf`, `.pptx`, `.zip` lecture files with mock Canvas origin $\rightarrow$ organized to `College/DBMS/Lectures/` with `CONFIRMED` status.
  2. **Software Project Scenario**: `Projects/` containing `Makefile`, `.py`, `.c`, `.md` source files $\rightarrow$ organized to `Projects/SmartSort/Source/` and `Projects/SmartSort/Documentation/`.
  3. **Cybersecurity Scenario**: `Cybersecurity/` containing `nmap_scan.xml`, `rockyou_subset.txt`, `exploit.py` $\rightarrow$ organized to `Cybersecurity/Reports/`, `Cybersecurity/Wordlists/`, `Cybersecurity/Tools/`.
  4. **Work / Finance Scenario**: `Work/` containing `Invoice_August_2026.pdf` and `Contract.docx` $\rightarrow$ organized to `Work/Invoices/` and `Work/Contracts/`.
  5. **Ambiguous / Generic Scenario**: `random.zip` with zero metadata $\rightarrow$ organized cleanly to `Archives/` or `Others/` with `Confidence.UNKNOWN`.
  6. **Intra-Batch Collision & Duplicate Safety Scenario**: Same filename with matching vs differing SHA-256 hashes $\rightarrow$ verified safe transfer, duplicate preservation, and unique renaming.

## Error Handling
- Verifies that malformed or unreadable files do not abort batch processing of healthy files.

## Security Considerations
- Asserts that all operations remain bounded inside temporary test directories.

## Performance Considerations
- The complete multi-domain integration test suite executes in < 2.0 seconds.

## CI / Headless Requirements
- 100% headless test execution with zero display server dependencies.

## Tests
- `tests/test_file_intelligence/test_integration.py`:
  - `test_academic_course_organization_end_to_end`
  - `test_software_project_organization_end_to_end`
  - `test_cybersecurity_toolkit_organization_end_to_end`
  - `test_work_finance_organization_end_to_end`
  - `test_ambiguous_file_fallback_end_to_end`
  - `test_duplicate_and_collision_intelligence_safety`

## Acceptance Criteria
- [x] All 6 multi-domain end-to-end integration tests pass against the established taxonomy (scenario differences below).
- [x] Existing tests and both cache regressions pass following the repair.
- [x] Three consecutive full-suite runs return exit code 0 with no expected failures (follow-up results below).

## Dependencies
- Standard library and pytest.

## What This Phase MUST NOT Change
- Must NOT modify production code.

## Completion Checklist
- [x] Integration tests implemented.
- [x] Full test suite verified green across 3 consecutive runs after repair.


## Implementation and execution report — 2026-11-18

Added `tests/test_file_intelligence/test_integration.py` with **20 passing cases**
and **two strict expected-failure regression cases**. Fixtures are synthetic and
isolated by function-scoped private XDG/home directories. Network creation is
blocked in the parent test process. Tests use real extractors, classifiers,
SQLite persistence and verified transfers, controlling only machine boundaries
and unreadability injection. No production source was modified.

### Coverage

- The six named scenarios cover real bounded PDF parsing, minimal OOXML PPTX and
  DOCX packages, ZIP directory inspection, Python/C/Markdown, Nmap/wordlists,
  exact destination paths and confidence/evidence/cluster propagation.
- A mixed batch verifies all seven classifier domains together, exact cold/warm
  routing on benign fixtures, source deletion, preserved bytes/SHA-256 hashes,
  and the enriched arrangement report.
- Seven download cases run the public `FileOrganizer.analyze_download()` and
  `process_file()` APIs for College, Projects, Cybersecurity, Work, Media,
  Archives and Others. Analysis is read-only; resulting transfers preserve hashes.
- A synthetic Chromium SQLite history verifies provenance matching, repeated
  cache reuse, redacted URL fields, unchanged browser database bytes and transfer.
- Warm-cache cases verify newly configured rules and deep-content opt-out take
  precedence. Malformed OOXML retains its explicit fallback while healthy files
  move; injected unreadability preserves the source and allows the batch to finish.
- A fresh subprocess rejects Qt imports while running core directory preview.
  The tests require no display server or external services.

### Scenario specification differences

The existing classifier intentionally maps `exploit.py` to
`Cybersecurity/Exploits/`, whereas the original phase example says `Tools/`.
`Tools/` is reserved for signals such as Metasploit/Burp. The scenario asserts
that established exact taxonomy rather than adding a routing rule to force it.

A bare extensionless `Makefile` identifies Projects from filename/origin but has
no dedicated content extractor and does not inherit `SmartSort/Source/`. Its
current exact destination is `Projects/Makefile`. The related explicitly named
Python/C sources and Markdown documentation do inherit
`Projects/SmartSort/{Source,Documentation}/`. This is a remaining feature gap
relative to the broader phase example, not a claim that Makefile extraction works.

### Certification blockers: confirmed cache defects

Both are reproducible with this **synthetic** Markdown input and origin disabled:

```text
# https://example.com/a?invoice=UncommonPrivateToken987
repository backend frontend source code
```

1. **Unchanged-file routing changes between cold and cached preview.** Cold
   extraction returns unsanitized metadata while the cache redacts only the stored
   copy. This input first routes to `Work/Invoices/opaque.md` with UNCERTAIN
   confidence, then to `Projects/Source/opaque.md` with PROBABLE confidence. The
   regression asserts equality of the complete preview, including evidence.
2. **URL-derived private tokens persist in keywords.** Redacting complete URLs
   does not remove `uncommonprivatetoken` already derived into metadata keywords.
   The regression reads the actual stored JSON and requires that token to be absent.

The two tests use `xfail(strict=True)` so the known defects stay visible and a
future repair cannot silently leave obsolete expected-failure markers. Running
with `--runxfail` produces **2 failed, 20 deselected**, actual exit code **1**, at
the intended equality/privacy assertions. They are **not** certification passes.
This phase's explicit “Must NOT modify production code” boundary is preserved.
Cache consistency/privacy must be repaired and these markers removed before
certifying Phase 18 or proceeding to packaging.

### Validation

- Baseline: **1,387 passed, 1 skipped**, actual exit code 0.
- Focused integration: **20 passed, 2 xfailed** in **2.30 s**. The two-second
  target was not met in this run while a full suite was also running; the earlier
  20-case run without the regression cases took 1.55 s. No timing guarantee is made.
- Three consecutive full runs each returned actual exit code **0**:

  | Run | Passed | Skipped | Known expected failures | Pytest duration |
  | --- | ---: | ---: | ---: | ---: |
  | 1 | 1,407 | 1 | 2 | 24.47 s |
  | 2 | 1,407 | 1 | 2 | 28.13 s |
  | 3 | 1,407 | 1 | 2 | 28.48 s |

  The runner preserves the actual `pytest.main()` return code despite the existing
  Qt teardown's forced exit-zero backstop. These exits do not turn the two known
  failures into passing contracts. Their separate unmarked run returned exit **1**.
- Production source SHA-256 hashes match the pre-phase snapshot; full source/test
  compilation, Qt-free core subprocess execution and whitespace checks pass.
- Earlier performance limits remain: large metadata lookup exceeds 0.05 ms,
  cold 100-PDF preview exceeds ten seconds, and report generation exceeds 2 ms.
  No performance or release certification is implied by passing test counts.


## Follow-up repair and certification result

The initial report above records the defects as originally found. A subsequent
repair normalizes fresh/cached metadata consistently, filters URLs before keyword
derivation and property splitting, and invalidates legacy schema-1 cache rows.
The two strict expected-failure markers were removed; those contracts now pass.
The test-only Phase 18 implementation is unchanged in scope; the prerequisite
cache production repair is recorded separately in the Phase 17 follow-up notes.

Added 36 privacy cases covering raw/percent-encoded URL components, values beyond
visible previews, PDF/Office/code, unavailable/disabled caches, bounded workers,
status preservation, legacy invalidation, Markdown links and immutable/idempotent
normalization. Sources and transfer paths remain unchanged.

Three fresh full-suite runs, preserving actual pytest exit codes:

| Run | Result | Exit code | Pytest duration |
| --- | --- | ---: | ---: |
| 1 | 1,445 passed, 1 skipped | 0 | 30.09 s |
| 2 | 1,445 passed, 1 skipped | 0 | 26.61 s |
| 3 | 1,445 passed, 1 skipped | 0 | 30.37 s |

There are **no expected failures**. Logs and return-code records are retained
locally under `build/validation/cache-repair/`. Compilation and whitespace checks
pass. The earlier performance limits and Makefile/taxonomy differences remain
explicitly documented; this correctness verification is not Phase 20 release
certification. Phase 19 packaging may now proceed.


Phase 20 subsequently removed the test fixture's unconditional exit-zero backstop,
added real pass/fail exit canaries and repeated the full validation with natural
process shutdown. See the final implementation report for current CI evidence.
