# Release Validation

Date: 2026-07-25
Target: SmartSort v1.0.1 Debian-only release

## Debian Build Status

Status: Passed.

Validation command:

```bash
./packaging/debian/build_deb.sh
```

Expected artifact:

```text
build/deb/smartsort_1.0.1_all.deb
```

## Test Status

Status: Passed.

Validation command:

```bash
QT_QPA_PLATFORM=offscreen PYTHONUNBUFFERED=1 python3 -m pytest -vv -s --durations=20 --durations-min=1 tests/
```

Latest result during consolidation:

```text
40 passed
```

## CI Status

Status: Updated and structurally validated for Debian-only release.

The GitHub Actions workflow now performs:

- Python setup.
- System dependency installation for PyQt tests.
- Python dependency installation.
- Compile validation.
- Unit test execution.
- Debian package build.
- Debian artifact upload.

Unsupported package builds and artifact paths were removed.

## Documentation Validation

Status: Updated and link-checked.

Documentation now identifies the official release package as Debian `.deb` and lists Debian, Ubuntu, Linux Mint, and other Debian-based distributions as supported. AppImage, Flatpak, and RPM appear only as future planned packaging, not as release deliverables.

Markdown link validation passed across README, docs, and remaining reports.

## Packaging Validation

Status: Debian validated.

Unsupported packaging implementations were removed from the release tree. The only supported package implementation is:

```text
packaging/debian/
```
