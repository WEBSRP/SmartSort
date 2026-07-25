# CI Shutdown Fix Report

## Files Modified

Three files were modified. Each change is minimal and directly addresses the shutdown hang.

---

## 1. `src/monitor.py` — FileMonitor.stop()

**Problem**: `observer.join()` throws `RuntimeError` when called on an Observer that was never started (race condition during fast shutdown).

**Before**:
```python
def stop(self):
    self.observer.stop()
    self.observer.join()
```

**After**:
```python
def stop(self):
    self.observer.stop()
    if self.observer.is_alive():
        self.observer.join()
```

**Justification**: `observer.stop()` sets the internal stop flag regardless of whether the thread has started. `observer.join()` must only be called if the thread is actually alive. This is a defensive guard, not a behaviour change — when the Observer is alive, `join()` still executes and waits for clean shutdown.

---

## 2. `src/gui/main_window.py` — MonitorThread.stop()

**Problem**: If `self.monitor.stop()` throws an exception, `self.quit()` is never called. The QThread's event loop (`self.exec()`) runs forever.

**Before**:
```python
def stop(self):
    self.monitor.stop()
    self.quit()
```

**After**:
```python
def stop(self):
    try:
        self.monitor.stop()
    except RuntimeError:
        pass
    finally:
        self.quit()
```

**Justification**: `self.quit()` must execute unconditionally. If the Observer shutdown fails (e.g., never started), the QThread event loop still needs to terminate. The `try/finally` guarantees `quit()` always runs.

---

## 3. `tests/test_core.py` — test cleanup

**Problem**: `gui.monitor_thread.wait()` was called without a timeout. If the QThread failed to quit, this blocked forever.

**Before**:
```python
gui.monitor_thread.stop()
gui.monitor_thread.wait()
```

**After**:
```python
gui.monitor_thread.stop()
gui.monitor_thread.wait(5000)
```

Also added `gui.threadpool.waitForDone(1000)` to ensure QThreadPool workers complete before widget deletion.

**Justification**: A 5-second timeout prevents indefinite blocking. The `MonitorThread.stop()` fix above makes this timeout a safety net rather than a primary defence.

---

## Before vs After Behaviour

| Scenario | Before | After |
| :--- | :--- | :--- |
| Observer starts normally, then stop() | Works | Works (identical) |
| Observer never started, then stop() | RuntimeError → quit() skipped → QThread hangs | RuntimeError caught → quit() always called → QThread exits |
| Test cleanup wait | Blocks forever if quit() was skipped | Times out after 5 seconds (safety net) |
| Application shutdown on desktop | Relies on OS process termination | Same, plus defensive guards |
