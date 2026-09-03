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
- [ ] `packaging/debian/DEBIAN/control` updated with correct dependencies.
- [ ] `build_deb.sh` produces verified `.deb` artifact.
- [ ] Package includes complete `src/core/file_intelligence/` codebase.

## Dependencies
- `dpkg-deb`, `binutils`.

## What This Phase MUST NOT Change
- Must NOT restore non-Debian packaging (AppImage, Flatpak, RPM).

## Completion Checklist
- [ ] Control file updated.
- [ ] Debian package built and verified.
