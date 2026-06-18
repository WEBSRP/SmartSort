import sys
import os
import argparse

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from PyQt6.QtWidgets import QApplication
from src.gui.main_window import SmartSortGUI

def main():
    parser = argparse.ArgumentParser(description="SmartSort File Organizer")
    parser.add_argument("--service", action="store_true", help="Run in service mode (minimized/background)")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = SmartSortGUI()
    
    if args.service:
        # In service mode, we might want to start minimized to tray
        # For now, just show it or hide it.
        # window.hide() 
        window.show() # Keep it visible for now as requested by GUI requirements
    else:
        window.show()
        
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
