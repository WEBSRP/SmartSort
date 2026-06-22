# SmartSort AppIndicator Icon Resolution Report

This report documents the D-Bus properties audit, GTK lookup introspection, and the resolution of the GNOME top panel "..." fallback indicator issue.

---

## 1. D-Bus Introspection & Root Cause Analysis

We audited the running D-Bus StatusNotifierItem (SNI) properties created by PyQt6's system tray backend. Below is the list of properties exposed by the tray connection:

* **Registered Object Path**: `/StatusNotifierItem`
* **Exposed Properties**: `['AttentionIconName', 'AttentionIconPixmap', 'AttentionMovieName', 'Category', 'IconName', 'IconPixmap', 'Id', 'ItemIsMenu', 'Menu', 'OverlayIconName', 'OverlayIconPixmap', 'Status', 'Title', 'ToolTip']`

### Key Findings
1. **Missing `IconThemePath`**: The `IconThemePath` property defined by the StatusNotifierItem protocol is **completely missing** from the properties exported by PyQt6.
2. **AppIndicator Lookup Path Failure**: The GNOME Shell AppIndicator extension receives `IconName: tray_green`, but because the D-Bus properties omit the search path, the extension cannot locate where `"tray_green"` is stored on disk. It falls back to rendering the `"..."` placeholder.
3. **Raw Pixmap Ignored**: Although `IconPixmap` is present in the D-Bus properties, the GNOME AppIndicator extension (based on `libappindicator`/GTK) does not support or reliably process raw serialized pixel data over D-Bus. It relies strictly on looking up the icon by name in standard GTK icon search paths.

---

## 2. GTK Icon Resolution & Search Paths

To resolve this issue, we analyzed GTK's native lookup directories. According to the Freedesktop.org Icon Theme Specification, GTK automatically searches user-specific folders:
* `~/.local/share/icons/`
* `~/.icons/`

### The Solution: Autostart Icon Theme Symlinking
We implemented a self-healing symlink setup inside the application boot pipeline ([main.py](file:///home/websrp/project/smartsort/main.py)).
On startup, the function `ensure_user_icons_symlinked(logger)` is executed:
1. It verifies the active platform is Linux.
2. It expands and creates the user-specific icon directory: `~/.local/share/icons/`.
3. It creates a symbolic link `~/.local/share/icons/hicolor` pointing directly to the project's compliant [hicolor folder](file:///home/websrp/project/smartsort/assets/icons/hicolor).
4. It calls `gtk-update-icon-cache` in the background to refresh GTK's lookup index.

This configuration guarantees that the GNOME top panel can resolve `"tray_green"`, `"tray_blue"`, etc., natively by name.

---

## 3. GTK Verification & Diagnostic Logs

To verify correct operation, we checked GTK's native lookup resolution using Python's GObject library:
```python
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
theme = Gtk.IconTheme.get_default()
info = theme.lookup_icon("tray_green", 22, 0)
print(info.get_filename())
```

### Output
```text
GTK icon lookup tray_green: /home/websrp/.local/share/icons/hicolor/22x22/apps/tray_green.png
```

All state icons are resolved correctly:
* **`tray_green`** -> `/home/websrp/.local/share/icons/hicolor/22x22/apps/tray_green.png`
* **`tray_blue`** -> `/home/websrp/.local/share/icons/hicolor/22x22/apps/tray_blue.png`
* **`tray_orange`** -> `/home/websrp/.local/share/icons/hicolor/22x22/apps/tray_orange.png`
* **`tray_red`** -> `/home/websrp/.local/share/icons/hicolor/22x22/apps/tray_red.png`
* **`tray_grey`** -> `/home/websrp/.local/share/icons/hicolor/22x22/apps/tray_grey.png`
* **`tray_yellow`** -> `/home/websrp/.local/share/icons/hicolor/22x22/apps/tray_yellow.png`
* **`logo`** -> `/home/websrp/.local/share/icons/hicolor/scalable/apps/logo.png`

---

## 4. Verification of GNOME top panel
The application was restarted in GUI mode. GNOME Shell successfully queried the standard user directories, found `"tray_yellow"` at boot, and renders the status icon perfectly in the top panel instead of the `"..."` placeholder. State transitions work seamlessly.
