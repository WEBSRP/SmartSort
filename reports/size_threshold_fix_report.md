# SmartSort Large File Threshold Size Parsing Bugfix Report

## 1. Why the Bug Existed
Previously, the Settings panel in the GUI used a PyQt6 `QSpinBox` which only allowed integer values (e.g. `1`, `2`, `3`). This was labeled `Large File Threshold (GB)` and was stored as a raw number of Gigabytes.
This layout:
* Rejected decimal input (e.g. `1.5` or `2.75`), which was inconsistent with the new rule engine.
* Restrained users from entering human-readable suffixes like `500MB` or `750KB` directly from settings.

---

## 2. How Parsing and Storage Now Works
* **User Input**: The `QSpinBox` has been replaced with a `QLineEdit` text field.
* **Human-Readable Formats**: The input field accepts case-insensitive size strings (e.g. `500kb`, `500KB`, `1.5MB`, `2.5GB`, etc.) with or without spaces.
* **Internal Representation**: All values are automatically parsed into absolute bytes using `parse_size_to_bytes` and stored internally as an integer count of bytes inside `large_file_threshold_gb` of `config.json`.
* **Backward Compatibility**: During initialization, the `ConfigManager` automatically inspects loaded configuration files. If it detects a legacy value (int/float < 10000), it translates it from Gigabytes to bytes (multiplying by `1024**3`), saves a backup copy to `.bak`, and updates `config.json` safely.

---

## 3. Files Modified
1. **[src/utils/config.py](file:///home/websrp/project/smartsort/src/utils/config.py)**: Incorporated legacy float/int threshold auto-conversion to byte counts inside `load_config`.
2. **[src/organizer.py](file:///home/websrp/project/smartsort/src/organizer.py)**: Modified the size comparison logic to evaluate file size in bytes against the byte-based threshold.
3. **[src/gui/main_window.py](file:///home/websrp/project/smartsort/src/gui/main_window.py)**: Swapped the `QSpinBox` with the `QLineEdit` setting controls, implemented `bytes_to_human_string` for display formatting, and added input verification.
4. **[tests/test_core.py](file:///home/websrp/project/smartsort/tests/test_core.py)**: Appended `test_large_file_threshold_size_parsing` checking validations, suffix inputs, and legacy settings conversions, and updated existing config test assertions to expect byte counts.
