# Phase 12: Intelligent Organization Planner & Hierarchy Generation

## Objective
Implement `src/core/file_intelligence/planner.py` (`OrganizationPlanner`) to synthesize safe, canonical destination paths (`OrganizationProposal`), enforce user rule precedence, and validate root directory boundary containment.

## Why This Phase Exists
The Organization Planner translates abstract classification results into concrete filesystem operations. It ensures that user-defined custom rules always take precedence, enforces path containment to prevent directory escapes, and guarantees deterministic destination formatting.

## Inputs
- Classified `FileContext` and target root directory path.

## Outputs
- `src/core/file_intelligence/planner.py` (`OrganizationPlanner`).
- Tests in `tests/test_file_intelligence/test_planner.py`.

## Files To Create
- `src/core/file_intelligence/planner.py`
- `tests/test_file_intelligence/test_planner.py`

## Files To Modify
- `src/core/file_intelligence/__init__.py`: Export `OrganizationPlanner`.

## Existing Components To Reuse
- `src/rules/manager.py` (`RuleManager`) & `src/rules/engine.py` (`RuleEngine`): For user custom rule evaluation.
- `src/core/file_intelligence/context.py`: Generates `OrganizationProposal`.

## APIs / Interfaces
```python
# src/core/file_intelligence/planner.py
class OrganizationPlanner:
    def __init__(self, rule_manager: RuleManager, config: ConfigManager):
        self.rule_manager = rule_manager
        self.config = config
        self.rule_engine = RuleEngine(rule_manager.rules)

    def plan_file(self, context: FileContext, root_dir: str) -> OrganizationProposal:
        """
        Evaluates user rules first, then synthesizes hierarchical proposal from
        context. Validates canonical path boundary containment.
        """
        ...
```

## Data Structures
- Produces `OrganizationProposal` from `src.core.file_intelligence.context`.

## Algorithms
- **User Rule Evaluation First**:
  - Calls `rule_engine.evaluate_file(context.path, context.size_bytes)`.
  - If a rule matches, returns `OrganizationProposal` with `is_rule_override=True`, `confidence_score=1.0`.
- **Intelligence Hierarchy Generation**:
  - Builds path segments: `[context.classification_domain] + context.subcategories`.
  - Resolves target: `os.path.abspath(os.path.join(root_dir, *segments, context.filename))`.
- **Boundary Containment Check**:
  - `os.path.commonpath([root_abs, target_abs]) == root_abs`. Raises `ValueError` on path traversal violation.

## Error Handling
- Rejects relative escapes (`../`) and illegal characters (`\0`).

## Security Considerations
- Guarantees target files never escape the configured root directory or destination base.

## Performance Considerations
- Planning execution in < 0.05 ms per proposal.

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_planner.py`:
  - Test user custom rule override precedence.
  - Test intelligent path synthesis (`College/DBMS/Lectures/notes.pdf`).
  - Test malicious path traversal rejection (`../../outside` raises `ValueError`).
  - Test low-confidence fallback to `Others/`.

## Acceptance Criteria
- [ ] `OrganizationPlanner` generates verified `OrganizationProposal` objects.
- [ ] User custom rules take strict precedence when matched.
- [ ] 100% test pass on `test_planner.py`.

## Dependencies
- Standard library `os`, `pathlib`, `typing`.

## What This Phase MUST NOT Change
- Must NOT modify existing safe transfer or move execution code.

## Completion Checklist
- [ ] `planner.py` implemented.
- [ ] Unit tests passing.
