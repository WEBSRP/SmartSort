# Path Manager Refactoring Report

This report documents the architectural centralization of path resolution inside the SmartSort codebase using a dedicated paths manager.

---

## 1. Centralized Path Manager (`AppPaths`)

Created a new central paths module [src/utils/paths.py](file:///home/websrp/SmartSort/src/utils/paths.py) containing the `AppPaths` class. This class is the sole authority for locating all filesystem files and directories:

*   `AppPaths.resource_dir()`: Returns the static assets directory.
*   `AppPaths.default_config()`: Locates the bundled default configuration template.
*   `AppPaths.config_dir()`: Resolves the XDG configuration base directory.
*   `AppPaths.config_file()`: Resolves the active user settings config path.
*   `AppPaths.logs_dir()`: Resolves the XDG logs/state directory.
*   `AppPaths.data_dir()`: Resolves the XDG share/data directory.
*   `AppPaths.cache_dir()`: Resolves the XDG cache directory.

---

## 2. Refactored Modules

All hardcoded path resolution, string additions, and `os.path` traversals were replaced with `AppPaths` lookups using Pathlib:

1.  **[src/utils/config.py](file:///home/websrp/SmartSort/src/utils/config.py)**: Decoupled from hardcoded repository configurations; delegates path checks and merges directly through `AppPaths`.
2.  **[src/utils/logger.py](file:///home/websrp/SmartSort/src/utils/logger.py)**: Decoupled logging target locations; log folders are resolved using `AppPaths.logs_dir()`.
3.  **[src/gui/main_window.py](file:///home/websrp/SmartSort/src/gui/main_window.py)**: Decoupled tray and windows icon search path registrations; resolves them through `AppPaths.resource_dir()`.
4.  **[src/gui/tray_manager.py](file:///home/websrp/SmartSort/src/gui/tray_manager.py)**: Resolves icon assets directory via `AppPaths.resource_dir()`.
5.  **[src/utils/autostart.py](file:///home/websrp/SmartSort/src/utils/autostart.py)**: Decoupled desktop entry icon file searches.
6.  **[main.py](file:///home/websrp/SmartSort/main.py)**: Branded application-wide icon loading resolved through `AppPaths.resource_dir()`.

---

## 3. Package Format Compatibility

`AppPaths` resolves the bundle root dynamically by matching the active runtime profile:
- Priority-resolves the bundle root relative to `sys.argv[0]` when running Python scripts or wrapper binaries directly.
- Falls back to relative code file layout traversal (`paths.py` relative imports) for standalone modules.
- This ensures it resolves assets and default configurations correctly across source trees, Debian, AppImage, and Flatpak platforms.
