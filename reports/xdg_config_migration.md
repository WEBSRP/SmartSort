# XDG Configuration Migration Report

This report documents the migration of SmartSort configuration and logging storage to comply with the Linux XDG Base Directory Specification.

---

## 1. Compliance Details

SmartSort stores all user-generated settings and execution state strictly under XDG base directories, completely decoupling local configuration from the source repository.

### Configuration Storage
- **XDG Target Path**: `$XDG_CONFIG_HOME/smartsort/config.json`
- **Fallback Path**: `~/.config/smartsort/config.json`
- **Behavior**: Loaded and saved dynamically.

### Log Storage
- **XDG Target Path**: `$XDG_STATE_HOME/smartsort/`
- **Fallback Path**: `~/.local/state/smartsort/`
- **Behavior**: Daily rotated log files (`smartsort_YYYYMMDD.log`) are stored here, and old files are cleaned up after 7 days (retention policy).

---

## 2. Automatic Migration Logic

To support existing users smoothly without losing settings:
1. **Startup Check**: During boot, `ConfigManager` checks if the legacy repository settings file `config/config.json` exists.
2. **Settings Copy**: If it exists and the XDG target file is not present, it copies the settings (and backups `config.json.bak`) to the new XDG config directory.
3. **Log Relocation**: It scans the legacy `logs/` directory in the repository root and moves all log files to the XDG state directory, then deletes the old empty folders.
4. **Cleanup**: Once copied, the legacy files inside the repository are deleted to maintain git tree hygiene.
5. **Fallbacks**: If no legacy configuration is found, `ConfigManager` copies the read-only template `config.default.json` to the active XDG config path on first launch.
