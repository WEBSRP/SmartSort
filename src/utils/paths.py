import os
from pathlib import Path

class AppPaths:
    """
    Central manager for all application filesystem paths, following the
    XDG Base Directory Specification on Linux.
    """

    @staticmethod
    def _bundle_root() -> Path:
        """Returns the base directory of the active application bundle."""
        import sys
        if hasattr(sys, "argv") and sys.argv and sys.argv[0]:
            try:
                argv_path = Path(sys.argv[0]).resolve()
                if argv_path.name in ("main.py", "smartsort"):
                    return argv_path.parent
            except Exception:
                pass
        # paths.py is at src/utils/paths.py, so parent.parent.parent is the bundle root.
        return Path(__file__).resolve().parent.parent.parent

    @classmethod
    def resource_dir(cls) -> Path:
        """
        Returns the directory containing static application resources (assets/icons/etc.).
        """
        return cls._bundle_root() / "assets"

    @classmethod
    def default_config(cls) -> Path:
        """
        Returns the path to the read-only default configuration template file.
        """
        return cls._bundle_root() / "config" / "config.default.json"

    @staticmethod
    def config_dir() -> Path:
        """
        Returns the XDG-compliant configuration directory (~/.config/smartsort/).
        """
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            path = Path(xdg_config) / "smartsort"
        else:
            path = Path.home() / ".config" / "smartsort"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def config_file(cls) -> Path:
        """
        Returns the path to the active user configuration file.
        """
        return cls.config_dir() / "config.json"

    @staticmethod
    def logs_dir() -> Path:
        """
        Returns the XDG-compliant logs/state directory (~/.local/state/smartsort/).
        """
        xdg_state = os.environ.get("XDG_STATE_HOME")
        if xdg_state:
            path = Path(xdg_state) / "smartsort"
        else:
            path = Path.home() / ".local" / "state" / "smartsort"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def data_dir() -> Path:
        """
        Returns the XDG-compliant user data directory (~/.local/share/smartsort/).
        """
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            path = Path(xdg_data) / "smartsort"
        else:
            path = Path.home() / ".local" / "share" / "smartsort"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def cache_dir() -> Path:
        """
        Returns the XDG-compliant user cache directory (~/.cache/smartsort/).
        """
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            path = Path(xdg_cache) / "smartsort"
        else:
            path = Path.home() / ".cache" / "smartsort"
        path.mkdir(parents=True, exist_ok=True)
        return path
