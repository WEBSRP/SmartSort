# Security Audit Report — SmartSort v1.0.3

**Target Version:** v1.0.3  
**Auditor:** Senior Security Reviewer & Release Manager  
**Date:** 2026-07-28  

---

## 1. Executive Summary

A comprehensive security audit of SmartSort v1.0.3 was conducted covering path traversal, file operation safety, symlink handling, input validation, privilege escalation, dependency risks, and process isolation.

SmartSort operates as a local, offline user-space application with zero external network connectivity, telemetry, or remote API endpoints. Overall security posture is **HIGH**, with robust destination base directory boundary checks preventing path traversal escape vulnerabilities. 

Three medium-severity risks were identified relating to symlink handling, unvalidated regular expression inputs (ReDoS potential), and unhandled permission errors during recursive folder operations. None of these block the release, but recommendations are provided for future hardening.

---

## 2. Security Assessment Matrix

| Vulnerability Category | Risk Level | Status | Details |
|---|---|---|---|
| **Path Traversal / Escapes** | 🟢 Low Risk | Passed | Verified strict `os.path.commonpath` boundary check in `FileOrganizer` |
| **Symlink Vulnerabilities** | 🟡 Medium Risk | Action Recommended | Symlinks are followed during SHA256 hashing and copying |
| **ReDoS (Regex Denial of Service)** | 🟡 Medium Risk | Action Recommended | User-supplied regex in `RegexCondition` evaluated using standard `re` module |
| **Privilege Escalation** | 🟢 Low Risk | Passed | Systemd service runs in user space (`systemctl --user`); no root privileges |
| **Code Injection / Shell Execution** | 🟢 Low Risk | Passed | Subprocess calls in `main_window.py` use list arguments without `shell=True` |
| **Dependency Vulnerabilities** | 🟢 Low Risk | Passed | Direct dependencies (`PyQt6`, `watchdog`, `notify2`) are standard open-source libraries |
| **Configuration Tampering** | 🟢 Low Risk | Passed | Auto-recovery from `.bak` backup file if `config.json` is corrupted |

---

## 3. Detailed Security Findings

### SEC-01: Symlink Following during File Hash and Copy Operations
- **Severity:** Medium
- **Component:** `src/utils/file_utils.py` ([FileUtils.calculate_sha256](file:///home/websrp/SmartSort/src/utils/file_utils.py#L8), [FileUtils.safe_copy](file:///home/websrp/SmartSort/src/utils/file_utils.py#L19))
- **Description:** `FileUtils.calculate_sha256` opens files with standard `open(file_path, "rb")`, and `shutil.copy2` copies target files directly. If a symlink is dropped or created inside the watched Downloads folder (e.g. `download.pdf -> /etc/passwd` or `~/.ssh/id_rsa`), SmartSort will follow the symlink, read/hash the target file, and copy it to the destination directory.
- **Impact:** Potential unauthorized exposure of sensitive local files if a malicious process or untrusted download archive creates symlinks inside the watched folder.
- **Recommendation:** Check `os.path.islink(file_path)` prior to processing. Either skip symbolic links or log a warning and ignore symlinks by default.
- **Release Blocker:** No (Local user-space tool operating on user's own `Downloads` directory).

---

### SEC-02: Regular Expression Denial of Service (ReDoS) Potential
- **Severity:** Medium
- **Component:** `src/rules/conditions.py` ([RegexCondition](file:///home/websrp/SmartSort/src/rules/conditions.py#L87))
- **Description:** Rules allow users to define custom regular expression patterns evaluated against incoming filenames. `RegexCondition.__init__` compiles the pattern using Python's standard `re` module. Catastrophic backtracking patterns (e.g. `(a+)+$`) evaluated against long filenames could freeze the file processing worker thread.
- **Impact:** High CPU utilization and worker thread freeze when matching crafted filenames against poorly constructed user rules.
- **Recommendation:** Implement a pattern length limit or timeout wrapper for regular expression matching, or sanitize/validate nested quantifiers during rule creation in `RuleDialog`.
- **Release Blocker:** No (Rules are created exclusively by the local desktop user).

---

### SEC-03: Arbitrary File Deletion Risk on Permission Failures
- **Severity:** Low
- **Component:** `src/organizer.py` ([FileOrganizer.process_file](file:///home/websrp/SmartSort/src/organizer.py#L105))
- **Description:** The file transfer lifecycle follows: Copy → SHA256 Verification → Delete Source (`os.remove(file_path)`). If `os.remove` fails due to permissions or read-only filesystem flags after a successful copy, the file exists in both source and destination, and an error is logged.
- **Impact:** Duplicate copies remain if source deletion fails; no data loss occurs.
- **Recommendation:** Maintain current non-destructive error handling behavior.
- **Release Blocker:** No.

---

### SEC-04: Subprocess Execution Safety
- **Severity:** Low (Compliant)
- **Component:** `src/gui/main_window.py`
- **Description:** Subprocess invocations (e.g., `systemctl --user is-active smartsort.service`) pass arguments as lists (`["systemctl", "--user", ...]` ) and do not set `shell=True`.
- **Impact:** Safe from command injection vulnerabilities.

---

## 4. Verification & Hardening Checklist

- [x] **Destination Directory Escape Prevention:** Verified `FileOrganizer.get_destination_path()` enforces `os.path.commonpath([base_dest, dest_path]) == base_dest`.
- [x] **Config File Backup Integrity:** Verified `ConfigManager` automatically creates `.bak` backups before writing settings.
- [x] **No Hardcoded Passwords / Secrets:** Verified repository contains no API keys, tokens, or credentials.
- [x] **User-Space Service Isolation:** Verified `smartsort.service` runs as a user-level systemd unit (`WantedBy=default.target`).

---

## 5. Security Conclusion

SmartSort v1.0.3 demonstrates a strong security baseline appropriate for an offline desktop file organizer. All file path resolution is bounded, subprocess execution is sanitized, and operations are strictly isolated to the user's desktop session.

**Security Status:** ✅ **APPROVED FOR RELEASE**
