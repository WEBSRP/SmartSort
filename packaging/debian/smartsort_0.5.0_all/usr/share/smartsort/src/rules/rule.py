import re
from typing import List, Dict, Any
from src.rules.conditions import (
    Condition, ExtensionCondition, FilenameContainsCondition,
    SizeCondition, RegexCondition
)

class Rule:
    def __init__(self, id: str, name: str, enabled: bool, priority: int, conditions: List[Condition], destination: str):
        self.id = id
        self.name = name
        self.enabled = enabled
        self.priority = priority
        self.conditions = conditions
        self.destination = destination

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Rule':
        rule_id = str(data.get("id", ""))
        name = str(data.get("name", ""))
        enabled = bool(data.get("enabled", True))
        
        try:
            priority = int(data.get("priority", 99))
        except (ValueError, TypeError):
            raise ValueError("Priority must be an integer")
            
        destination = str(data.get("destination", "")).strip()
        
        if not destination:
            raise ValueError("Destination cannot be empty")
            
        # Check destination placeholders
        placeholders = re.findall(r'\{([^}]+)\}', destination)
        allowed = {"extension", "filename"}
        for p in placeholders:
            if p not in allowed:
                raise ValueError(f"Invalid placeholder: {{{p}}}. Only {{extension}} and {{filename}} are allowed.")

        cond_list = []
        raw_conds = data.get("conditions", [])
        for c in raw_conds:
            c_type = str(c.get("type", "")).lower().strip()
            val = c.get("value")
            if val is None:
                raise ValueError(f"Condition '{c_type}' value is missing")
                
            if c_type == "extension":
                cond_list.append(ExtensionCondition(val))
            elif c_type in ("filename_contains", "filename", "contains"):
                cond_list.append(FilenameContainsCondition(val))
            elif c_type == "size":
                operator = c.get("operator", "")
                if not operator:
                    raise ValueError("Size condition requires 'operator'")
                cond_list.append(SizeCondition(operator, val))
            elif c_type == "regex":
                cond_list.append(RegexCondition(str(val)))
            else:
                raise ValueError(f"Unsupported condition type: {c_type}")

        return cls(rule_id, name, enabled, priority, cond_list, destination)

    def evaluate(self, file_path: str, file_size: int = None) -> bool:
        if not self.enabled:
            return False
        if not self.conditions:
            return True
        return all(c.evaluate(file_path, file_size) for c in self.conditions)

    def to_dict(self) -> Dict[str, Any]:
        raw_conds = []
        for c in self.conditions:
            if isinstance(c, ExtensionCondition):
                raw_conds.append({"type": "extension", "value": c.extensions})
            elif isinstance(c, FilenameContainsCondition):
                raw_conds.append({"type": "filename", "value": c.substrings})
            elif isinstance(c, SizeCondition):
                raw_conds.append({"type": "size", "operator": c.operator, "value": c.value_str})
            elif isinstance(c, RegexCondition):
                raw_conds.append({"type": "regex", "value": c.pattern_str})
        
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "priority": self.priority,
            "conditions": raw_conds,
            "destination": self.destination
        }
