# SmartSort Configuration Initialization Fix Report

This report outlines the audit findings and implementation details for establishing a robust, crash-proof configuration initialization workflow for SmartSort.

---

## 1. Audit of Configuration Keys

We audited the entire codebase to identify all configuration keys accessed by the GUI and background daemon. A total of **12 configuration keys** were identified:

| # | Key Name | Expected Type | Description | Default Value |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `downloads_folder` | `str` | The source directory being watched for incoming files. | `"~/Downloads"` |
| 2 | `destination_base` | `str` | The base directory where sorted files are moved. | `"~"` |
| 3 | `large_file_threshold_gb` | `int` or `float` | File size limit distinguishing small and large files (stored in bytes). | `2.5` (converted to `2684354560` bytes) |
| 4 | `enable_hash_verification` | `bool` | Enables hashing to verify integrity post-transfer. | `true` |
| 5 | `enable_notifications` | `bool` | Controls OS desktop system notifications. | `true` |
| 6 | `enable_duplicate_detection` | `bool` | Performs SHA-256 duplicate checking before moving files. | `true` |
| 7 | `conflict_resolution` | `str` | Policy when filename conflicts occur (`rename`, `overwrite`, `skip`). | `"rename"` |
| 8 | `categories` | `dict` | Predefined file sorting rules based on extension or keyword matching. | *(Standard category templates)* |
| 9 | `rules` | `list` | Custom user-defined rule dictionaries. | `[]` |
| 10 | `start_minimized` | `bool` | Launches the GUI hidden in the system tray. | `false` |
| 11 | `autostart` | `bool` | Configures GNOME auto-launch on desktop login. | `false` |
| 12 | `theme` | `str` | GUI look and feel preference (`system`, `dark`, `light`). | `"system"` |

---

## 2. Identified Vulnerabilities

Before our fixes, the application suffered from multiple configuration-related vulnerabilities:
1. **Missing Keys Crash**: If any of the optional keys (such as `theme`, `conflict_resolution`, `rules`, or `categories`) were completely missing from the user's `config.json`, the GUI crashed on startup when trying to load widget states (e.g. `setChecked(None)` raised a `TypeError`).
2. **Corrupted JSON Failure**: If `config.json` was corrupted or empty, the loading process crashed the application instead of falling back to default configuration values.
3. **No Automatic Merge**: Any new settings added during development did not automatically merge into existing user configurations, forcing manual updates or configuration deletion.

---

## 3. Implemented Fixes & Robust Merging Strategy

We implemented a comprehensive, multi-layer fallback strategy in [src/utils/config.py](file:///home/websrp/project/smartsort/src/utils/config.py) and [src/gui/main_window.py](file:///home/websrp/project/smartsort/src/gui/main_window.py):

### A. Deep Configuration Merging
We updated the `load_config` logic in `ConfigManager` to perform the following steps on launch:
1. Initialize a complete dictionary of hardcoded defaults covering all 12 keys.
2. Load and overlay any keys specified in `config/default_config.json`.
3. Load the user's configuration file `config/config.json`. If it fails (due to missing files or corrupted JSON syntax), it attempts to load from the backup file `config.json.bak`. If both fail, it falls back to default values.
4. Perform key-by-key type validation. If a user-supplied key matches the expected type, it is retained. If the key is missing or has an incorrect type (e.g. `enable_notifications: "string"`), it is automatically repaired with the default value.
5. Save the resulting merged configuration back to `config.json` if keys were missing or corrected, keeping the file healthy and up to date.

### B. Safe Fallback in `ConfigManager.get`
We rewrote the `get` method to enforce defaults at runtime. If the requested key resolves to `None`, it automatically retrieves the value from the last-resort defaults registry, preventing downstream `None` crashes.

### C. Safe GUI Initialization & Input Validation
We updated [src/gui/main_window.py](file:///home/websrp/project/smartsort/src/gui/main_window.py)'s settings initializers to:
* Coerce checkbox states safely using `bool(...)`:
  ```python
  self.chk_autostart.setChecked(bool(self.config.get("autostart", False)))
  self.chk_notif.setChecked(bool(self.config.get("enable_notifications", True)))
  self.chk_dup.setChecked(bool(self.config.get("enable_duplicate_detection", True)))
  ```
* Enforce string theme indices with fallback:
  ```python
  theme_val = str(self.config.get("theme", "system")).lower()
  ```
* Handle size parsing inside `bytes_to_human_string` with `try-except` blocks. If any invalid type or corrupted size string is supplied, the GUI gracefully resolves it to `"2.5GB"` rather than crashing.

---

## 4. Verification and Testing

1. **Successful Test Runs**:
   We ran the unit tests and verified that **all 31 tests passed successfully**.
   ```bash
   $ PYTHONPATH=. ./smartsort/bin/pytest
   ============================== 31 passed in 0.28s ==============================
   ```

2. **Added Robustness Unit Test**:
   We appended `test_config_initialization_robustness` to [tests/test_core.py](file:///home/websrp/project/smartsort/tests/test_core.py) verifying:
   * Automatic creation of `config.json` with all 12 keys if it is missing.
   * Graceful recovery from corrupted JSON files.
   * Merging of default values for missing configuration keys.
   * Auto-healing of wrong configuration types without raising crashes.

3. **Fresh Config File Simulation**:
   We verified that loading a completely fresh config file automatically populates all 12 keys, including `theme`, `conflict_resolution`, and `rules` default fields.
