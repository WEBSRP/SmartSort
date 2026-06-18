import json
import os

class ConfigManager:
    def __init__(self, config_path="config/config.json", default_path="config/default_config.json"):
        self.config_path = config_path
        self.default_path = default_path
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        elif os.path.exists(self.default_path):
            with open(self.default_path, 'r') as f:
                config = json.load(f)
                self.save_config(config)
                return config
        else:
            return {}

    def save_config(self, config=None):
        if config:
            self.config = config
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()
