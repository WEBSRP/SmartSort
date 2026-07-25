# Debian Release Migration

Date: 2026-07-25
Target: SmartSort v1.0.1

## Summary

SmartSort v1.0.1 has been consolidated into a Debian-first release. The official release package is Debian `.deb`, intended for Debian, Ubuntu, Linux Mint, and other Debian-based distributions.

Future planned package formats are documented as AppImage, Flatpak, and RPM, but their implementations and CI artifacts are not part of this release.

## Files Removed

- `packaging/appimage/`
- `packaging/flatpak/`
- `packaging/rpm/`
- `build/appimage/`
- `build/flatpak/`
- `build/rpm/`
- Package-format-specific historical reports for AppImage, Flatpak, RPM, and obsolete multi-format release state.

## Files Modified

- `.github/workflows/ci.yml`: removed unsupported package build and artifact upload steps.
- `README.md`: rewrote installation, project structure, service, and build sections for Debian-only release.
- `docs/build.md`: reduced release build instructions to Debian package generation.
- `docs/packaging.md`: documented Debian package as the official release package.
- `docs/release.md`: updated release checklist to build and upload only `.deb` artifacts.
- `.github/ISSUE_TEMPLATE/bug_report.md`: constrained packaging examples to source and Debian `.deb`.
- `CHANGELOG.md`: recorded Debian-only release consolidation.

## Rationale

AppImage, Flatpak, and RPM were not reproducibly validated for v1.0.1. Keeping those implementations in the release tree implied support that the current repository could not prove. Removing them reduces release risk and aligns CI, documentation, and artifacts with the validated deliverable.

## Repository Simplifications

- One official package build path: `./packaging/debian/build_deb.sh`.
- One package output directory: `build/deb/`.
- One CI release artifact family: `.deb`.
- Reduced stale report surface describing unsupported packages.

## Release Impact

Users on Debian-based distributions receive a validated native package. Users needing other package formats should wait for future releases where those formats are reintroduced with reproducible build validation.

