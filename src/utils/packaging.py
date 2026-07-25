import os
import sys
from enum import Enum

class PackageType(Enum):
    SOURCE = "SOURCE"
    DEBIAN = "DEBIAN"
    APPIMAGE = "APPIMAGE"
    FLATPAK = "FLATPAK"

class Capability(Enum):
    GUI = "GUI"
    TRAY = "TRAY"
    NOTIFICATIONS = "NOTIFICATIONS"
    DOWNLOADS_MONITOR = "DOWNLOADS_MONITOR"
    BACKGROUND_MONITOR = "BACKGROUND_MONITOR"
    SYSTEMD_INTEGRATION = "SYSTEMD_INTEGRATION"
    AUTOSTART = "AUTOSTART"

# Capability matrix defining which features are supported on each platform
CAPABILITIES = {
    PackageType.SOURCE: {
        Capability.GUI: True,
        Capability.TRAY: True,
        Capability.NOTIFICATIONS: True,
        Capability.DOWNLOADS_MONITOR: True,
        Capability.BACKGROUND_MONITOR: True,
        Capability.SYSTEMD_INTEGRATION: True,
        Capability.AUTOSTART: True,
    },
    PackageType.DEBIAN: {
        Capability.GUI: True,
        Capability.TRAY: True,
        Capability.NOTIFICATIONS: True,
        Capability.DOWNLOADS_MONITOR: True,
        Capability.BACKGROUND_MONITOR: True,
        Capability.SYSTEMD_INTEGRATION: True,
        Capability.AUTOSTART: True,
    },
    PackageType.APPIMAGE: {
        Capability.GUI: True,
        Capability.TRAY: True,
        Capability.NOTIFICATIONS: True,
        Capability.DOWNLOADS_MONITOR: True,
        Capability.BACKGROUND_MONITOR: True,
        Capability.SYSTEMD_INTEGRATION: True,
        Capability.AUTOSTART: True,
    },
    PackageType.FLATPAK: {
        Capability.GUI: True,
        Capability.TRAY: True,
        Capability.NOTIFICATIONS: True,
        Capability.DOWNLOADS_MONITOR: True,
        Capability.BACKGROUND_MONITOR: False,
        Capability.SYSTEMD_INTEGRATION: False,
        Capability.AUTOSTART: True,
    }
}

def detect_package_type() -> PackageType:
    """
    Detects the current package execution environment:
    - FLATPAK: presence of /.flatpak-info
    - APPIMAGE: presence of APPIMAGE or APPDIR environment variables
    - DEBIAN: execution path starts with /usr/share/smartsort or system prefixes
    - SOURCE: default fallback
    """
    if os.path.exists("/.flatpak-info"):
        return PackageType.FLATPAK
    if os.environ.get("APPIMAGE") or os.environ.get("APPDIR"):
        return PackageType.APPIMAGE
    
    # Check if this script's path is inside the system debian folder
    current_file = os.path.abspath(__file__)
    if current_file.startswith("/usr/share/smartsort") or current_file.startswith("/usr/lib/smartsort"):
        return PackageType.DEBIAN
        
    return PackageType.SOURCE

def has_capability(capability: Capability) -> bool:
    """
    Returns True if the current package type supports the specified capability.
    """
    pkg_type = detect_package_type()
    return CAPABILITIES.get(pkg_type, {}).get(capability, False)

def check_appimage_moved() -> tuple[bool, str, str]:
    """
    Checks if the AppImage has moved since the systemd service was registered.
    Returns (has_moved, current_path, service_path).
    """
    current_appimage = os.environ.get("APPIMAGE")
    if not current_appimage:
        return False, "", ""
        
    from pathlib import Path
    service_file = Path.home() / ".config" / "systemd" / "user" / "smartsort.service"
    if not service_file.exists():
        return False, "", ""
        
    try:
        content = service_file.read_text()
        for line in content.splitlines():
            if line.startswith("ExecStart="):
                parts = line.split("=")
                if len(parts) > 1:
                    cmd_part = parts[1].strip()
                    import shlex
                    cmd_tokens = shlex.split(cmd_part)
                    if cmd_tokens:
                        service_exec = cmd_tokens[0]
                        if service_exec != current_appimage:
                            return True, current_appimage, service_exec
    except Exception:
        pass
        
    return False, "", ""
