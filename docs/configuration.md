# Configuration Guide

This document describes the structure, default options, and paths of the SmartSort configuration.

---

## 1. Config Base Directory

Following the XDG base directory specification, SmartSort configuration is located at:
```bash
~/.config/smartsort/config.json
```
If `$XDG_CONFIG_HOME` is custom-defined, it resolves to `$XDG_CONFIG_HOME/smartsort/config.json`.

---

## 2. Configuration Options

Below are the options managed inside `config.json`:

```json
{
    "downloads_folder": "~/Downloads",
    "destination_base": "~",
    "large_file_threshold_gb": 2684354560,
    "enable_hash_verification": true,
    "enable_notifications": true,
    "enable_duplicate_detection": true,
    "conflict_resolution": "rename",
    "categories": {
        "Videos": {
            "extensions": [".mkv", ".mp4", ".avi", ".mov"]
        },
        "Documents": {
            "extensions": [".pdf", ".docx", ".pptx", ".xlsx"]
        }
    },
    "rules": [],
    "start_minimized": false,
    "autostart": false,
    "theme": "system"
}
```

- **downloads_folder**: Paths starting with `~` are expanded automatically at runtime.
- **large_file_threshold_gb**: Size threshold in bytes (e.g. 2.5 GB).
- **conflict_resolution**: Decides handling of filename collisions. Supported policies: `rename` (appends incremental numeric tags), `overwrite`, or `skip`.
