# Flatpak Python Dependency Audit Report

## Executive Summary
Following the upgrade of the Flatpak runtime from KDE Platform 6.6 to KDE Platform 6.9, the compilation phase failed to resolve `PyQt6-sip` (error: `PyQt6-sip<14,>=13.6 cannot satisfy dependency`). This audit details the root cause (Python version mismatch and ABI tagging change), the mapping of transitive dependencies, the implementation of an automated download script, and successful validation of the offline Flatpak build.

## 1. Root Cause Analysis
During our packaging modernization, the Flatpak runtime and SDK were upgraded to version `6.9` (which uses **Python 3.12**). 
However, our previous vendored dependency folder (`python-wheels/`) contained a pre-downloaded wheel of `pyqt6_sip` built for Python 3.11 (`cp311` tag):
`pyqt6_sip-13.11.1-cp311-cp311-manylinux1_x86_64.manylinux_2_5_x86_64.whl`

Since `PyQt6-sip` is a compiled C extension, its binary ABI must match the interpreter version exactly. Because there was no network access in the sandbox, pip could not download the matching Python 3.12 wheel (`cp312`) from PyPI, leading to the compilation failure.

---

## 2. Transitive Dependency Audit
We performed a full audit of all dependencies declared in [requirements_flatpak.txt](file:///home/websrp/SmartSort/packaging/flatpak/requirements_flatpak.txt) to identify all transitive libraries:

| Target Package | Version | Transitive Dependencies | Role | ABI Dependency |
| :--- | :--- | :--- | :--- | :--- |
| **PyQt6** | `6.7.0` | `PyQt6-sip` (`>=13.6`), `PyQt6-Qt6` (`>=6.7.0`) | Main UI framework bindings | Yes (Requires `cp312` match) |
| **PyQt6-Qt6** | `6.7.3` | None (pure binary) | Bundled Qt6 C++ core library | No (Universal Python wrapper) |
| **PyQt6-sip** | `13.11.1` | None (C extension) | SIP runtime module for PyQt6 | **Yes (Strict cp312 ABI binding)** |
| **watchdog** | `4.0.1` | None | File system events monitor | No (Pure Python wheel) |
| **notify2** | `0.3.1` | None | DBus Desktop notifications | No (Pure Python wheel) |

---

## 3. Automation and Wheel Generation
To prevent future ABI mismatches and ensure simple maintainability, we created an automated dependency resolution script [download_wheels.sh](file:///home/websrp/SmartSort/packaging/flatpak/download_wheels.sh):

```bash
# Dynamically detect Python version inside Flatpak org.kde.Platform//6.9 runtime
PYTHON_VERSION=$(flatpak run --runtime=org.kde.Platform//6.9 --command=python3 org.kde.Platform//6.9 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "3.12")

# Derive ABI tag (e.g. cp312)
ABI_TAG="cp${PYTHON_VERSION//./}"

# Download requirements and all transitive dependencies offline
pip3 download \
  --dest "$WHEELS_DIR" \
  --python-version "$PYTHON_VERSION" \
  --implementation cp \
  --abi "$ABI_TAG" \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 \
  --platform manylinux_2_28_x86_64 \
  --platform any \
  -r "$REQUIREMENTS_FILE"
```

Running this script fetches all dependencies for Python 3.12 (ABI tag `cp312`), staging the following files under `python-wheels/`:
1. `PyQt6-6.7.0-1-cp38-abi3-manylinux_2_28_x86_64.whl`
2. `PyQt6_Qt6-6.7.3-py3-none-manylinux_2_28_x86_64.whl`
3. `pyqt6_sip-13.11.1-cp312-cp312-manylinux1_x86_64.manylinux_2_5_x86_64.whl` (Upgraded `cp312` SIP wheel)
4. `watchdog-4.0.1-py3-none-manylinux2014_x86_64.whl`
5. `notify2-0.3.1-py2.py3-none-any.whl`

---

## 4. Verification and Offline Validation
We executed the validation steps to ensure compilation and launches are successful:

1. **Clean Workspace**: Removed build folders (`app_dir/`, `repo/`).
2. **Execute Build Script**: Ran `./build_flatpak.sh` to initialize the Flatpak build against runtime/SDK 6.9 and perform offline wheel installations.
   ```
   Installing Python dependencies inside sandbox...
   Looking in links: ../../packaging/flatpak/python-wheels
   Processing ./python-wheels/watchdog-4.0.1-py3-none-manylinux2014_x86_64.whl
   Processing ./python-wheels/PyQt6-6.7.0-1-cp38-abi3-manylinux_2_28_x86_64.whl
   Processing ./python-wheels/notify2-0.3.1-py2.py3-none-any.whl
   Processing ./python-wheels/pyqt6_sip-13.11.1-cp312-cp312-manylinux1_x86_64.manylinux_2_5_x86_64.whl
   Processing ./python-wheels/PyQt6_Qt6-6.7.3-py3-none-manylinux_2_28_x86_64.whl
   Successfully installed PyQt6-6.7.0 PyQt6-Qt6-6.7.3 PyQt6-sip-13.11.1 notify2-0.3.1 watchdog-4.0.1
   ...
   Flatpak build complete. Generated smartsort.flatpak in workspace root.
   ```
3. **Execution Check**: Launched the application launcher helper inside the sandboxed directory to ensure imports resolve:
   ```bash
   $ flatpak build app_dir smartsort --help
   usage: main.py [-h] [--service] [--daemon]
   ...
   ```
   No missing module errors were reported, confirming a 100% offline-compatible build.
