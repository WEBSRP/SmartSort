import sys
import os
import atexit
import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication fixture to ensure a single instance is reused and cleaned up."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # Flush all pending Qt events (deferred deletions, signals, etc.)
    for _ in range(20):
        app.processEvents()
    # Register os._exit(0) as an atexit backstop. This guarantees the process
    # exits even if Qt background threads or non-daemon Python threads are still
    # alive after the test session. By the time atexit runs, pytest has already
    # written the final test summary to stdout, so no output is lost.
    atexit.register(os._exit, 0)
