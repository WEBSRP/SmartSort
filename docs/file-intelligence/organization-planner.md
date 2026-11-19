# SmartSort File Intelligence Engine: Organization Planner

## Implementation status

Phase 12 implements `OrganizationPlanner` in
`src/core/file_intelligence/planner.py` and `OrganizationProposal` in `context.py`.
Both are exported from the file-intelligence package. The planner accepts an
existing rule manager and config argument; it does not instantiate either or
read configuration. The explicit `root_dir` argument is the destination boundary.
Relative roots resolve against the current working directory; environment
variables and `~` are not expanded.

`plan_file(context, root_dir)` returns a proposal and sets
`context.proposed_destination` only after every check succeeds. Other context
fields are preserved. It does not classify files, create directories, reserve
targets, open file contents, access the network or execute transfers. Path
canonicalization uses read-only filesystem metadata queries (`stat`/`readlink`).
A missing source file is not probed; the enriched context supplies its size.

## Rule precedence and destination semantics

A fresh existing `RuleEngine` is built from `rule_manager.rules` for each call,
so manager edits and enabled-state changes are honored. Existing priority,
condition and variable-expansion behavior remains unchanged: lower priority
numbers win and the first enabled matching rule takes precedence. Rules are
evaluated using the context source path and non-negative integer size.

- A matching rule normally names a directory; the filename is appended.
- When its original destination contains `{filename}`, its expanded destination
  is the complete target path. The filename is not appended a second time.
- `{extension}` retains the existing engine's uppercase expansion.
- Relative rule destinations are rooted under `root_dir`. Absolute destinations
  are allowed only when their canonical target remains inside the same root.
- Empty, control-containing, URI/drive-style and backslash-containing destinations
  are rejected. Any `..` component is rejected, including a traversal that would
  ultimately return inside the root. Benign `.` and repeated/trailing directory
  separators are normalized; a full-file template may not end with `/`.
- An invalid winning rule or evaluation failure does not silently fall through
  to intelligence or a lower-priority rule. Errors leave the context unchanged.

Rule proposals set `is_rule_override=True`, use the safe display rule name as
`domain`/`rule_name`, and carry `CONFIRMED`/1.0 with a rule-match explanation.
This represents an explicit policy override, not measured semantic certainty.
The hierarchy comes from actual destination directories, rather than the rule
name. Rule display labels are bounded to 256 characters with controls replaced.

## Classification hierarchy and fallback

Without a matched rule, the engine's `Others/` no-match destination is ignored.
The planner uses the classified context directly:

```text
root / classification_domain / subcategory_1 / ... / filename
```

For example, `College` plus `['DBMS', 'Lectures']` yields
`College/DBMS/Lectures/notes.pdf`; `Projects` plus `['SmartSort', 'Source']`
yields `Projects/SmartSort/Source/notes.pdf`. The planner does not invent a
missing course/project name or a `General` folder.

Scores below 0.35, confidence levels `UNKNOWN`/`NOT_AVAILABLE`, or a semantic
`Others` result now use a fixed file-type fallback (1.2.4). Known video formats
route to `Videos`, audio to `Audio`, installers such as DEB/AppImage/APK/XAPK to
`Applications`, and ordinary documents/text to `Documents`. Images, archives and
code also retain useful type destinations. Only unknown formats use `Others`.

Fallback proposals carry `UNKNOWN` confidence and a zero score, retain the
original semantic evidence, and add an explicit file-type fallback explanation.
Discarded subcategory hints cannot escape this fixed vocabulary. At exactly
0.35, a usable typed classification can retain its semantic hierarchy. Strong
content classifications and custom rules retain their existing precedence.

Otherwise, only the seven Phase 11 roots are accepted. Malformed/unrecognized
high-confidence domains and invalid hierarchy components raise `ValueError`.
Classification scores must be finite in `[0, 1]` and levels must be enum members.
The planner copies classification evidence into the proposal; it never alters
the classification decision or adds a relationship confidence boost.

## Filename, path and containment checks

The context filename must be one component and match the source basename.
Phase 14 adds an optional keyword-only `override_filename` to `plan_file()` for
download cleanup. It validates a separate destination component without changing
the original context filename, rule conditions, extension or source path. In
full-file rule templates only actual `{filename}` placeholders are replaced,
preserving identical literal directory names. Unicode,
spaces and ordinary Linux filename punctuation are preserved rather than
silently rewritten. Components reject empty/whitespace-only names, `.`/`..`,
slashes, backslashes, C0 controls and DEL; each is limited to 255 filesystem
bytes. Source/root/expanded planning paths are limited to 4,096 characters.
Classification hierarchies allow at most 16 subcategories and evidence lists at
most 8,192 items.

Both root and target are canonicalized through existing symlinks, including
missing suffixes. Component-aware `os.path.commonpath` containment must place
the resolved target strictly beneath the resolved root. A prefix sibling such
as `root_extra` is outside `root`. Escaping parent/final symlinks and dangling
links pointing outside are rejected. Loops, permission failures and non-directory
ancestors fail closed. Existing roots must be directories; existing target files
must be regular files. Directory, FIFO and other special targets are rejected.
Missing root/target directories remain absent and can be created later by the
execution layer.

A selected root may itself be a symlink: its canonical directory becomes the
boundary. Internal aliases resolving within that boundary are allowed. Proposal
`target_path`, `relative_target` and `hierarchy_segments` all describe the same
canonical destination, even when an internal alias changes directory names.
The classification `domain` remains semantic metadata.

## Proposal model and execution boundary

`OrganizationProposal` includes source/target paths, relative target, domain,
hierarchy segments, confidence level/score, evidence and rule metadata. Its
`to_dict()`/`from_dict()` helpers round-trip enum/evidence values through JSON
and independently copy lists. It validates typed fields and finite unit scores
and evidence weights. Model construction/deserialization alone does not validate
filesystem containment; only a freshly generated plan performs those checks.

The planner is deterministic while rules, context, working directory and the
filesystem remain unchanged. It does not choose collision suffixes, overwrite
an existing target, reserve a path, detect duplicates or skip same-source/target
no-ops. Those decisions belong to organizer/execution integration.

Containment is a **planning-time check**, not a race-free authorization to write.
Symlinks, directories, mounts or permissions can change afterwards. Execution
must revalidate current paths and retain the existing safe transfer protocol.
No transfer code or organizer/GUI integration is changed in Phase 12. Existing
rule regex evaluation is also unchanged and has no new execution deadline.
