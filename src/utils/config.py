import json
import copy
import shutil
from pathlib import Path
from src.utils.paths import AppPaths

def get_cache_dir() -> Path:
    """Returns the XDG cache directory (backwards compatibility wrapper)."""
    return AppPaths.cache_dir()

def get_user_data_dir() -> Path:
    """Returns the XDG user data directory (backwards compatibility wrapper)."""
    return AppPaths.data_dir()

class ConfigManager:
    """
    Manages loading, validation, merging, and saving of application configurations.
    """
    def __init__(self, config_path=None, default_path=None):
        is_testing = "PYTEST_CURRENT_TEST" in os_environ_check()
        
        # 1. Determine paths
        if config_path:
            self.config_path = Path(config_path).resolve()
        else:
            self.config_path = AppPaths.config_file()
            
        if default_path:
            self.default_path = Path(default_path).resolve()
        else:
            self.default_path = AppPaths.default_config()

        # Ensure active custom config parent directory exists (for custom paths/testing)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # 2. Migrate existing user settings/logs if appropriate
        if not is_testing or "pytest" in os_environ_check().get("XDG_CONFIG_HOME", ""):
            self._migrate_old_paths()

        # 3. First launch check: Copy config.default.json to config.json if missing
        if self.config_path and self.default_path and not self.config_path.exists():
            if self.default_path.exists():
                try:
                    shutil.copy2(self.default_path, self.config_path)
                except Exception:
                    pass

        # Warm up optional XDG directories, but do not make configuration loading
        # fail on restricted/read-only home directories.
        try:
            AppPaths.cache_dir()
            AppPaths.data_dir()
        except OSError:
            pass

        self.config = self.load_config()

    def _migrate_old_paths(self):
        """
        Migrates existing user settings (config.json) and logs from the legacy
        repository locations to XDG-compliant base directories.
        """
        # Determine the bundle root which corresponds to the repository root
        # when running from source.
        bundle_root = AppPaths._bundle_root()
        old_config = bundle_root / "config" / "config.json"
        old_bak = bundle_root / "config" / "config.json.bak"
        
        # Migrate Configuration
        if old_config.is_file() and not self.config_path.exists():
            try:
                # Copy config.json to the new location
                shutil.copy2(old_config, self.config_path)
                
                # Copy backup config if present
                if old_bak.is_file():
                    shutil.copy2(old_bak, self.config_path.with_suffix(".json.bak"))
                
                # Delete the old files if they are writeable
                old_config.unlink(missing_ok=True)
                old_bak.unlink(missing_ok=True)
            except Exception:
                pass
                
        # Migrate Logs
        old_logs_dir = bundle_root / "logs"
        if old_logs_dir.is_dir():
            new_logs_dir = AppPaths.logs_dir()
            try:
                # Copy all log files to the new XDG state directory
                for log_file in old_logs_dir.glob("*.log"):
                    if log_file.is_file():
                        shutil.copy2(log_file, new_logs_dir / log_file.name)
                        log_file.unlink(missing_ok=True)
                
                # Remove old logs directory if empty or after cleaning
                if old_logs_dir.exists() and not any(old_logs_dir.iterdir()):
                    old_logs_dir.rmdir()
            except Exception:
                pass

    def validate_config(self, config):
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a JSON object (dict)")
        
        # Check required/expected keys and their types
        required_keys = {
            "downloads_folder": str,
            "destination_base": str,
            "large_file_threshold_gb": (int, float),
            "enable_hash_verification": bool,
            "enable_notifications": bool,
            "enable_duplicate_detection": bool,
            "conflict_resolution": str,
            "categories": dict,
            "rules": list,
            "start_minimized": bool,
            "autostart": bool,
            "theme": str,
            "smart_filename_cleanup": bool,
            "filename_min_length": int,
            "filename_max_length": int
        }
        for key, expected_type in required_keys.items():
            if key in config:
                val = config[key]
                if not isinstance(val, expected_type):
                    type_names = expected_type.__name__ if not isinstance(expected_type, tuple) else " or ".join(t.__name__ for t in expected_type)
                    raise ValueError(f"Key '{key}' must be of type {type_names}, got {type(val).__name__}")
        
        # Validate categories structure
        if "categories" in config:
            for cat_name, cat_data in config["categories"].items():
                if not isinstance(cat_data, dict):
                    raise ValueError(f"Category '{cat_name}' must be a JSON object (dict)")
                valid_cat_keys = {"extensions", "subfolders", "keywords"}
                for k in cat_data.keys():
                    if k not in valid_cat_keys:
                        raise ValueError(f"Category '{cat_name}' has invalid key '{k}'. Only {valid_cat_keys} are allowed.")
                if "extensions" in cat_data:
                    if not isinstance(cat_data["extensions"], list) or not all(isinstance(x, str) for x in cat_data["extensions"]):
                        raise ValueError(f"Category '{cat_name}' extensions must be a list of strings")
                if "keywords" in cat_data:
                    if not isinstance(cat_data["keywords"], list) or not all(isinstance(x, str) for x in cat_data["keywords"]):
                        raise ValueError(f"Category '{cat_name}' keywords must be a list of strings")
                if "subfolders" in cat_data:
                    if not isinstance(cat_data["subfolders"], dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in cat_data["subfolders"].items()):
                        raise ValueError(f"Category '{cat_name}' subfolders must be a dictionary of strings to strings")

    def load_config(self):
        # 1. Define complete set of defaults
        defaults = {
            "downloads_folder": "~/Downloads",
            "destination_base": "~",
            "large_file_threshold_gb": 2.5,
            "enable_hash_verification": True,
            "enable_notifications": True,
            "enable_duplicate_detection": True,
            "conflict_resolution": "rename",
            "categories": {
                "Videos": {
                    "extensions": [".mkv", ".mp4", ".avi", ".mov"],
                    "subfolders": {
                        "Big_Videos": "Videos/Big_Videos",
                        "Small_Videos": "Videos"
                    }
                },
                "Documents": {
                    "extensions": [".pdf", ".docx", ".pptx", ".xlsx"]
                },
                "Archives": {
                    "extensions": [".zip", ".rar", ".7z", ".tar.gz"]
                },
                "Disk Images": {
                    "extensions": [".iso"]
                },
                "Images": {
                    "extensions": [".jpg", ".jpeg", ".png", ".webp"]
                },
                "Cybersecurity": {
                    "keywords": ["nmap", "burp", "wireshark", "metasploit", "rockyou", "wordlist", "kali", "parrot"]
                },
                "College": {
                    "keywords": ["assignment", "lecture", "lab", "semester", "notes", "ppt"]
                }
            },
            "rules": [],
            "start_minimized": False,
            "autostart": False,
            "theme": "system",
            "smart_filename_cleanup": False,
            "filename_min_length": 4,
            "filename_max_length": 80
        }

        # 2. Try to load config.default.json to override defaults
        if self.default_path.is_file():
            try:
                with self.default_path.open('r') as f:
                    file_defaults = json.load(f)
                    if isinstance(file_defaults, dict):
                        for k, v in file_defaults.items():
                            defaults[k] = copy.deepcopy(v)
            except Exception:
                pass

        # Migrate threshold in defaults if it is in GB representation
        val = defaults.get("large_file_threshold_gb")
        if isinstance(val, (int, float)) and val < 10000:
            defaults["large_file_threshold_gb"] = int(val * (1024**3))

        loaded_config = {}
        config_loaded_successfully = False
        config_path_existed = self.config_path.is_file()

        # 3. Load user config from config_path
        if config_path_existed:
            try:
                with self.config_path.open('r') as f:
                    loaded_config = json.load(f)
                    if isinstance(loaded_config, dict):
                        config_loaded_successfully = True
            except Exception:
                # If reading active config fails, try backup
                bak_path = self.config_path.with_suffix(".json.bak")
                if bak_path.is_file():
                    try:
                        with bak_path.open('r') as f:
                            loaded_config = json.load(f)
                            if isinstance(loaded_config, dict):
                                config_loaded_successfully = True
                    except Exception:
                        pass

        # 4. Merge loaded_config with defaults, validating type of each key
        merged_config = copy.deepcopy(defaults)
        
        required_keys = {
            "downloads_folder": str,
            "destination_base": str,
            "large_file_threshold_gb": (int, float),
            "enable_hash_verification": bool,
            "enable_notifications": bool,
            "enable_duplicate_detection": bool,
            "conflict_resolution": str,
            "categories": dict,
            "rules": list,
            "start_minimized": bool,
            "autostart": bool,
            "theme": str,
            "smart_filename_cleanup": bool,
            "filename_min_length": int,
            "filename_max_length": int
        }

        if config_loaded_successfully:
            for key, expected_type in required_keys.items():
                if key in loaded_config:
                    val = loaded_config[key]
                    if isinstance(val, expected_type):
                        merged_config[key] = copy.deepcopy(val)

        # Migrate legacy threshold in merged config
        val = merged_config.get("large_file_threshold_gb")
        if isinstance(val, (int, float)) and val < 10000:
            merged_config["large_file_threshold_gb"] = int(val * (1024**3))

        # 5. Save config if missing, failed to load, or missing keys/type-healed
        needs_write = (not config_path_existed) or (not config_loaded_successfully)
        if not needs_write:
            for key in required_keys:
                if key not in loaded_config or loaded_config[key] != merged_config[key]:
                    needs_write = True
                    break
        
        if needs_write:
            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with self.config_path.open('w') as f:
                    json.dump(merged_config, f, indent=4)
            except Exception:
                pass

        return merged_config

    def save_config(self, config=None):
        if config is None:
            config = self.config
        
        # 1. Validate
        self.validate_config(config)
        
        # 2. Backup existing config
        if self.config_path.is_file():
            try:
                shutil.copy2(self.config_path, self.config_path.with_suffix(".json.bak"))
            except Exception:
                pass

        # 3. Write
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open('w') as f:
            json.dump(config, f, indent=4)
        
        self.config = config

    def get(self, key, default=None):
        val = self.config.get(key)
        if val is None:
            val = default
        if val is None:
            # Last-resort defaults dictionary
            defaults = {
                "downloads_folder": "~/Downloads",
                "destination_base": "~",
                "large_file_threshold_gb": 2.5,
                "enable_hash_verification": True,
                "enable_notifications": True,
                "enable_duplicate_detection": True,
                "conflict_resolution": "rename",
                "categories": {},
                "rules": [],
                "start_minimized": False,
                "autostart": False,
                "theme": "system",
                "smart_filename_cleanup": False,
                "filename_min_length": 4,
                "filename_max_length": 80
            }
            val = defaults.get(key)
            if key == "large_file_threshold_gb" and isinstance(val, (int, float)) and val < 10000:
                val = int(val * (1024**3))
        if key in ("downloads_folder", "destination_base") and isinstance(val, str):
            if val.startswith("~"):
                return str(Path(val).expanduser())
        return val

    def set(self, key, value):
        new_config = copy.deepcopy(self.config)
        new_config[key] = value
        self.save_config(new_config)

def os_environ_check():
    import os
    return os.environ
