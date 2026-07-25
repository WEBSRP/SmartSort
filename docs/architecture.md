# SmartSort System Architecture

This document describes the high-level architecture and design components of the SmartSort organization platform.

---

## 1. High-Level Design

SmartSort is composed of two primary execution modes: the **Background Daemon** (monitoring service) and the **Graphical User Interface (GUI)**. They communicate through shared settings files and system notifications.

```
       [ Downloads Directory ]
                 ↓
         [ Watchdog Monitor ]
                 ↓
          [ Rule Engine ]  ← [ AppPaths (config.json) ]
                 ↓
       [ Organizer Pipeline ]
                 ↓
      [ Files Sorted & Moved ]
```

---

## 2. Core Modules

### A. Central Path Manager (`AppPaths`)
Located in [src/utils/paths.py](file:///home/websrp/SmartSort/src/utils/paths.py), this class centralizes path mapping and ensures strict XDG Base Directory specification compliance:
- `AppPaths.config_file()` resolves settings to `~/.config/smartsort/config.json`.
- `AppPaths.logs_dir()` resolves execution logs to `~/.local/state/smartsort/`.
- Decouples file lookups from system-specific locations, enabling transparent compatibility across Debian, AppImage, Flatpak, and Source installations.

### B. Configuration Manager (`ConfigManager`)
Located in [src/utils/config.py](file:///home/websrp/SmartSort/src/utils/config.py), this module loads, validates, and serializes user preferences and categories:
- Creates `config.json` automatically from the template `config.default.json` on first launch.
- Provides automatic, self-healing settings migration from legacy repository directories to user XDG-compliant locations.

### C. File Monitor (`FileMonitor`)
Located in [src/monitor.py](file:///home/websrp/SmartSort/src/monitor.py), this utilizes the `watchdog` framework to listen to file events in the monitored directory in real-time, executing transfers when new files arrive.

### D. Rule Engine (`RuleEngine`)
Located in [src/rules/engine.py](file:///home/websrp/SmartSort/src/rules/engine.py), it evaluates user-defined rules against file attributes (metadata, size, matching regex).
