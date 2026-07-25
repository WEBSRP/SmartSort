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
    # Process all pending events and quit
    app.processEvents()
    app.quit()
