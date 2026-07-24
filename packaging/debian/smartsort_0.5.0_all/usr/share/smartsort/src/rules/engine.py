import os
from typing import List, Optional, Tuple
from src.rules.rule import Rule

class RuleEngine:
    def __init__(self, rules: List[Rule]):
        # "Sort by priority. Evaluate highest priority first. First matching rule wins."
        # Lower priority number is evaluated first (e.g. 1 is highest).
        self.rules = sorted([r for r in rules if r.enabled], key=lambda r: r.priority)

    def evaluate_file(self, file_path: str, file_size: int = None) -> Tuple[Optional[Rule], str]:
        """
        Evaluate rules against a file.
        Returns first matching rule and the expanded destination path.
        If no rule matches, returns (None, 'Others/')
        """
        for rule in self.rules:
            if rule.evaluate(file_path, file_size):
                dest = self.expand_variables(rule.destination, file_path)
                return rule, dest
        
        # Fallback if no rule matches
        fallback_dest = self.expand_variables("Others/", file_path)
        return None, fallback_dest

    @staticmethod
    def expand_variables(destination_template: str, file_path: str) -> str:
        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].replace(".", "").upper()
        
        expanded = destination_template
        expanded = expanded.replace("{extension}", ext)
        expanded = expanded.replace("{filename}", filename)
        return expanded
