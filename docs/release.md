# Release Workflow

This document outlines the official release flow and checklist for publishing public versions of SmartSort.

---

## 1. Release Flow

When publishing a new release:

1.  **Version Update**:
    - Centralize the new version number inside [src/version.py](../src/version.py).
    - Ensure Debian packaging metadata consumes this version dynamically.
2.  **Changelog Sync**:
    - Document all fixes, updates, and milestones inside [CHANGELOG.md](../CHANGELOG.md) under the release heading.
3.  **Local Quality Control**:
    - Verify all tests pass locally: `PYTHONPATH=. pytest`
    - Run formatting checks.
4.  **Local Package Compile**:
    - Execute the Debian build script: `./packaging/debian/build_deb.sh`.
    - Confirm the output file is saved inside `build/deb/`.
5.  **GitHub Release Tagging**:
    - Commit all files and tag the commit:
      ```bash
      git tag -a vX.Y.Z -m "Release vX.Y.Z"
      git push origin vX.Y.Z
      ```
    - GitHub Actions will run tests, compile the Debian release package, and upload the `.deb` artifact automatically.

