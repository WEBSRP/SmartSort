# Flatpak Dependency Packaging Report

## Executive Summary
This report details the implementation of a fully offline, reproducible, and least-privilege Flatpak build process for SmartSort, complying with Flatpak packaging best practices. We eliminated all runtime network dependency retrieval during the compilation phase, staging local wheel binaries that match the Flatpak runtime's Python version.

## Root Cause & Challenge
In standard environments, `flatpak-builder` disables network access inside the compilation sandbox. Executing `pip3 install -r requirements.txt` during the build phase causes a compilation failure since PyPI is unreachable.

Additionally, the Python version on the host (`3.13.5`) differs from the Python version bundled with the Flatpak `org.kde.Sdk//6.6` runtime (`3.11.13`). Simply downloading host-native wheels would result in an ABI mismatch (e.g., Python 3.13 `.whl` vs Python 3.11 target sandbox).

## Implementation Details

### 1. Vendoring Python 3.11 Compatible Wheels
We used specific pip tags on the host to download compatibility wheels matching the Flatpak target architecture and python environment:

```bash
pip3 download \
  --dest python-wheels \
  --python-version 3.11 \
  --implementation cp \
  --abi cp311 \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 \
  --platform manylinux_2_28_x86_64 \
  --platform any \
  watchdog==4.0.1 PyQt6==6.7.0 notify2==0.3.1
```

This successfully staged the following offline wheel assets inside [python-wheels/](file:///home/websrp/SmartSort/packaging/flatpak/python-wheels/):
*   `watchdog-4.0.1-py3-none-manylinux2014_x86_64.whl` (universal file watcher)
*   `PyQt6-6.7.0-1-cp38-abi3-manylinux_2_28_x86_64.whl` (compatible with PyQt6-abi3)
*   `notify2-0.3.1-py2.py3-none-any.whl` (pure python DBus notifications)
*   `PyQt6_Qt6-6.7.3-py3-none-manylinux_2_28_x86_64.whl` (bundled Qt6 core package)
*   `pyqt6_sip-13.11.1-cp311-cp311-manylinux1_x86_64.manylinux_2_5_x86_64.whl` (Python 3.11 ABI specific bindings)

### 2. Offline Build Manifest Refactoring
We updated [com.smartsort.SmartSort.yml](file:///home/websrp/SmartSort/packaging/flatpak/com.smartsort.SmartSort.yml#L17) to replace online pip installation with offline lookups:

```yaml
build-commands:
  - pip3 install --no-index --find-links=packaging/flatpak/python-wheels --prefix=/app -r packaging/flatpak/requirements_flatpak.txt
```

*   `--no-index` forces pip to skip remote index queries (eliminates PyPI access).
*   `--find-links=packaging/flatpak/python-wheels` instructs pip to look exclusively inside the local vendored wheel directory.

We also updated [build_flatpak.sh](file:///home/websrp/SmartSort/packaging/flatpak/build_flatpak.sh#L15) similarly, and omitted the `--share=network` argument from the build instruction to enforce the sandbox compile restrictions.

## Verification & Build Validation

### 1. Flatpak Builder Validation
Running `flatpak-builder` completes successfully with clean exits:

```
$ flatpak-builder --user --force-clean build_dir com.smartsort.SmartSort.yml
...
Committing stage build-smartsort to cache
Cleaning up
Committing stage cleanup to cache
Finishing app
Exporting share/applications/com.smartsort.SmartSort.desktop
Exporting share/icons/hicolor/scalable/apps/com.smartsort.SmartSort.png
Committing stage finish to cache
Pruning cache
```

### 2. Standalone Bundle Validation
The build successfully outputted the portable package `smartsort.flatpak` in the workspace root.

## Conclusion
SmartSort's Flatpak packaging is now 100% offline-compliant, reproducible, and aligns with secure sandboxing standards by requiring zero internet permissions during compilation.
