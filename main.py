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
    ensure_user_icons_installed(logger)
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

def ensure_user_icons_installed(logger=None):
    if not sys.platform.startswith("linux"):
        return
        
    try:
        user_icons_dir = os.path.expanduser("~/.local/share/icons")
        user_hicolor_dir = os.path.join(user_icons_dir, "hicolor")
        
        project_root = os.path.dirname(os.path.abspath(__file__))
        project_hicolor_dir = os.path.join(project_root, "assets", "icons", "hicolor")
        project_logo_path = os.path.join(project_root, "assets", "icons", "logo.png")
        
        if not os.path.exists(project_hicolor_dir):
            if logger:
                logger.warning(f"Project theme source directory {project_hicolor_dir} does not exist.")
            return

        # 1. Do NOT symlink or replace the main hicolor directory.
        # If it is currently a symlink to our project, remove the symlink.
        if os.islink(user_hicolor_dir) if hasattr(os, "islink") else os.path.islink(user_hicolor_dir):
            try:
                target = os.readlink(user_hicolor_dir)
                if "smartsort" in target or "assets/icons/hicolor" in target:
                    os.unlink(user_hicolor_dir)
                    if logger:
                        logger.info("Removed old hicolor symlink pointing to project icons.")
            except Exception as link_err:
                if logger:
                    logger.error(f"Error checking/removing hicolor symlink: {link_err}")
                    
        os.makedirs(user_hicolor_dir, exist_ok=True)
        
        sizes = ["16x16", "22x22", "24x24", "32x32", "scalable"]
        
        # 2. Copy/Create icons in ~/.local/share/icons/hicolor/{size}/apps/
        from PyQt6.QtGui import QImage
        from PyQt6.QtCore import Qt
        import shutil
        
        color_mapping = {
            "green": "smartsort-green",
            "blue": "smartsort-blue",
            "orange": "smartsort-orange",
            "red": "smartsort-red",
            "grey": "smartsort-grey",
            "yellow": "smartsort-yellow"
        }
        
        for size in sizes:
            dest_apps_dir = os.path.join(user_hicolor_dir, size, "apps")
            os.makedirs(dest_apps_dir, exist_ok=True)
            
            # Install smartsort.png
            dest_smartsort_path = os.path.join(dest_apps_dir, "smartsort.png")
            if size == "scalable":
                if os.path.exists(project_logo_path):
                    shutil.copy2(project_logo_path, dest_smartsort_path)
            else:
                # Resize and save
                try:
                    w, h = map(int, size.split("x"))
                    img = QImage(project_logo_path)
                    if not img.isNull():
                        resized = img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        resized.save(dest_smartsort_path)
                except Exception as scale_err:
                    if logger:
                        logger.error(f"Failed to scale and install smartsort.png for {size}: {scale_err}")
                        
            # Install dynamic state icons
            for color, dest_name in color_mapping.items():
                src_name = f"tray_{color}.png"
                src_path = os.path.join(project_hicolor_dir, size, "apps", src_name)
                dest_path = os.path.join(dest_apps_dir, f"{dest_name}.png")
                if os.path.exists(src_path):
                    try:
                        shutil.copy2(src_path, dest_path)
                    except Exception as copy_err:
                        if logger:
                            logger.error(f"Failed to copy {src_name} to {dest_path}: {copy_err}")
                            
        # 3. Update icon cache after installation
        import subprocess
        try:
            subprocess.run(["gtk-update-icon-cache", "-t", user_hicolor_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if logger:
                logger.info("Successfully updated icon cache for ~/.local/share/icons/hicolor")
        except Exception as cache_err:
            if logger:
                logger.error(f"Failed to update icon cache: {cache_err}")
                
    except Exception as e:
        if logger:
            logger.error(f"Failed to install user icon theme: {e}")

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
    from src.utils.logger import SmartSortLogger

    logger = SmartSortLogger()
    ensure_user_icons_installed(logger)

    app = QApplication(sys.argv)
    
    # Set up theme search paths and set application-wide branded icon
    from PyQt6.QtGui import QIcon
    if isinstance(QApplication, type) and hasattr(QApplication, "instance"):
        inst = QApplication.instance()
        if inst is not None and not hasattr(inst, "mock_calls"):
            project_root = os.path.dirname(os.path.abspath(__file__))
            icon_dir = os.path.join(project_root, "assets", "icons")
            current_paths = QIcon.themeSearchPaths()
            if icon_dir not in current_paths:
                QIcon.setThemeSearchPaths(current_paths + [icon_dir])
            
            logo_icon = QIcon.fromTheme("smartsort")
            if not logo_icon.isNull():
                app.setWindowIcon(logo_icon)
            else:
                icon_path = os.path.join(icon_dir, "logo.png")
                if os.path.exists(icon_path):
                    app.setWindowIcon(QIcon(icon_path))
        
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
