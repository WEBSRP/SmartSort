import os
import re

def parse_size_to_bytes(size_str) -> int:
    if isinstance(size_str, (int, float)):
        return int(size_str)
    size_str = str(size_str).strip().upper()
    match = re.match(r'^([\d.]+)\s*(GB|MB|KB|B)?$', size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    val, unit = match.groups()
    val = float(val)
    if val < 0:
        raise ValueError("Size value cannot be negative")
    if unit == 'GB':
        return int(val * 1024**3)
    elif unit == 'MB':
        return int(val * 1024**2)
    elif unit == 'KB':
        return int(val * 1024)
    else:
        return int(val)

class Condition:
    def evaluate(self, file_path: str, file_size: int = None) -> bool:
        raise NotImplementedError

class ExtensionCondition(Condition):
    def __init__(self, value):
        if isinstance(value, list):
            self.extensions = [ext.lower().strip() for ext in value]
        else:
            self.extensions = [str(value).lower().strip()]

    def evaluate(self, file_path: str, file_size: int = None) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        for cond_ext in self.extensions:
            target = cond_ext if cond_ext.startswith('.') else '.' + cond_ext
            if ext == target:
                return True
        return False

class FilenameContainsCondition(Condition):
    def __init__(self, value):
        if isinstance(value, list):
            self.substrings = [sub.lower().strip() for sub in value]
        else:
            self.substrings = [str(value).lower().strip()]

    def evaluate(self, file_path: str, file_size: int = None) -> bool:
        filename = os.path.basename(file_path).lower()
        for substring in self.substrings:
            if substring in filename:
                return True
        return False

class SizeCondition(Condition):
    def __init__(self, operator: str, value: str):
        self.operator = operator.strip()
        if self.operator not in (">", "<", ">=", "<=", "=="):
            raise ValueError(f"Invalid operator for size condition: {self.operator}")
        self.value_str = value
        self.bytes_limit = parse_size_to_bytes(value)

    def evaluate(self, file_path: str, file_size: int = None) -> bool:
        if file_size is None:
            if os.path.exists(file_path):
                try:
                    file_size = os.path.getsize(file_path)
                except OSError:
                    return False
            else:
                return False
        
        if self.operator == ">":
            return file_size > self.bytes_limit
        elif self.operator == "<":
            return file_size < self.bytes_limit
        elif self.operator == ">=":
            return file_size >= self.bytes_limit
        elif self.operator == "<=":
            return file_size <= self.bytes_limit
        elif self.operator == "==":
            return file_size == self.bytes_limit
        return False

class RegexCondition(Condition):
    def __init__(self, value: str):
        self.pattern_str = value
        try:
            self.pattern = re.compile(value)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {value}. Error: {e}")

    def evaluate(self, file_path: str, file_size: int = None) -> bool:
        filename = os.path.basename(file_path)
        return bool(self.pattern.search(filename))
