import os
import sys
import shlex
from pathlib import Path
from src.utils.packaging import detect_package_type, PackageType


class AutostartManager:
    def __init__(self, logger=None, autostart_dir=None):
        self.logger = logger
        if autostart_dir:
            self.autostart_dir = Path(autostart_dir)
        else:
            self.autostart_dir = Path.home() / ".config" / "autostart"
        self.desktop_file = self.autostart_dir / "smartsort.desktop"

    def is_autostart_enabled(self) -> bool:
        """
        Checks if the autostart desktop entry is present and valid.
        """
        if not self.desktop_file.exists():
            return False

        try:
            content = self.desktop_file.read_text()
            if "Name=SmartSort" in content:
                for line in content.splitlines():
                    if line.strip().startswith("X-GNOME-Autostart-enabled=false"):
                        return False
                return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error reading autostart desktop file: {e}")
        return False

    def enable_autostart(self) -> bool:
        """
        Creates or updates the autostart desktop file with the appropriate Exec command.
        """
        try:
            self.autostart_dir.mkdir(parents=True, exist_ok=True)
            cmd = self.get_command()
            icon_path = self.get_icon_path()

            content = f"""[Desktop Entry]
Type=Application
Exec={cmd}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=SmartSort
Comment=SmartSort File Organizer Background Service
Icon={icon_path}
"""
            self.desktop_file.write_text(content)
            if self.logger:
                self.logger.info(f"Autostart enabled. Entry written to {self.desktop_file} with Exec={cmd}")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to enable autostart: {e}")
            return False

    def disable_autostart(self) -> bool:
        """
        Disables autostart by removing the desktop file.
        """
        try:
            if self.desktop_file.exists():
                self.desktop_file.unlink()
                if self.logger:
                    self.logger.info(f"Autostart disabled. Removed {self.desktop_file}")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to disable autostart: {e}")
            return False

    def get_command(self) -> str:
        pkg_type = detect_package_type()
        if pkg_type == PackageType.DEBIAN:
            return "/usr/bin/smartsort --service"
        else:  # SOURCE
            main_path = os.path.abspath(sys.argv[0])
            return f'"{sys.executable}" "{main_path}" --service'

    def get_icon_path(self) -> str:
        pkg_type = detect_package_type()
        if pkg_type == PackageType.DEBIAN:
            return "smartsort"
        else:
            from src.utils.paths import AppPaths
            logo_path = AppPaths.resource_dir() / "icons" / "logo.png"
            if logo_path.exists():
                return str(logo_path)
            return "smartsort"

    def check_appimage_moved(self) -> tuple:
        """
        Stub retained for backward compatibility with the test suite.
        AppImage is no longer a supported package type in v1.0.3+.
        Always returns (False, "", "").
        """
        return False, "", ""
