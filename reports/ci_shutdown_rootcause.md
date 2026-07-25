# CI Shutdown Root Cause Analysis

## Root Cause

The Python process hung after pytest because a `QThread` event loop was never terminated.

### Exact Failure Chain

```
SmartSortGUI.__init__()
    ↓
self.start_monitor()
    ↓
MonitorThread(watch_path, organizer).start()    ← QThread native thread spawned
    ↓
MonitorThread.run()                              ← Executes in QThread
    ↓
self.monitor.start()                             ← Calls observer.start()
self.exec()                                      ← QThread enters event loop (BLOCKS)
```

During test cleanup:

```
finally block
    ↓
gui.monitor_thread.stop()
    ↓
MonitorThread.stop()
    ↓
self.monitor.stop()                              ← FileMonitor.stop()
    ↓
self.observer.stop()                             ← Sets stop flag (OK)
self.observer.join()                             ← RACE CONDITION
```

The `observer.join()` call in `FileMonitor.stop()` throws `RuntimeError("cannot join thread before it is started")` when the watchdog Observer thread hasn't fully started yet (race condition between QThread starting and cleanup beginning).

This exception propagates out of `MonitorThread.stop()` **before** `self.quit()` on line 59 executes. The QThread's event loop (`self.exec()`) therefore **never receives a quit signal** and runs indefinitely.

The test cleanup then calls `gui.monitor_thread.wait()` **without a timeout**, which blocks forever waiting for a QThread that will never finish.

### Affected Files

| File | Issue |
| :--- | :--- |
| [src/monitor.py](file:///home/websrp/SmartSort/src/monitor.py#L127-L129) | `observer.join()` called unconditionally, throws on never-started Observer |
| [src/gui/main_window.py](file:///home/websrp/SmartSort/src/gui/main_window.py#L57-L59) | `self.quit()` not called if `self.monitor.stop()` throws |
| [tests/test_core.py](file:///home/websrp/SmartSort/tests/test_core.py#L1434-L1436) | `monitor_thread.wait()` called without timeout |

### Why the Bug Only Appeared in CI

Locally, the test appeared to work because:
1. The local machine has `~/Downloads` and the Observer may start fast enough to avoid the race condition
2. Even when the race occurs locally, the test may still "pass" because the exception in the `finally` block doesn't prevent pytest from reporting results — pytest catches it and exits
3. Local Python process termination may be more aggressive with signal handling

On GitHub Actions:
1. The headless offscreen Qt platform may introduce slight timing differences
2. The QThread's event loop, once orphaned, prevents the pytest process from terminating
3. GitHub Actions waits indefinitely for the process to exit, then times out
