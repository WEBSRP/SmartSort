# Compilation & Build Guide

This document describes how to set up your developer environment and compile the SmartSort package binaries locally.

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

## 2. Compiling Packages

SmartSort compiles release-ready packages dynamically from the active source tree into the central `build/` output directory. 

Before building, verify the target version in [src/version.py](file:///home/websrp/SmartSort/src/version.py).

-   **Build Debian (`.deb`)**:
    ```bash
    ./packaging/debian/build_deb.sh
    ```
    Outputs to `build/deb/smartsort_<version>_all.deb`.

-   **Build AppImage (`.AppImage`)**:
    ```bash
    ./packaging/appimage/build_appimage.sh
    ```
    Outputs to `build/appimage/SmartSort-<version>-x86_64.AppImage`.

-   **Build Flatpak (`.flatpak`)**:
    ```bash
    ./packaging/flatpak/build_flatpak.sh
    ```
    Outputs to `build/flatpak/smartsort_<version>.flatpak`.

-   **Build RPM (`.rpm`)**:
    ```bash
    ./packaging/rpm/build_rpm.sh
    ```
    Outputs custom `.spec` specifications and source tarballs to `build/rpm/`.
