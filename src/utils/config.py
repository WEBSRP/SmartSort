import json
import os
import copy
import shutil
from pathlib import Path

class ConfigManager:
    def __init__(self, config_path="config/config.json", default_path="config/default_config.json"):
        self.config_path = config_path
        self.default_path = default_path
        self.config = self.load_config()

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
            "theme": str
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
            "theme": "system"
        }

        # 2. Try to load default_config.json to override defaults
        if os.path.exists(self.default_path):
            try:
                with open(self.default_path, 'r') as f:
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
        config_path_existed = os.path.exists(self.config_path)

        # 3. Load user config from config_path
        if config_path_existed:
            try:
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                    if isinstance(loaded_config, dict):
                        config_loaded_successfully = True
            except Exception:
                # If reading active config fails, try backup
                bak_path = self.config_path + ".bak"
                if os.path.exists(bak_path):
                    try:
                        with open(bak_path, 'r') as f:
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
            "theme": str
        }

        if config_loaded_successfully:
            for key, expected_type in required_keys.items():
                if key in loaded_config:
                    val = loaded_config[key]
                    if isinstance(val, expected_type):
                        merged_config[key] = copy.deepcopy(val)
                    else:
                        # Log/warn and retain default value for safety
                        pass

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
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, 'w') as f:
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
        if os.path.exists(self.config_path):
            try:
                shutil.copy2(self.config_path, self.config_path + ".bak")
            except Exception:
                pass

        # 3. Write
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
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
                "theme": "system"
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

