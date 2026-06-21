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
            "autostart": bool
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
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    
                    # Migrate legacy threshold
                    val = config.get("large_file_threshold_gb")
                    if isinstance(val, (int, float)) and val < 10000:
                        config["large_file_threshold_gb"] = int(val * (1024**3))
                        try:
                            shutil.copy2(self.config_path, self.config_path + ".bak")
                        except Exception:
                            pass
                        with open(self.config_path, 'w') as out_f:
                            json.dump(config, out_f, indent=4)
                            
                    self.validate_config(config)
                    return config
        except Exception as e:
            # Try to restore from backup
            bak_path = self.config_path + ".bak"
            if os.path.exists(bak_path):
                try:
                    with open(bak_path, 'r') as f:
                        config = json.load(f)
                        val = config.get("large_file_threshold_gb")
                        if isinstance(val, (int, float)) and val < 10000:
                            config["large_file_threshold_gb"] = int(val * (1024**3))
                        self.validate_config(config)
                        # Restore active file
                        with open(self.config_path, 'w') as out_f:
                            json.dump(config, out_f, indent=4)
                        return config
                except Exception:
                    pass

        # Try to load default config
        if os.path.exists(self.default_path):
            with open(self.default_path, 'r') as f:
                try:
                    config = json.load(f)
                    val = config.get("large_file_threshold_gb")
                    if isinstance(val, (int, float)) and val < 10000:
                        config["large_file_threshold_gb"] = int(val * (1024**3))
                    self.validate_config(config)
                    # Try to save valid default config as current config
                    os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                    with open(self.config_path, 'w') as out_f:
                        json.dump(config, out_f, indent=4)
                    return config
                except Exception:
                    return {}
        return {}

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
                pass # Proceed even if backup creation fails (e.g. read-only filesystem check, though unlikely)

        # 3. Write
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=4)
        
        self.config = config

    def get(self, key, default=None):
        val = self.config.get(key, default)
        if key in ("downloads_folder", "destination_base") and isinstance(val, str):
            if val.startswith("~"):
                return str(Path(val).expanduser())
        return val

    def set(self, key, value):
        new_config = copy.deepcopy(self.config)
        new_config[key] = value
        self.save_config(new_config)

