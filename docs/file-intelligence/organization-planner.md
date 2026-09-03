# SmartSort File Intelligence Engine: Organization Planner

## 1. Overview & Objectives

The **Organization Planner** converts high-level classification results (`ClassificationResult`) into safe, canonical, and structured filesystem paths (`OrganizationProposal`).

It bridges the intelligence system with SmartSort's physical organization engines (`DirectoryOrganizer` and `FileOrganizer`).

---

## 2. Planning Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. USER RULE EVALUATION (Highest Precedence)                                │
│    - Evaluates existing RuleEngine rules first                              │
│    - If a user rule matches, generates proposal with `is_rule_override=True`│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (If no explicit user rule matches)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. INTELLIGENCE HIERARCHY SYNTHESIS                                         │
│    - Combines Domain + Course/Project Subcategory + Section Category        │
│    - E.g. Domain='College', Subcategory='DBMS', Section='Lectures'          │
│      $\rightarrow$ Relative Path: `College/DBMS/Lectures/`                   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. PATH SANITIZATION & NORMALIZATION                                        │
│    - Strips illegal Linux path characters (`\0`, control chars, invalid URI)│
│    - Resolves relative path segments (`..`, `./`) to prevent directory traversal│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. BOUNDARY CONTAINMENT VERIFICATION                                        │
│    - Verifies resolved destination path remains strictly inside target root │
│    - `os.path.commonpath([root_dir, target_path]) == root_dir`              │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. EMISSION OF `OrganizationProposal`                                       │
│    - Includes source path, target path, confidence score, and evidence list │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Path Generation Rules

### 3.1 Academic Hierarchy Synthesis
- If domain is `College`:
  - Segment 1: `College`
  - Segment 2: Identified Subject/Course (e.g. `DBMS`, `Operating_Systems`, `CS101`) or `General`
  - Segment 3: Document Subtype (`Lectures`, `Assignments`, `Labs`, `Exams`, `Notes`)
  - Target Path: `{Root}/College/{Subject}/{Subtype}/{Filename}`

### 3.2 Project Hierarchy Synthesis
- If domain is `Projects`:
  - Segment 1: `Projects`
  - Segment 2: Identified Project Name (e.g. `SmartSort`, `ECommerceApp`)
  - Segment 3: Resource Subtype (`Source`, `Documentation`, `Design`, `Releases`)
  - Target Path: `{Root}/Projects/{Project_Name}/{Subtype}/{Filename}`

### 3.3 Cybersecurity Hierarchy Synthesis
- If domain is `Cybersecurity`:
  - Segment 1: `Cybersecurity`
  - Segment 2: Tool or Category (`Tools`, `Reports`, `Wordlists`, `Captures`, `Exploits`)
  - Target Path: `{Root}/Cybersecurity/{Category}/{Filename}`

### 3.4 Fallback and Low-Confidence Handling
- If `confidence_score < 0.35` (`ConfidenceLevel.UNKNOWN`):
  - Fall back to standard extension-based categorization: `{Root}/Others/{Filename}` or `{Root}/Documents/{Filename}`
  - Prevents erroneous cluttering of specialized project/academic folders.

---

## 4. Integration with User Rule Engine

To preserve user agency, SmartSort's user-configured rules in `RuleManager` are evaluated before intelligence proposals:

```python
class OrganizationPlanner:
    def __init__(self, rule_manager: RuleManager, config: ConfigManager):
        self.rule_manager = rule_manager
        self.config = config
        self.rule_engine = RuleEngine(rule_manager.rules)

    def plan_file(self, file_context: FileContext, root_dir: str) -> OrganizationProposal:
        # 1. Check custom user rules first
        rule, relative_dest = self.rule_engine.evaluate_file(
            file_context.path, file_context.size_bytes
        )
        if rule is not None:
            target_path = os.path.abspath(os.path.join(root_dir, relative_dest, file_context.filename))
            self._validate_boundary(root_dir, target_path)
            return OrganizationProposal(
                source_path=file_context.path,
                target_path=target_path,
                relative_target=os.path.join(relative_dest, file_context.filename),
                domain=rule.name,
                hierarchy_segments=[rule.name],
                confidence_level=ConfidenceLevel.CONFIRMED,
                confidence_score=1.0,
                evidence=[EvidenceItem(
                    signal_type=SignalType.FILENAME_TOKEN,
                    description=f"Matched custom user rule: '{rule.name}' (Priority {rule.priority})",
                    weight=1.0,
                    source_field="rules"
                )],
                is_rule_override=True,
                rule_name=rule.name
            )

        # 2. Generate intelligent proposal
        relative_target = os.path.join(
            file_context.classification_domain,
            *file_context.subcategories,
            file_context.filename
        )
        target_path = os.path.abspath(os.path.join(root_dir, relative_target))
        self._validate_boundary(root_dir, target_path)

        return OrganizationProposal(
            source_path=file_context.path,
            target_path=target_path,
            relative_target=relative_target,
            domain=file_context.classification_domain,
            hierarchy_segments=[file_context.classification_domain] + file_context.subcategories,
            confidence_level=file_context.confidence,
            confidence_score=file_context.confidence_score,
            evidence=file_context.evidence_list,
            is_rule_override=False
        )

    def _validate_boundary(self, root_dir: str, target_path: str):
        root_abs = os.path.abspath(root_dir)
        target_abs = os.path.abspath(target_path)
        if os.path.commonpath([root_abs, target_abs]) != root_abs:
            raise ValueError(f"Security Violation: Target path '{target_abs}' escapes root '{root_abs}'")
```
