import sys
import os
import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication fixture to ensure a single instance is reused and cleaned up."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # Flush all pending events before teardown
    for _ in range(20):
        app.processEvents()
    # exit(0) posts a QuitEvent to all event loops (including QThread exec() loops),
    # ensuring every thread's exec() returns and the process can exit cleanly.
    app.exit(0)
    # One final flush to process the quit event delivery
    for _ in range(5):
        app.processEvents()
