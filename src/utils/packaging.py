"""
packaging.py — Package type detection and capability registry for SmartSort.

SmartSort v1.0.3 officially supports Debian-based distributions only (.deb).
SOURCE mode is also supported for development/running directly from source.
"""

import os
from enum import Enum


class Capability(Enum):
    GUI = "gui"
    TRAY = "tray"
    NOTIFICATIONS = "notifications"
    DOWNLOADS_MONITOR = "downloads_monitor"
    BACKGROUND_MONITOR = "background_monitor"
    SYSTEMD_INTEGRATION = "systemd_integration"
    AUTOSTART = "autostart"


class PackageType(Enum):
    DEBIAN = "DEBIAN"
    SOURCE = "SOURCE"


CAPABILITIES = {
    PackageType.DEBIAN: {
        Capability.GUI: True,
        Capability.TRAY: True,
        Capability.NOTIFICATIONS: True,
        Capability.DOWNLOADS_MONITOR: True,
        Capability.BACKGROUND_MONITOR: True,
        Capability.SYSTEMD_INTEGRATION: True,
        Capability.AUTOSTART: True,
    },
    PackageType.SOURCE: {
        Capability.GUI: True,
        Capability.TRAY: True,
        Capability.NOTIFICATIONS: True,
        Capability.DOWNLOADS_MONITOR: True,
        Capability.BACKGROUND_MONITOR: True,
        Capability.SYSTEMD_INTEGRATION: True,
        Capability.AUTOSTART: True,
    },
}


def detect_package_type() -> PackageType:
    """
    Detects the current package execution environment:
    - DEBIAN: execution path starts with /usr/share/smartsort or /usr/lib/smartsort
    - SOURCE: default fallback (running directly from source checkout)
    """
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
