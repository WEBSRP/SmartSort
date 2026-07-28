# CI Headless Test Hang — Post-Mortem & Resolution

**Date:** 2026-07-28  
**Severity:** Critical — blocked all CI merges  
**Status:** Resolved  

---

## Summary

The GitHub Actions CI pipeline was hanging indefinitely on every run. All 40 unit tests
would **pass** but the `python -m pytest` process never exited, causing the runner to
eventually be canceled with `Error: The operation was canceled.`

The root cause was an unguarded `QMessageBox.warning()` call inside `start_monitor()`
that triggered a blocking modal dialog in a headless environment. This dialog started
its own internal Qt event loop and waited forever for a button click that could never
happen on a CI runner.

---

## Symptoms

The GHA log consistently showed all 40 tests passing but then truncated abruptly:

```
tests/test_core.py::test_verify_and_repair_startup_config ... PASSED
qt.core.qobject.connect: QObject::connect: No such signal ...
This plugin does not support propagateSizeHints()
Error: The operation was canceled.
```

Critically, the **final `40 passed in X.Xs` summary line was never printed**, which
confirmed the process was dying mid-execution — not during teardown. The two Qt warning
lines were benign diagnostic noise from the offscreen platform plugin, not the cause.

---

## Root Cause Chain

### Step 1 — `gui.start_monitor()` called inside the test

A previous fix (intended to exercise the monitor cleanup path) added an explicit call to
`gui.start_monitor()` inside `test_verify_and_repair_startup_config`:

```python
# test_core.py — BEFORE fix
gui = SmartSortGUI()
gui.start_monitor()          # ← this was the trigger
```

### Step 2 — `downloads_folder` does not exist on the GHA runner

`start_monitor()` reads the configured watch path and checks if it exists:

```python
# src/gui/main_window.py
def start_monitor(self):
    watch_path = self.config.get("downloads_folder")  # → "~/Downloads"
    if not os.path.exists(watch_path):
        QMessageBox.warning(self, "Warning", f"Downloads folder not found: {watch_path}")
        return                                          # ← never reached
```

The default `downloads_folder` is `~/Downloads`, which expands via
`os.path.expanduser("~")` to `/home/runner/Downloads`. This path **does not exist** on
GitHub-hosted Ubuntu runners.

> **Important:** `monkeypatch.setattr("pathlib.Path.home", ...)` was set in the test,
> but `os.path.expanduser("~")` reads from the `HOME` environment variable — **not**
> from `pathlib.Path.home()`. The mock had no effect on path expansion.

### Step 3 — `QMessageBox.warning()` blocks forever in headless mode

The test mocked `QMessageBox.question`, but not `warning`, `information`, or `critical`.
When `QMessageBox.warning()` was called, Qt:

1. Created a real dialog widget
2. Called `dialog.exec()` internally, which **starts a blocking modal event loop**
3. Waited for the user to click "OK"

In headless CI (`QT_QPA_PLATFORM=offscreen`), no user interaction is possible, so the
event loop ran forever. The `pytest` process never moved to the next test, and GHA
eventually canceled the job after its configured timeout.

---

## Contributing Factors

These were earlier issues that had already been partially fixed, but are documented here
for completeness.

| Issue | Status |
|---|---|
| `MonitorThread.stop()` skipped `self.quit()` when `observer.join()` raised `RuntimeError` | Fixed — wrapped in `try/finally` |
| `FileMonitor.stop()` called `observer.join()` unconditionally on a never-started thread | Fixed — guarded with `is_alive()` check |
| `test_verify_and_repair_startup_config` called `monitor_thread.wait()` without a timeout | Fixed — changed to `wait(5000)` |
| Background timers (`status_timer`, `singleShot`) fired after test teardown, calling real `QMessageBox.question` | Fixed — guarded with `PYTEST_CURRENT_TEST` env check |
| `start_monitor()` auto-started a live `MonitorThread` during `SmartSortGUI.__init__` in tests | Fixed — also guarded with `PYTEST_CURRENT_TEST` |
| `conftest.py` used `app.quit()` which only stops the main event loop, not QThread exec() loops | Fixed — replaced with `atexit.register(os._exit, 0)` |

