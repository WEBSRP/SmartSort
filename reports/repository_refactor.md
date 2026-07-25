# Repository Refactoring Report

This report documents the restructuring of the SmartSort repository into a clean, professional, and dry directory structure.

---

## 1. Single Source of Truth Alignment

Previously, identical copies of the Python source tree (`main.py`, `src/`, `assets/`, `config/`) were duplicated inside individual format-specific subdirectories under `packaging/`. 

- **Audited & Removed Duplicate Trees**: Removed all duplicate application folders under `packaging/debian/smartsort_0.5.0_all/usr/share/smartsort/`.
- **Target Folder Contents**: Packaging directories now contain ONLY:
  - Manifests (`com.smartsort.SmartSort.yml`)
  - Build scripts (`build_deb.sh`, `build_appimage.sh`, `build_flatpak.sh`)
  - Metadata / Control files (`control`, `postinst`, `postrm`, `prerm`)
  - Desktop entries (`smartsort.desktop`, `com.smartsort.SmartSort.desktop`)
  - Wrappers / Launchers (`AppRun`, `smartsort.sh`)
- Packaging formats now draw dynamically from the root directories: `src/`, `assets/`, `config/`.

---

## 2. Version Source Centralization

- **File Created**: [src/version.py](file:///home/websrp/SmartSort/src/version.py) containing:
  ```python
  VERSION = "0.5.0"
  ```
- All build scripts read this version string dynamically using pattern extraction:
  ```bash
  VERSION=$(grep -oP 'VERSION\s*=\s*"\K[^"]+' "src/version.py")
  ```
- Eliminates hardcoded duplicate version records inside package manifests, script titles, and filenames.

---

## 3. Configuration Management Refactor

- **Introduced Template**: [config/config.default.json](file:///home/websrp/SmartSort/config/config.default.json).
- **Untracked User Settings**: Added `config/config.json` and `config/config.json.bak` to `.gitignore` to prevent developers committing user-specific configurations.
- **First Launch Auto-Copy**: Added checks in `ConfigManager.__init__` to dynamically copy `config.default.json` to `config.json` if the user configuration is missing.
