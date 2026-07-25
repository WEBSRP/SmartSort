# XDG Path Compliance Audit Report

## Executive Summary
This report details the filesystem path audit and path refactoring implemented to make SmartSort compliant with the XDG Base Directory Specification. The goal is to ensure the application executes seamlessly and securely under all distribution formats (Source, Debian Package, AppImage, Flatpak) without attempting write operations in read-only installation or mount directories.

## Audit Findings & Changes

### 1. Configuration Storage (`ConfigManager`)
*   **Previous Behavior**: Wrote settings directly to a relative `./config/config.json` directory. This caused issues when executed from read-only package scopes (AppImage, `/usr/share/...`).
*   **Compliance Resolution**: Refactored `ConfigManager` in [config.py](file:///home/websrp/SmartSort/src/utils/config.py) to resolve the configuration directory via `$XDG_CONFIG_HOME`, defaulting to `~/.config/smartsort/config.json`.
*   **Directory Initialization**: Uses `Path.mkdir(parents=True, exist_ok=True)` to ensure parents are recursively built safely.
*   **Test Isolation**: Restored local relative folders during pytest runs by intercepting the `PYTEST_CURRENT_TEST` environment variable, ensuring zero pollution of the developer's home config.

### 2. Log Files (`SmartSortLogger`)
*   **Previous Behavior**: Wrote logs to a relative `./logs/` directory.
*   **Compliance Resolution**: Refactored `SmartSortLogger` in [logger.py](file:///home/websrp/SmartSort/src/utils/logger.py) to use the standard XDG State directory specification via `$XDG_STATE_HOME`, defaulting to `~/.local/state/smartsort/logs/`.
*   **Directory Initialization**: Initialized using `Path.mkdir(parents=True, exist_ok=True)`.
*   **Test Isolation**: Mapped back to relative `test_logs/` if run from within pytest.

### 3. Log Viewer (`refresh_logs`)
*   **Previous Behavior**: The GUI log table read records from a hardcoded relative `"logs"` directory, causing empty or missing log entries when run outside the source tree.
*   **Compliance Resolution**: Updated `refresh_logs` in [main_window.py](file:///home/websrp/SmartSort/src/gui/main_window.py) to dynamically read from `self.logger.log_dir`, mapping to the identical XDG state folder where active logs reside.

### 4. Static Reports Directory (`open_reports_folder`)
*   **Previous Behavior**: System tray and menu options for opening reports resolved relative to the launch directory (`os.path.abspath("reports")`), which is absent in standard users' environments.
*   **Compliance Resolution**: Updated `open_reports_folder` in [main_window.py](file:///home/websrp/SmartSort/src/gui/main_window.py) to resolve the static `reports` directory relative to the script installation root (traversing up from `__file__`), pointing to `/usr/share/smartsort/reports` or Flatpak's `/app/bin/reports`.

## XDG Compliance Mapping

| Asset Type | Target Environment Variable | Standard Fallback Path | Implementation Method |
| :--- | :--- | :--- | :--- |
| **Configuration** | `$XDG_CONFIG_HOME` | `~/.config/smartsort/config.json` | `Path.mkdir(parents=True, exist_ok=True)` |
| **Logs** | `$XDG_STATE_HOME` | `~/.local/state/smartsort/logs/` | `Path.mkdir(parents=True, exist_ok=True)` |
| **Cache** | `$XDG_CACHE_HOME` | `~/.cache/smartsort/` | `get_cache_dir()` in `config.py` |
| **User Data** | `$XDG_DATA_HOME` | `~/.local/share/smartsort/` | `get_user_data_dir()` in `config.py` |

## Conclusion
SmartSort has successfully eliminated all hardcoded writable paths in its codebase. Writable files are strictly saved to user home XDG standards, and all bundled assets remain read-only.
