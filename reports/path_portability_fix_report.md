# SmartSort Path Portability Improvement Report

## 1. Why the Change Was Needed
Previously, the default configuration file `config/default_config.json` contained hardcoded absolute paths:
```json
{
  "downloads_folder": "/home/websrp/Downloads",
  "destination_base": "/home/websrp"
}
```
This hardcoding restricted the application's out-of-the-box functionality to the original developer's machine (`websrp`). Any other user (e.g., `alice`, `bob`, `john`) had to manually edit these configurations to point to their own home directory before the application could start. 

To improve portability and installation experience:
* Hardcoded user-specific directories are replaced with standard Unix tilde (`~`) prefixes.
* SmartSort now automatically resolves the tilde (`~`) character to the active user's home folder at runtime.
* Existing user-defined custom configuration settings (which may contain absolute paths) are preserved to maintain backward compatibility.

---

## 2. How Path Expansion Works
When the application starts, it reads its settings via the configuration manager. The tilde expansion occurs at runtime in a centralized manner:
* **Storage Portable Format**: The default settings are stored with the relative prefix: `~/Downloads` and `~`.
* **Runtime Path Resolution**: The `ConfigManager` class in `src/utils/config.py` intercepts requests for path-related configuration parameters.
* **Tilde Detection & pathlib Integration**:
  If the configuration keys `downloads_folder` or `destination_base` are queried via the `get()` method and their value starts with `~`, SmartSort expands the path using `pathlib.Path.expanduser()`.
  ```python
  def get(self, key, default=None):
      val = self.config.get(key, default)
      if key in ("downloads_folder", "destination_base") and isinstance(val, str):
          if val.startswith("~"):
              return str(Path(val).expanduser())
      return val
  ```
  This resolves paths dynamically:
  * For user `alice`: `~/Downloads` $\rightarrow$ `/home/alice/Downloads`
  * For user `bob`: `~/Downloads` $\rightarrow$ `/home/bob/Downloads`
* **Backward Compatibility**: If a user has already customized their configuration file with absolute paths (e.g., `/home/alice/CustomDownloads`), the value does not start with `~`. It is returned exactly as stored, ensuring existing customizations are fully respected.

---

## 3. Files Modified
1. **[config/default_config.json](file:///home/websrp/project/smartsort/config/default_config.json)**:
   Updated default directories from `/home/websrp/...` to portable paths (`~/Downloads` and `~`).
2. **[src/utils/config.py](file:///home/websrp/project/smartsort/src/utils/config.py)**:
   Imported `pathlib.Path` and added dynamic tilde-expansion logic for path configuration keys in `ConfigManager.get()`.
3. **[tests/test_core.py](file:///home/websrp/project/smartsort/tests/test_core.py)**:
   Added `test_path_portability_expansion` to verify:
   * Automatic `~/Downloads` and `~` expansion to the running user's actual home directory.
   * Persistence of raw configurations containing tilde strings on write operations.
   * Preservation of custom absolute path configurations without modifying them.
4. **[README.md](file:///home/websrp/project/smartsort/README.md)**:
   Documented the automatic path expansion behavior and added a reference to this report.

---

## 4. Test Results
The automated test suite runs successfully within the virtual environment:
```bash
$ PYTHONPATH=. ./smartsort/bin/pytest
```

Output:
```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-8.2.2, pluggy-1.6.0
rootdir: /home/websrp/project/smartsort
collected 15 items                                                             

tests/test_core.py ...............                                       [100%]

============================== 15 passed in 0.07s ==============================
```

All 15 tests, including config loading, priority matching, and the newly implemented path portability tests, passed successfully.
