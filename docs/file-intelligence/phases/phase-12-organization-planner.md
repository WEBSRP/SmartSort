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
- `src/core/file_intelligence/context.py`: Implement and export the previously
  documented `OrganizationProposal`, including JSON serialization helpers.

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
  - Preserves existing full-target semantics for templates containing
    `{filename}`; otherwise appends the context filename to the expanded folder.
- **Intelligence Hierarchy Generation**:
  - Builds path segments: `[context.classification_domain] + context.subcategories`.
  - Resolves target: `os.path.abspath(os.path.join(root_dir, *segments, context.filename))`.
- **Boundary Containment Check**:
  - Canonicalizes root/target through symlinks before checking
    `os.path.commonpath([root_real, target_real]) == root_real`.
    Raises `ValueError` on path traversal violation or resolution failure.

## Error Handling
- Rejects relative escapes (`../`) and illegal characters (`\0`).

## Security Considerations
- Checks destination containment in the selected root against the current
  filesystem. Execution must revalidate paths; a proposal is not a race-free
  authorization to write after later filesystem changes.

## Performance Considerations
- Target: planning execution in < 0.05 ms per proposal. Local warm medians meet
  this on the measured fixtures; cold calls and maxima exceed it (see below).

## CI / Headless Requirements
- Zero Qt imports. 100% headless test execution.

## Tests
- `tests/test_file_intelligence/test_planner.py`:
  - Test user custom rule override precedence.
  - Test intelligent path synthesis (`College/DBMS/Lectures/notes.pdf`).
  - Test malicious path traversal rejection (`../../outside` raises `ValueError`).
  - Test low-confidence fallback to `Others/`.

## Acceptance Criteria
- [x] `OrganizationPlanner` generates verified `OrganizationProposal` objects.
- [x] User custom rules take strict precedence when matched.
- [x] 100% test pass on `test_planner.py`.

## Dependencies
- Standard library `os`, `pathlib`, `typing`.

## What This Phase MUST NOT Change
- Must NOT modify existing safe transfer or move execution code.

## Completion Checklist
- [x] `planner.py` implemented.
- [x] Unit tests passing.

## Implementation State — 2026-11-17

Functional implementation is complete in the local working tree. Added/exported
`OrganizationPlanner` and `OrganizationProposal`. No dependencies, organizer,
GUI, configuration or transfer execution behavior changed. The existing rule
engine is reused, refreshed from the supplied manager on every plan, with size
conditions using context metadata rather than reading the source file.

Rules win over classification, including unknown classification. Directory
templates append the filename; full-file `{filename}` templates do not duplicate
it. Absolute rule targets are accepted only inside the canonical root. An invalid
winning rule raises rather than falling back. Rule labels are display metadata;
proposal hierarchy segments describe actual canonical directories.

Without a rule, classified domain/subcategory segments form the hierarchy.
Scores below 0.35 or UNKNOWN/NOT_AVAILABLE levels route to `Others`. Invalid
high-confidence domains/components are rejected. The planner does not invent
missing course/project names or perform extension-based classification again.
Only `context.proposed_destination` changes, after successful proposal creation.

Safety checks reject traversal, control characters, ambiguous separators,
unsafe filename components, oversized paths/hierarchies, escaping/dangling
symlinks, symlink loops, inaccessible paths, non-directory ancestors and special
targets. Internal aliases resolving inside the selected canonical root are
allowed. Missing directories are not created; existing regular targets are not
overwritten or renamed. Rules, relative working directory and filesystem state
are inputs to determinism. Containment checks do not eliminate races between
planning and execution, or replace collision/no-op handling and safe transfers.

Validation:

- Baseline: **1,091 passed, 1 skipped**, exit code 0.
- Added **95 planner test cases**, covering real rule-manager conditions,
  priority/updates/expansion, intelligent and fallback hierarchies, traversal,
  symlink and file-type checks, Unicode/byte limits, invalid inputs, atomic context
  updates, JSON/list independence, classifier interoperability and headless import.
- Final full suite: **1,186 passed, 1 skipped** in 19.32 s, genuine pytest exit
  code **0** preserved before the existing Qt teardown's forced exit-zero hook.
- Source compilation and `git diff --check` pass. Test state/bytecode use `/tmp`.

Isolated local measurements (501 runs per case; first call, then median and
maximum of 500 subsequent calls, in milliseconds):

| Fixture | First | Warm median | Warm maximum |
| --- | ---: | ---: | ---: |
| Intelligence; missing destination directories | 0.1491 | 0.0487 | 0.1202 |
| Intelligence; existing destination directories | 0.0737 | 0.0482 | 0.1769 |
| One custom rule | 0.0792 | 0.0496 | 0.2193 |

Warm medians meet the 0.05 ms target on these fixtures; first calls and maxima
do not. These observations are not a universal deadline. Longer paths, slower
filesystems and more/expensive existing rules increase runtime. This phase adds
no rule-regex timeout or persistent cache.

See [organization-planner.md](../organization-planner.md) for exact contracts.
Next: **Phase 13 — Directory Organizer Integration & Batch Profiling**.
