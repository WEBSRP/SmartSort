# Rule Engine Specification

This document details the rule engine execution, priority rules, syntax matching, and destination path expansions.

---

## 1. Rule Structure

Rules are list-ordered JSON dictionaries containing criteria and actions:

```json
{
    "name": "Organize Images",
    "priority": 10,
    "criteria": {
        "extensions": [".png", ".jpg", ".jpeg"],
        "size_operator": "less_than",
        "size_bytes": 10485760
    },
    "destination": "Pictures/Sorted/{year}/{month}"
}
```

---

## 2. Supported Criteria
- **extensions**: A list of matching filename extensions.
- **keywords**: Case-insensitive substring searches inside filenames.
- **regex**: Advanced Python-regex matching on filenames.
- **size**: Numerical filters matching: `greater_than`, `less_than`, or `equal`.

---

## 3. Dynamic Variables Expansion
SmartSort automatically expands curly-brace placeholders inside destination strings:
- `{extension}`: Resolves to the file extension (e.g. `png`).
- `{filename}`: Resolves to the filename without extension.
- `{year}` / `{month}` / `{day}`: Active date variables corresponding to the transfer execution time.
