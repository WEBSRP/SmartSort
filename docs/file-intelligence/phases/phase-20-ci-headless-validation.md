# Phase 20: Headless CI Validation & Release Certification

**Status — 2026-11-18:** Local validation and audit report complete. Unconditional
production-release certification remains pending hosted CI and documented targets.

## Objective
Execute the full continuous integration validation pipeline under headless conditions, verify zero CI hang regressions across repeated test runs, compile the Debian release package, and create the final certification report.

## Why This Phase Exists
SmartSort mandates an absolute guarantee against headless CI hangs and test flakiness. This final phase validates the complete system against the exact GitHub Actions execution environment prior to tag release.

## Inputs
- Fully implemented SmartSort File Intelligence Engine codebase.

## Outputs
- Clean CI test logs.
- Certified release report: `reports/file_intelligence_implementation.md`.

## Files To Create
- `reports/file_intelligence_implementation.md`

## Files To Modify
- None.

## Existing Components To Reuse
- `.github/workflows/ci.yml`, `packaging/debian/build_deb.sh`.

## APIs / Interfaces
- Complete application test suite.

## Data Structures
- Final test summary and confidence matrices.

## Algorithms
- **Continuous Integration Validation Sequence**:
  1. Python bytecode compilation: `python3 -m compileall src main.py`.
  2. Dedicated File Intelligence test run: `QT_QPA_PLATFORM=offscreen python3 -m pytest -q tests/test_file_intelligence/`.
  3. Full test suite Run 1: `QT_QPA_PLATFORM=offscreen PYTHONUNBUFFERED=1 python3 -m pytest -q tests/`.
  4. Full test suite Run 2: `QT_QPA_PLATFORM=offscreen PYTHONUNBUFFERED=1 python3 -m pytest -q tests/`.
  5. Full test suite Run 3: `QT_QPA_PLATFORM=offscreen PYTHONUNBUFFERED=1 python3 -m pytest -q tests/`.
  6. Debian package build: `./packaging/debian/build_deb.sh`.
  7. Audit package integrity and metadata: `dpkg-deb --info` and `dpkg-deb --contents`.

## Error Handling
- Any failed test, timeout, or non-zero exit code immediately halts certification.

## Security Considerations
- Ensure no test logs contain sensitive user paths or tokens.

## Performance Considerations
- Full suite execution completes in under 1.5 seconds.

## CI / Headless Requirements
- Complete validation runs with `QT_QPA_PLATFORM=offscreen` without requiring an active X11 display.

## Tests
- All test files under `tests/` and `tests/test_file_intelligence/`.

## Acceptance Criteria
- [x] Three consecutive local full-suite runs pass with exit code 0 and no expected failures (one existing skip).
- [x] No outstanding Python workers, tracked Qt workers/timers or child processes detected in final local inventories.
- [x] Debian package compiles cleanly and passes content/system-Python smoke checks.
- [x] Final report `reports/file_intelligence_implementation.md` generated with explicit certification limits.

## Dependencies
- `pytest`, `dpkg-dev`, standard library.

## What This Phase MUST NOT Change
- Must NOT alter production logic.

## Completion Checklist
- [x] Local workflow-style/Xvfb and offscreen validation completed; exact hosted Ubuntu/Python 3.12 validation remains pending.
- [x] Release audit report written.
- [ ] System certified for production release.


## Validation result

See [the final report](../../../reports/file_intelligence_implementation.md).
Dedicated intelligence: **1,242 passed, 1 skipped**. Each of three full runs:
**1,447 passed, 1 skipped**, actual exit code **0**, no forced exit, no expected
failures. The earlier fixture's unconditional exit-zero backstop was removed and
two subprocess canaries now test failure/success propagation. This is a justified
test-infrastructure repair; production source hashes are unchanged.

The workflow-style run required approval to start Xvfb outside the sandbox because
local display sockets were blocked there. Final runs returned naturally with no
observed outstanding Python threads, tracked running QThreads/active QTimers or
child processes. Final full-suite times of roughly 25–30 seconds miss the phase's
1.5-second target. Exact hosted CI and public release sign-off are not claimed.
