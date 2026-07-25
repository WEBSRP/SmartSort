# Build System Documentation Report

This report documents the design and execution details of the dedicated, automated packaging scripts created for SmartSort.

---

## 1. Automated Build Scripts

The repository includes three dedicated scripts inside the `packaging/` tree:

### A. Debian Packaging (`packaging/debian/build_deb.sh`)
- **Action Flow**:
  1. Detects package version from `src/version.py`.
  2. Creates a temporary build workspace `packaging/debian/smartsort_${VERSION}_all`.
  3. Replaces the `Version:` header dynamically in the generated `DEBIAN/control` file.
  4. Copies maintainer scripts (`postinst`, `postrm`, `prerm`), setting execute permissions.
  5. Copies application source files (`main.py`, `src/`, `assets/`, `config.default.json`).
  6. Copies standard icons, scalable tray assets, and systemd services.
  7. Runs `dpkg-deb --build --root-owner-group` to compile the package.
  8. Deletes the temporary workspace directory.

### B. AppImage Packaging (`packaging/appimage/build_appimage.sh`)
- **Action Flow**:
  1. Detects version.
  2. Generates the temporary workspace `packaging/appimage/SmartSort.AppDir`.
  3. Copies the source tree, assets, default configurations, and `AppRun` binary wrapper.
  4. Resolves app icon path mappings and packages desktop launcher entries.
  5. Invokes `./appimagetool` to compile the final `.AppImage` output.
  6. Deletes the temporary `SmartSort.AppDir` directory.

### C. Flatpak Packaging (`packaging/flatpak/build_flatpak.sh`)
- **Action Flow**:
  1. Detects version.
  2. Creates temporary workspaces `app_dir/` and `repo/`.
  3. Initializes flatpak build environment and bootstraps `pip` inside the sandbox using `ensurepip`.
  4. Installs Python dependencies offline inside the sandbox using pre-downloaded wheels and `--prefix=/app`.
  5. Purges intermediate build-time pip binaries to save space.
  6. Copies main files, modules, desktop definitions, and launcher wrappers.
  7. Runs `flatpak build-finish`, `build-export`, and `build-bundle` to produce `smartsort_${VERSION}.flatpak`.
  8. Deletes temporary folders (`app_dir` and `repo`).

---

## 2. Temporary Directory Safety & Cleanup

To ensure that the host build system remains clean:
- Every build script targets absolute paths relative to its location, allowing execution from any directory.
- Intermediate workspaces are cleaned up via `rm -rf` at the end of execution, ensuring nothing but the final package remains.
