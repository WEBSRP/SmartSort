# Phase 20: Headless CI Validation & Release Certification

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
- [ ] 3 consecutive full-suite test runs pass 100% with exit code 0.
- [ ] Zero thread leaks or unmanaged timers detected.
- [ ] Debian package compiles cleanly.
- [ ] Final certification report `reports/file_intelligence_implementation.md` generated.

## Dependencies
- `pytest`, `dpkg-dev`, standard library.

## What This Phase MUST NOT Change
- Must NOT alter production logic.

## Completion Checklist
- [ ] CI pipeline validated.
- [ ] Release audit report written.
- [ ] System certified for production release.
