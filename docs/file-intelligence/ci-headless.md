# SmartSort File Intelligence Engine: CI & Headless Constraints

## 1. Context & Historical CI Hang Background

SmartSort previously suffered from release-blocking GitHub Actions pipeline hangs. Root-cause audits identified three failure modes:
1. **Unmocked Modal Dialogs**: `QMessageBox` calls initiated inside core logic or background worker threads when running on headless display servers.
2. **Unmanaged Threads & Indefinite Joins**: Watchdog observers or Qt threads waiting indefinitely on background resources without explicit stop events or timeouts.
3. **Implicit Qt Event Loops**: Single-shot timers or QTimer instances that prevented clean Python process termination after test completion.

The File Intelligence Engine is architected specifically to **prevent any reintroduction of CI hangs**.

---

## 2. Mandatory Headless Invariants

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADLESS CI SAFETY RULES (STRICTLY ENFORCED)                                │
│                                                                             │
│  1. ZERO Qt Imports in `src/core/file_intelligence/`                        │
│     - Core modules must NEVER import PyQt6, QWidget, QMessageBox, QThread,   │
│       QRunnable, or QObject.                                                │
│                                                                             │
│  2. NO Blocking Modal Calls                                                 │
│     - All user prompts or error notifications must exist exclusively in UI  │
│       slot handlers in `src/gui/main_window.py`.                            │
│                                                                             │
│  3. NO Arbitrary `time.sleep()` Synchronizations                            │
│     - Thread coordination must use `threading.Event()` or bounded timeouts.│
│                                                                             │
│  4. Deterministic Mocking of Browser & Filesystem Resources                 │
│     - Tests must never access real user home directories (`~/.config/google-│
│       chrome` or `~/.mozilla/firefox`). Always mock using `tmp_path`.        │
│                                                                             │
│  5. Bounded Process Termination                                             │
│     - Tests must cleanly exit with code 0 without hanging pytest runners.   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. GitHub Actions Pipeline Verification

All File Intelligence additions must run seamlessly within the existing `.github/workflows/ci.yml` pipeline:

```yaml
- name: Run Test Suite
  shell: bash
  run: |
    set -euxo pipefail
    xvfb-run -a python -m pytest \
      -vv \
      -s \
      --durations=20 \
      --durations-min=1 \
      tests/ | tee pytest.log
```

Any test or module that fails to terminate normally under `xvfb-run` or `QT_QPA_PLATFORM=offscreen` is considered a **release-blocking critical failure**.


## Phase 20 validation update

The former Qt teardown forced exit-zero backstop was removed after a controlled
failure demonstrated that it made the CLI report success despite failed tests.
`tests/test_ci_exit.py` now verifies both successful and failing subprocess exit
codes using the real session Qt fixture. No production logic changed.

The local workflow-style and offscreen validation runs exited naturally with no
Python worker threads, tracked running QThreads/active QTimers or child processes
at final inventory. This is observed evidence, not an absolute guarantee against
future hangs. Hosted Ubuntu/Python 3.12 was not reproduced by the Debian/Python
3.13 local environment. See the final implementation report for the exact
commands, results, artifact checks and outstanding performance/release gates.
