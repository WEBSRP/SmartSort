# Runtime Debug Report

Date: 2026-07-25

## Question Investigated

GitHub Actions runs all tests, the last visible test is `test_verify_and_repair_startup_config`, Qt prints shutdown warnings, and pytest never reaches the summary. Local `pytest tests/` returns normally.

## Evidence Collected

- Local offscreen pytest completed before fixes: `38 passed in 0.42s`.
- The CI command shape uses `xvfb-run ... pytest ... | tee pytest.log`; this means the CI step only completes when pytest, Python, Qt threads, and any inherited output handles all terminate.
- `test_verify_and_repair_startup_config` instantiates a real `SmartSortGUI`, which creates:
  - `QTimer` for dashboard stats.
  - `MonitorThread`, a `QThread`.
  - `FileMonitor`, wrapping a watchdog `Observer`.
  - `QSystemTrayIcon`.
  - `QThreadPool`.
- A lifecycle probe after GUI creation showed a running `MonitorThread` plus watchdog inotify helper threads before cleanup, and only `MainThread` after normal cleanup.
- A targeted race reproduction showed the real failure:
  - Call `MonitorThread.stop()` before `MonitorThread.start()`.
  - Then call `start()`.
  - Before the fix, `wait(1000)` returned `False`; `isRunning()` stayed `True`; Qt printed an exception warning.

## Root Cause

The remaining CI hang was a `MonitorThread` startup/shutdown race.

Before the fix, `MonitorThread.stop()` called `quit()`, but a stop request made before the thread entered `run()` was not remembered. If CI timing caused cleanup to request stop before `run()` reached `self.exec()`, the thread could later start, call `monitor.start()`, and enter the Qt event loop anyway. That left a live non-main Qt thread after tests, preventing Python process shutdown and therefore preventing the `tee` pipeline from completing.

## Why Local Execution Succeeded

Local execution usually starts the `QThread` fast enough that cleanup stops an already-running event loop. CI timing is different under Python 3.12, `xvfb-run`, Qt offscreen/X11 setup, and shell pipeline logging. The race depends on ordering, so local success did not disprove the bug.

## Fix Applied

`src/gui/main_window.py` now records stop intent with `_stop_requested` and `requestInterruption()`. `run()` checks that state before starting the monitor and again before entering `self.exec()`. If a stop was requested early, the thread returns instead of entering the event loop.

Regression test added: `test_monitor_thread_stop_before_start_exits`.

## Validation

- Targeted regression: `2 passed in 0.37s`.
- Full suite: `40 passed in 0.34s`.
- CI-shaped local pipeline without `xvfb-run`: `40 passed in 0.34s` and pytest summary printed.
- `xvfb-run` could not be executed locally because it is not installed in this container.

