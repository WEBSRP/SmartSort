import os
from enum import Enum, auto
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

class TrayState(Enum):
    STARTUP = auto()
    IDLE = auto()
    PROCESSING_SMALL = auto()
    PROCESSING_LARGE = auto()
    ERROR = auto()
    PAUSED = auto()

class TrayStateManager:
    def __init__(self, tray_icon, parent=None):
        self.tray_icon = tray_icon
        self.parent = parent
        self.current_state = TrayState.STARTUP
        self.has_active_error = False
        self.last_error = ""
        self.processed_count = 0
        self.rules_active = 0
        self.processing_file_name = ""
        self.processing_file_size = ""
        
        # Load and cache icons
        self.icons = {}
        self._load_icons()

    def _load_icons(self):
        # Prevent QIcon loading crashes/aborts during headless unit testing
        if QApplication.instance() is None or (self.tray_icon and "Mock" in type(self.tray_icon).__name__):
            return
            
        # Determine project root dynamically based on this file's path (three levels up from src/gui/tray_manager.py)
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_file_dir))
        icon_dir = os.path.abspath(os.path.join(project_root, "assets", "icons"))
        
        logger = getattr(self.parent, "logger", None)
        if logger:
            logger.info(f"Tray Icon Path Audit: Resolving absolute assets directory to {icon_dir}")
            
        # Register the assets/icons path in Qt's icon search path fallback registry
        try:
            current_paths = QIcon.themeSearchPaths()
            if icon_dir not in current_paths:
                QIcon.setThemeSearchPaths(current_paths + [icon_dir])
                if logger:
                    logger.info(f"Tray Icon Path Audit: Added {icon_dir} to QIcon theme search paths")
        except Exception as e:
            if logger:
                logger.error(f"Tray Icon Path Audit: Failed to add search path fallback: {e}")
                
        state_mapping = {
            TrayState.STARTUP: "smartsort-yellow",
            TrayState.IDLE: "smartsort-green",
            TrayState.PROCESSING_SMALL: "smartsort-blue",
            TrayState.PROCESSING_LARGE: "smartsort-orange",
            TrayState.ERROR: "smartsort-red",
            TrayState.PAUSED: "smartsort-grey"
        }
        
        for state, prefix in state_mapping.items():
            # Try to load themed icon first for GNOME/AppIndicator compatibility
            icon = QIcon.fromTheme(prefix)
            method = "fromTheme"
            
            # Fall back to manual file loading if the icon cannot be resolved via theme
            if icon.isNull():
                icon = QIcon()
                method = "fallback-files"
                loaded_files = []
                
                color = prefix.split("-")[-1] if "-" in prefix else ""
                # Add all scaled files for sharpness across different display resolutions/scaling
                for size in ["16x16", "22x22", "24x24", "32x32"]:
                    file_name = f"tray_{color}_{size}.png" if color else f"logo_{size}.png"
                    file_path = os.path.join(icon_dir, file_name)
                    if os.path.exists(file_path):
                        icon.addFile(file_path)
                        loaded_files.append((size, file_path))
                
                # Add the original full-res file as a fallback
                full_res_name = f"tray_{color}.png" if color else "logo.png"
                full_res_path = os.path.join(icon_dir, full_res_name)
                if os.path.exists(full_res_path):
                    icon.addFile(full_res_path)
                    loaded_files.append(("original", full_res_path))
            
            self.icons[state] = icon
            
            if logger:
                logger.info(f"Tray Icon Audit - State: {state.name} | Loaded Method: {method} | isNull: {icon.isNull()}")
                
                # Diagnostics: check existence and dimensions for user's installed theme paths
                for size in ["16x16", "22x22", "24x24", "32x32"]:
                    user_theme_file = os.path.expanduser(f"~/.local/share/icons/hicolor/{size}/apps/{prefix}.png")
                    exist = os.path.exists(user_theme_file)
                    dims = "N/A"
                    if exist:
                        from PyQt6.QtGui import QImage
                        img = QImage(user_theme_file)
                        dims = f"{img.width()}x{img.height()}" if not img.isNull() else "Invalid"
                    logger.info(f"  - Size {size} (installed theme): Path: {user_theme_file} | Exist: {exist} | Dimensions: {dims}")
                
                scalable_file = os.path.expanduser(f"~/.local/share/icons/hicolor/scalable/apps/{prefix}.png")
                exist = os.path.exists(scalable_file)
                dims = "N/A"
                if exist:
                    from PyQt6.QtGui import QImage
                    img = QImage(scalable_file)
                    dims = f"{img.width()}x{img.height()}" if not img.isNull() else "Invalid"
                logger.info(f"  - Size scalable (installed theme): Path: {scalable_file} | Exist: {exist} | Dimensions: {dims}")

    def set_startup(self):
        self.current_state = TrayState.STARTUP
        self.update_tray()

    def set_monitoring(self, processed_count, rules_active):
        self.processed_count = processed_count
        self.rules_active = rules_active
        if self.has_active_error:
            self.current_state = TrayState.ERROR
        else:
            self.current_state = TrayState.IDLE
        self.update_tray()

    def set_paused(self, processed_count, rules_active):
        self.processed_count = processed_count
        self.rules_active = rules_active
        self.current_state = TrayState.PAUSED
        self.update_tray()

    def set_processing(self, filename, size_bytes):
        self.processing_file_name = filename
        
        # Format size and determine small (< 1 GB) vs large (>= 1 GB)
        is_large = False
        if isinstance(size_bytes, (int, float)):
            is_large = size_bytes >= (1024 ** 3)
            # Format size to human readable (e.g., "750 MB", "2.1 GB")
            if size_bytes >= 1024 ** 3:
                val = size_bytes / (1024 ** 3)
                self.processing_file_size = f"{val:.1f} GB" if not val.is_integer() else f"{int(val)} GB"
            elif size_bytes >= 1024 ** 2:
                val = size_bytes / (1024 ** 2)
                self.processing_file_size = f"{val:.1f} MB" if not val.is_integer() else f"{int(val)} MB"
            elif size_bytes >= 1024:
                val = size_bytes / 1024
                self.processing_file_size = f"{val:.1f} KB" if not val.is_integer() else f"{int(val)} KB"
            else:
                self.processing_file_size = f"{size_bytes} B"
        else:
            self.processing_file_size = str(size_bytes)
            try:
                from src.rules.conditions import parse_size_to_bytes
                parsed_bytes = parse_size_to_bytes(size_bytes)
                is_large = parsed_bytes >= (1024 ** 3)
            except Exception:
                pass
                
        if is_large:
            self.current_state = TrayState.PROCESSING_LARGE
        else:
            self.current_state = TrayState.PROCESSING_SMALL
            
        self.update_tray()

    def set_success(self, processed_count, rules_active):
        self.has_active_error = False
        self.last_error = ""
        self.processed_count = processed_count
        self.rules_active = rules_active
        self.current_state = TrayState.IDLE
        self.update_tray()

    def set_error(self, error_msg):
        self.has_active_error = True
        self.last_error = error_msg
        self.current_state = TrayState.ERROR
        self.update_tray()

    def update_tray(self):
        if not self.tray_icon:
            return
            
        # Tooltip formatting per task specifications
        if self.current_state == TrayState.STARTUP:
            tooltip = "SmartSort\nStatus: Startup / Initial Scan"
        elif self.current_state == TrayState.IDLE:
            tooltip = f"SmartSort\nStatus: Monitoring\nFiles Processed: {self.processed_count}\nRules Active: {self.rules_active}"
        elif self.current_state == TrayState.PAUSED:
            tooltip = f"SmartSort\nStatus: Paused\nFiles Processed: {self.processed_count}\nRules Active: {self.rules_active}"
        elif self.current_state == TrayState.PROCESSING_SMALL:
            tooltip = f"SmartSort\nStatus: Processing\nFile: {self.processing_file_name}\nSize: {self.processing_file_size}"
        elif self.current_state == TrayState.PROCESSING_LARGE:
            tooltip = f"SmartSort\nStatus: Processing\nFile: {self.processing_file_name}\nSize: {self.processing_file_size}"
        elif self.current_state == TrayState.ERROR:
            tooltip = f"SmartSort\nStatus: Error\nLast Error: {self.last_error}"
        else:
            tooltip = "SmartSort"

        # Update tray icon if loaded
        if self.current_state in self.icons:
            self.tray_icon.setIcon(self.icons[self.current_state])
            
        # Update tray tooltip (limit length to be safe with all system trays)
        self.tray_icon.setToolTip(tooltip[:127] if len(tooltip) > 127 else tooltip)
