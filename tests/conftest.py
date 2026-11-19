import sys
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
    # Let pytest return its actual status and Python shut down normally.
    # Forced exit here masks failing tests and cannot prove worker cleanup.
