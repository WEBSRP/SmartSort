# Release Workflow

This document outlines the official release flow and checklist for publishing public versions of SmartSort.

---

## 1. Release Flow

When publishing a new release:

1.  **Version Update**:
    - Centralize the new version number inside [src/version.py](file:///home/websrp/SmartSort/src/version.py).
    - Ensure manifests and spec files under `packaging/` consume this version dynamically.
2.  **Changelog Sync**:
    - Document all fixes, updates, and milestones inside [CHANGELOG.md](file:///home/websrp/SmartSort/CHANGELOG.md) under the release heading.
3.  **Local Quality Control**:
    - Verify all tests pass locally: `python3 -m pytest tests/`
    - Run formatting checks.
4.  **Local Package Compiles**:
    - Execute build scripts for Debian, AppImage, Flatpak, and RPM.
    - Confirm output files are cleanly saved inside `build/`.
5.  **GitHub Release Tagging**:
    - Commit all files and tag the commit:
      ```bash
      git tag -a v1.0.0 -m "Release v1.0.0"
      git push origin v1.0.0
      ```
    - GitHub Actions will run tests, compile release binaries, and upload the build outputs as job artifacts automatically.
