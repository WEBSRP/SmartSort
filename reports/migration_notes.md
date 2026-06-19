# SmartSort Migration Notes Report

## 1. Upgrade Safety & Backups
When upgrading to SmartSort version 2.0+, dynamic rules completely replace the legacy hardcoded categorization parameters. 
To ensure zero configuration or data loss, **upgrades are executed automatically** on application start:
1. When the `ConfigManager` loads configuration parameters, the [RuleManager](file:///home/websrp/project/smartsort/src/rules/manager.py#L154) checks if the legacy `"categories"` dictionary is present.
2. If `"categories"` is detected, a backup copy of the active configuration file is immediately saved in the configuration path as:
   `config/config.json.bak` (or relative path to config).
3. Legacy categories are converted into prioritized rule mappings.
4. The upgraded config is written back to the active `config/config.json` path, and `"categories"` is permanently deleted.

---

## 2. Legacy Categories to Rule Engine Mapping Details

The migration wrapper performs the following conversions:

### Category: `Images`
* **Legacy Behavior**: Mapped all image extensions to the `Pictures` base directory.
* **Upgraded Rules (Phase 3 Spec)**: Split into 3 independent, size-based quality rules:
  1. **Low Quality Images** (Priority 1): Sizes `< 1MB` go to `Pictures/Low_Quality/{extension}`.
  2. **Medium Quality Images** (Priority 2): Sizes `>= 1MB` and `< 5MB` go to `Pictures/Medium_Quality/{extension}`.
  3. **High Quality Images** (Priority 3): Sizes `>= 5MB` go to `Pictures/High_Quality/{extension}`.
* **Supported Extensions**: `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`.

### Category: `Videos`
* **Legacy Behavior**: Categorized video extensions and split destination based on size threshold config.
* **Upgraded Rules**: Split into 2 rules:
  1. **Videos (Big)**: Priority 4, size `>=` threshold, target `"Videos/Big_Videos"`.
  2. **Videos**: Priority 5, target `"Videos"`.

### Other Extension & Keyword Categories (e.g. Cybersecurity, College, Documents, Archives, Disk Images)
* **Conversion**: Formatted as rules with priorities starting from 6. Keyword parameters match substringContains filters, while extensions match standard lists. Targets map to original relative paths.

---

## 3. Manual Intervention Guide
No manual intervention is required. If a corrupt configuration or failed schema load is encountered, the loader will automatically fallback to loading from `config.json.bak` and restore it as the primary config, preventing any application crashes on start.
