import os
import shutil
from typing import List, Dict, Any
from src.rules.rule import Rule

def validate_rules(rules_dicts: list):
    priorities = set()
    for r_dict in rules_dicts:
        try:
            p = int(r_dict.get("priority"))
        except (ValueError, TypeError):
            raise ValueError(f"Rule '{r_dict.get('name')}' priority must be an integer")
        if p < 0:
            raise ValueError(f"Rule '{r_dict.get('name')}' priority cannot be negative")
        if p in priorities:
            raise ValueError(f"Duplicate priority detected: {p}")
        priorities.add(p)
        
        # Test full rule parsing to catch regex errors, invalid sizes, empty destinations, etc.
        Rule.from_dict(r_dict)

def migrate_config_if_needed(config_dict: dict, config_path: str = None) -> bool:
    """
    Checks if legacy 'categories' is present in config.
    If so, converts categories to new rules list, backups config.json to config.json.bak, 
    and returns True (indicating migration occurred).
    """
    if "categories" not in config_dict:
        return False
        
    # Create backup of config.json if path is provided
    if config_path and os.path.exists(config_path):
        try:
            shutil.copy2(config_path, config_path + ".bak")
        except Exception:
            pass
            
    legacy_categories = config_dict["categories"]
    new_rules = []
    
    # 1. Default image rules (Phase 3 quality default rules)
    image_exts = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]
    new_rules.append({
        "id": "img_low",
        "name": "Low Quality Images",
        "enabled": True,
        "priority": 1,
        "conditions": [
            {"type": "extension", "value": image_exts},
            {"type": "size", "operator": "<", "value": "1MB"}
        ],
        "destination": "Pictures/Low_Quality/{extension}"
    })
    new_rules.append({
        "id": "img_med",
        "name": "Medium Quality Images",
        "enabled": True,
        "priority": 2,
        "conditions": [
            {"type": "extension", "value": image_exts},
            {"type": "size", "operator": ">=", "value": "1MB"},
            {"type": "size", "operator": "<", "value": "5MB"}
        ],
        "destination": "Pictures/Medium_Quality/{extension}"
    })
    new_rules.append({
        "id": "img_high",
        "name": "High Quality Images",
        "enabled": True,
        "priority": 3,
        "conditions": [
            {"type": "extension", "value": image_exts},
            {"type": "size", "operator": ">=", "value": "5MB"}
        ],
        "destination": "Pictures/High_Quality/{extension}"
    })
    
    # 2. Iterate and convert categories
    next_priority = 4
    
    category_destinations = {
        "Videos": "Videos",
        "Documents": "Documents",
        "Archives": "Archives",
        "Disk Images": "ISO",
        "Images": "Pictures",
        "Cybersecurity": "Cybersecurity",
        "College": "Documents/College",
    }
    
    for cat_name, cat_data in legacy_categories.items():
        if cat_name == "Images":
            # Replaced by the quality rules above
            continue
            
        dest = category_destinations.get(cat_name, cat_name)
        
        if cat_name == "Videos":
            thresh_gb = config_dict.get("large_file_threshold_gb", 2.5)
            subfolders = cat_data.get("subfolders", {})
            big_dest = subfolders.get("Big_Videos", "Videos/Big_Videos")
            small_dest = subfolders.get("Small_Videos", "Videos")
            exts = cat_data.get("extensions", [".mkv", ".mp4", ".avi", ".mov"])
            
            # Big Video rule
            new_rules.append({
                "id": f"legacy_{cat_name.lower()}_big",
                "name": f"{cat_name} (Big)",
                "enabled": True,
                "priority": next_priority,
                "conditions": [
                    {"type": "extension", "value": exts},
                    {"type": "size", "operator": ">=", "value": f"{thresh_gb}GB"}
                ],
                "destination": big_dest
            })
            next_priority += 1
            
            # Small Video rule
            new_rules.append({
                "id": f"legacy_{cat_name.lower()}_small",
                "name": cat_name,
                "enabled": True,
                "priority": next_priority,
                "conditions": [
                    {"type": "extension", "value": exts}
                ],
                "destination": small_dest
            })
            next_priority += 1
            continue

        conds = []
        if "extensions" in cat_data:
            conds.append({"type": "extension", "value": cat_data["extensions"]})
        if "keywords" in cat_data:
            conds.append({"type": "filename", "value": cat_data["keywords"]})
            
        new_rules.append({
            "id": f"legacy_{cat_name.lower()}",
            "name": cat_name,
            "enabled": True,
            "priority": next_priority,
            "conditions": conds,
            "destination": dest
        })
        next_priority += 1
        
    config_dict["rules"] = new_rules
    if "categories" in config_dict:
        del config_dict["categories"]
    return True

class RuleManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        
        # Trigger legacy migration if categories key exists
        if hasattr(self.config_manager, "config") and self.config_manager.config:
            config = self.config_manager.config
            if migrate_config_if_needed(config, getattr(self.config_manager, "config_path", None)):
                self.config_manager.save_config(config)
            
        self.rules = self.load_rules()

    def load_rules(self) -> List[Rule]:
        raw_rules = self.config_manager.get("rules")
        if raw_rules is None:
            # Maybe it has legacy categories? (typical in tests using legacy categories mock config)
            categories = self.config_manager.get("categories")
            if categories is not None:
                mock_config = {
                    "categories": categories,
                    "large_file_threshold_gb": self.config_manager.get("large_file_threshold_gb", 2.5)
                }
                migrate_config_if_needed(mock_config)
                raw_rules = mock_config.get("rules", [])
            else:
                raw_rules = []
                
        rules_list = []
        for r_dict in raw_rules:
            try:
                rules_list.append(Rule.from_dict(r_dict))
            except Exception as e:
                print(f"Skipping loading of invalid rule: {r_dict}. Error: {e}")
        return sorted(rules_list, key=lambda r: r.priority)

    def save_rules(self, rules_list: List[Rule] = None):
        if rules_list is None:
            rules_list = self.rules
            
        # Validate prior to saving
        rules_dicts = [r.to_dict() for r in rules_list]
        validate_rules(rules_dicts)
        
        self.config_manager.set("rules", rules_dicts)
        self.rules = sorted(rules_list, key=lambda r: r.priority)

    def add_rule(self, rule: Rule):
        self.rules.append(rule)
        self.save_rules()

    def delete_rule(self, rule_id: str):
        self.rules = [r for r in self.rules if r.id != rule_id]
        self.save_rules()

    def update_rule(self, updated_rule: Rule):
        for idx, r in enumerate(self.rules):
            if r.id == updated_rule.id:
                self.rules[idx] = updated_rule
                break
        self.save_rules()