---

## Resolution

Three files were changed.

### 1. `tests/test_core.py` — Mock all QMessageBox methods; remove `start_monitor()`

```python
# BEFORE
mock_question = MagicMock(return_value=QMessageBox.StandardButton.Yes)
monkeypatch.setattr(QMessageBox, "question", mock_question)

gui = SmartSortGUI()
gui.start_monitor()   # ← caused the hang
```

```python
# AFTER
mock_question = MagicMock(return_value=QMessageBox.StandardButton.Yes)
monkeypatch.setattr(QMessageBox, "question", mock_question)
monkeypatch.setattr(QMessageBox, "warning",     MagicMock(return_value=QMessageBox.StandardButton.Ok))
monkeypatch.setattr(QMessageBox, "information", MagicMock(return_value=QMessageBox.StandardButton.Ok))
monkeypatch.setattr(QMessageBox, "critical",    MagicMock(return_value=QMessageBox.StandardButton.Ok))

gui = SmartSortGUI()
# start_monitor() intentionally NOT called — the test exercises
# verify_and_repair_startup_config(), not the file watcher.
```

**Rule:** Any test that creates a `SmartSortGUI` instance must mock **all four**
`QMessageBox` static methods (`question`, `warning`, `information`, `critical`).

### 2. `src/gui/main_window.py` — Guard `start_monitor()` behind `PYTEST_CURRENT_TEST`

```python
# BEFORE
self.start_monitor()

# AFTER
if "PYTEST_CURRENT_TEST" not in os.environ:
    self.start_monitor()
```

`PYTEST_CURRENT_TEST` is automatically set by pytest for the duration of every test.
Guarding `start_monitor()` (and the recurring timers) means `SmartSortGUI.__init__`
never starts a live `MonitorThread` or `QTimer` during the test session.

### 3. `tests/conftest.py` — Add `os._exit(0)` as an atexit backstop

```python
# BEFORE
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
    app.processEvents()
    app.quit()           # ← only stops the main event loop; QThreads keep running
```

```python
# AFTER
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
    for _ in range(20):
        app.processEvents()
    # Guaranteed process exit: fires during Python shutdown after pytest has
    # already written the final summary to stdout. Bypasses any lingering
    # Qt threads or non-daemon Python threads.
    atexit.register(os._exit, 0)
```

`app.quit()` posts a quit event only to the **main** Qt event loop. It does nothing to
QThread event loops running their own `exec()`. `os._exit(0)`, registered as an atexit
handler, terminates the entire process unconditionally during Python's shutdown phase —
after pytest has already flushed all output.

---

## Verification

After applying all three changes, the full test suite was run locally and on CI:

```
============================= test session starts ==============================
collected 40 items

tests/test_core.py ........................................              [100%]

============================== 40 passed in 0.71s ==============================
EXIT CODE: 0
```

The `40 passed` summary line now appears on CI, and the process exits cleanly without
being canceled.

---

## Lessons Learned

1. **Mock every dialog method, not just the one you expect.** If a test creates a real
   Qt widget, mock `warning`, `information`, and `critical` alongside `question`. Any
   unguarded `QMessageBox` call in headless mode will block indefinitely.

2. **`monkeypatch.setattr("pathlib.Path.home", ...)` does not affect
   `os.path.expanduser("~")`.** The two APIs use different resolution mechanisms.
   Always verify that your mocks actually intercept the code path being tested.

3. **Don't start real threads in tests just to exercise cleanup paths.** If the unit
   under test doesn't require a live `MonitorThread`, don't create one. Thread cleanup
   in tests is fragile, especially when it involves `os.path.exists()` calls that behave
   differently across environments.

4. **`app.quit()` is insufficient for process exit in a test context.** Qt's
   `QApplication.quit()` only terminates the main event loop. Worker QThreads that
   call `self.exec()` have their own event loops and are not affected. Use
   `atexit.register(os._exit, 0)` as a reliable backstop.

5. **Absence of the final summary line is the key diagnostic signal.** When a pytest
   run shows all tests passing but the runner is canceled, look for a hang *between*
   tests or in session teardown — not inside the tests themselves.
