# Phase 19: Debian Packaging Updates & Dependency Integration

## Objective
Update the Debian package control specification in `packaging/debian/DEBIAN/control`, build the `.deb` release package using `./packaging/debian/build_deb.sh`, and verify package contents and dependencies.

## Why This Phase Exists
SmartSort is distributed exclusively as a native Debian package (`.deb`). Packaging metadata must be synchronized with the new `src/core/file_intelligence/` tree and Debian extractor dependencies.

## Inputs
- `packaging/debian/DEBIAN/control`, `packaging/debian/build_deb.sh`, and complete `src/` tree.

## Outputs
- Updated `packaging/debian/DEBIAN/control`.
- Valid Debian package: `build/deb/smartsort_<version>_all.deb`.

## Files To Create
- None.

## Files To Modify
- `packaging/debian/DEBIAN/control`: Update dependencies list.
- `docs/packaging.md`: Document updated dependencies.

## Existing Components To Reuse
- `packaging/debian/build_deb.sh`: Debian package assembly script.

## APIs / Interfaces
```text
# packaging/debian/DEBIAN/control
Package: smartsort
Version: 1.2.0
Architecture: all
Maintainer: Soumya Ranjan Parida <contact@smartsort-org.com>
Depends: python3, python3-pyqt6, python3-watchdog, python3-notify2, python3-pypdf, python3-pil, python3-mutagen, libglib2.0-0, gir1.2-notify-0.7
Suggests: python3-docx, python3-openpyxl
Description: Intelligent Download Organizer and File Intelligence Platform for Linux
 SmartSort is an offline Linux file automation, organization, and intelligence platform built in Python and PyQt6.
```

## Data Structures
- Debian binary package structure (`control`, `data.tar.xz`).

## Algorithms
- Run `./packaging/debian/build_deb.sh`.
- Audit package contents using `dpkg-deb -c build/deb/*.deb`.
- Audit package control info using `dpkg-deb -I build/deb/*.deb`.

## Error Handling
- Capture packaging assembly errors, missing maintainer scripts, or bad permissions.

## Security Considerations
- Ensure maintainer scripts (`postinst`, `postrm`, `prerm`) have standard 755 permissions.

## Performance Considerations
- Package build completes in < 5 seconds.

## CI / Headless Requirements
- Debian packaging commands (`dpkg-deb`) run in headless CI environments.

## Tests
- Run `bash packaging/debian/build_deb.sh`.
- Assert package builds cleanly with exit code 0.
- Assert package contains `/usr/share/smartsort/src/core/file_intelligence/`.

## Acceptance Criteria
- [x] `packaging/debian/DEBIAN/control` updated with correct dependencies.
- [x] `build_deb.sh` produces verified `.deb` artifact.
- [x] Package includes complete `src/core/file_intelligence/` codebase.

## Dependencies
- `dpkg-deb`, `binutils`.

## What This Phase MUST NOT Change
- Must NOT restore non-Debian packaging (AppImage, Flatpak, RPM).

## Completion Checklist
- [x] Control file updated.
- [x] Debian package built and verified.


## Implementation and package verification — 2026-11-18

Completed after repairing the two Phase 18 cache blockers and obtaining three
consecutive full-suite results of **1,445 passed, 1 skipped**, actual exit code 0
and no expected failures. See the Phase 18 follow-up report.

The control file now requires `python3-pypdf`, `python3-pil` and `python3-mutagen`
and suggests `python3-docx`/`python3-openpyxl`. The description covers file
intelligence. Native bounded XML Office readers remain available without the
suggested SDKs. Local Debian 13 apt metadata supplies every added dependency.
The prior broad compatibility claims were replaced with explicit dependency
availability requirements in `docs/packaging.md`.

The existing build script already copies the full source tree, excludes bytecode,
sets root ownership and 0755 maintainer scripts, and only installs app-owned icons
in the shared system hicolor directories. No build-script change was needed in
this phase. App-private assets may contain a theme descriptor; the package does
not claim the system `/usr/share/icons/hicolor/index.theme` or its cache.

Artifact: `build/deb/smartsort_1.1.6+intelligence.20261118.1_all.deb`.
The preview suffix distinguishes this local feature build from the installed GUI
preview. `src/version.py` and the control template retain base version 1.1.6;
`SMARTSORT_PACKAGE_VERSION` supplies the generated package version. The phase's
illustrative 1.2.0 release version is not claimed before Phase 20 certification.

Validation:

- Build exit code **0**, artifact **13,666,144 bytes**. Build time **5.229 s**;
  the five-second target was narrowly missed on this machine.
- Extended the real package regression test: **1 passed** in 5.12 s. It checks
  every intelligence Python source byte-for-byte, dependencies, root ownership,
  script permissions, icons and exclusion of bytecode.
- Inspected generated control/data archives; all intelligence modules (including
  `cache.py` and `privacy.py`) match the workspace. Maintainer scripts and wrapper
  have 0755 mode, and archive ownership is root:root.
- Extracted to a private temporary directory and used **`/usr/bin/python3`** to
  import the packaged GUI and required backends, perform identical cold/warm
  preview on the former cache regression fixture, then verify transfer/report.
  Imported code paths were checked to come from the extracted artifact.
- `desktop-file-validate` and shell syntax checks pass. Maintainer scripts were
  syntax-checked, not executed. No package was installed or user service started.
- `apt-get --simulate install <artifact>` succeeds: proposes upgrading the existing
  GUI preview and adding `python3-pypdf`, with no removals. This is local dependency
  resolution, not an actual installation test or a clean-distribution matrix.
- SHA-256: `1f4ccc354794932c0534c0ca66602c9924b1715472649785157498226a57a6ba`.
  A `.deb.sha256` sidecar is written beside the artifact.
- Validation records live locally under `build/validation/phase19/`.

Phase 20 — Headless CI Validation & Release Certification — remains next.
Earlier extractor/report latency limitations remain documented; this package is a
verified local preview rather than a certified release.


Phase 20 subsequently rebuilt the same local preview version. The current artifact
is **13,665,952 bytes**, SHA-256
`fdb02245eca3494fa5c96cc9173cb71047182660b4aba30296dfd384d469bdb2`; the earlier Phase 19 hash above identifies its original build.
See the final implementation report for the current artifact and validation record.
