# Compilation & Build Guide

This document describes how to set up your developer environment and compile the official SmartSort Debian package locally.

---

## 1. Developer Environment Setup

To run and debug SmartSort from source:

1.  **Prerequisites**:
    - Python 3.8 or higher.
    - PyQt6 (PyQt6-Qt6).
    - Watchdog.
    - Notify2 (for desktop notifications).

2.  **Dependencies Installation**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run Locally**:
    ```bash
    python3 main.py
    ```

4.  **Run Test Suite**:
    We use `pytest` for automated test verification:
    ```bash
    python3 -m pytest tests/
    ```

---

## 2. Compiling the Release Package

SmartSort v1.0.1 officially supports Debian-based distributions. The release build compiles dynamically from the active source tree into the central `build/deb/` output directory.

Before building, verify the target version in [src/version.py](../src/version.py).

### Officially Supported

- Debian
- Ubuntu
- Linux Mint
- Other Debian-based distributions

### Future Planned Packaging

- AppImage
- Flatpak
- RPM

### Build Debian (`.deb`)

```bash
./packaging/debian/build_deb.sh
```

Outputs to `build/deb/smartsort_<version>_all.deb`.
