import sys
import os
import argparse
import time

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def run_daemon():
    from pathlib import Path
    from src.utils.config import ConfigManager
    from src.utils.logger import SmartSortLogger
    from src.organizer import FileOrganizer
    from src.monitor import FileMonitor
    
    config = ConfigManager(config_path="config/config.json", default_path="config/default_config.json")
    logger = SmartSortLogger()
    organizer = FileOrganizer(config, logger)
    watch_folder = config.get("downloads_folder")
    
    if watch_folder.startswith("~"):
        watch_folder = str(Path(watch_folder).expanduser())
        
    logger.info(f"Daemon mode started. Monitoring downloads folder: {watch_folder}")
    
    notifications_enabled = False
    if config.get("enable_notifications"):
        try:
            import notify2
            notify2.init("SmartSort")
            notifications_enabled = True
        except Exception as e:
            logger.error(f"Could not initialize notifications in daemon: {e}")

    def on_new_file(file_path):
        logger.info(f"Daemon detected file: {file_path}")
        result, info = organizer.process_file(file_path, user_approved=True)
        logger.info(f"Daemon processed file {file_path}. Result: {result}, Info: {info}")
        if notifications_enabled:
            try:
                n = notify2.Notification("SmartSort Daemon", f"Processed: {os.path.basename(file_path)}\nResult: {result}")
                n.show()
            except Exception:
                pass

    monitor = FileMonitor(watch_folder, organizer, on_new_file)
    monitor.start()
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Daemon mode stopping...")
        monitor.stop()

def main():
    from pathlib import Path
    import time
    
    parser = argparse.ArgumentParser(description="SmartSort File Organizer")
    parser.add_argument("--service", action="store_true", help="Run in service mode (minimized/background)")
    parser.add_argument("--daemon", action="store_true", help="Run in background daemon mode (no GUI)")
    args = parser.parse_args()

    if args.daemon:
        run_daemon()
        return

    from PyQt6.QtWidgets import QApplication
    from src.gui.main_window import SmartSortGUI
    from src.utils.config import ConfigManager

    app = QApplication(sys.argv)
    window = SmartSortGUI()
    
    config = ConfigManager(config_path="config/config.json", default_path="config/default_config.json")
    
    if (args.service or config.get("start_minimized")) and getattr(window, "tray_available", False):
        # Run directly in tray (don't show the dashboard window)
        pass
    else:
        window.show()
        
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
