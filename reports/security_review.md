# Security Review

Date: 2026-07-25

## Fixed Release Issue

Rule destinations could previously escape `destination_base` through `..` path components. Example: a rule destination of `../outside` would resolve outside the configured base during organization.

Fix: `FileOrganizer.get_destination_path()` now resolves the configured base and candidate destination and rejects paths whose common path is outside the base. `process_file()` returns `ERROR` and preserves the source file on violation.

Regression test added: `test_destination_path_cannot_escape_base`.

## Reviewed Areas

- Filesystem operations use copy, SHA256 verification, and source deletion only after verified copy.
- Duplicate detection compares SHA256 where destination exists.
- Config files are validated and backed up before writes.
- Autostart/systemd command generation uses fixed application commands for packaged modes.
- Subprocess calls are bounded with timeouts in most GUI service-control paths.

## Residual Risks

- Symlink handling is improved for destination traversal through resolved paths, but `safe_copy()` still follows filesystem semantics for existing destination symlinks. A malicious destination tree controlled by another user could still be risky. This is lower risk for normal per-user Downloads organization but should be hardened before multi-user or privileged operation.
- Regex rules are user-provided Python regexes and can be expensive on pathological patterns. The current scope is local user configuration, so this is a denial-of-service risk against the user's own process.
- `ensure_user_icons_installed()` writes into `~/.local/share/icons`; failures are caught and logged, but tests show noisy errors on read-only homes.

## Security Readiness

Security is acceptable for an unprivileged single-user desktop application after the destination containment fix. It is not appropriate to run as root or as a shared multi-user service without additional symlink and permission hardening.

