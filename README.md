# SmartSort

SmartSort is an offline Linux file automation and organization platform built in Python and PyQt6. It monitors your Downloads folder in real-time and automatically sorts incoming files into category directories using a dynamic, priority-sorted rule engine.

---

## Features

* **Real-time Downloads Monitoring**: Hooks directory change events using `watchdog` to detect new or completed browser downloads.
* **Rule-based File Organization**: Evaluates composite condition filters (AND logic) dynamically to decide file categories and destinations.
* **GUI Rule Editor**: Add, Edit, Delete, Enable, Disable, and re-order rules (Move Up / Down) inside a list view without editing JSON.
* **Rule Priority System**: Evaluates rules sequentially based on user-defined priority numbers (first match wins).
* **Image Quality Classification**: Automatically sorts image files (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`) into high, medium, or low quality directories based on file size.
* **Duplicate Detection**: Prevents copying duplicate files if an identical file matching the SHA256 checksum already exists at the target path.
* **Conflict Resolution**: Supports configurable policies (`rename`, `overwrite`, `skip`) to handle destination filename collisions.
* **Safe Transfers**: Executes a strict Copy → Verify (SHA256 checksum) → Delete original workflow to ensure zero data loss.
* **Desktop Notifications**: Pushes DBus alerts via `notify2` for successful actions and critical errors.
* **Rule Testing Sandbox**: Contains a Rule Tester tab where users can preview matching rules, priorities, and destination templates for virtual filenames and sizes.
* **Automatic Config Backups**: Automatically creates `.bak` backups before config writes, restoring from backup if the primary config is corrupted.
* **Logging and Reports**: Creates daily logs and generates detailed implementation, migration, and testing reports under `reports/`.
* **Portable Configuration**: Employs home-directory expansion (`~`) so settings work out-of-the-box across different Linux user accounts without hardcoded user paths.
* **No Hardcoded User Paths**: Eliminates developer-specific absolute paths from the default configuration.
* **Works Across Linux User Accounts**: Automatically resolves home directories dynamically based on the current active user.
* **Fully Offline Operation**: Zero cloud calls, telemetry, or external dependencies.

---

## Screenshots

Below are placeholders for the interface:

![Dashboard](docs/screenshots/dashboard.png)
*Dashboard showing real-time logs and statistics.*

![Rules Editor](docs/screenshots/rules.png)
*Graphical Rule List Editor and Condition Dialog Builder.*

![Settings Panel](docs/screenshots/settings.png)
*Configuration settings showing paths, threshold size, and behavior toggles.*

![Rule Tester Sandbox](docs/screenshots/rule_tester.png)
*Interactive Rule testing sandbox tab.*

---

## Project Structure

```
SmartSort/
├── config/              # Configuration files (config.json, default_config.json)
├── logs/                # Daily execution action logs
├── reports/             # System migration, test, and implementation reports
├── src/                 # Application codebase
│   ├── gui/             # PyQt6 windows, dialogs, and tester interface
│   ├── rules/           # Rule engine models, conditions, and manager logic
│   └── utils/           # Utilities (configuration loaders, SHA256 checkers, loggers)
├── tests/               # Pytest automated test suites
├── main.py              # Application main entry point
├── smartsort.service    # systemd user service script
└── README.md            # Project documentation
```

---

## How It Works

```
[ File Detected ]
       ↓
[ Rule Evaluation ]  ← Check extension, keywords, regex, size
       ↓
[ Destination Selected ]  ← Dynamic variables expansion ({extension}, {filename})
       ↓
[ Copy File ]
       ↓
[ SHA256 Verification ]
       ↓
[ Delete Original ] (Only if checksum matches)
       ↓
[ Log Result ]
```

---

## Rule Engine

All file sorting decisions are determined by the Rule Engine.

* **Rules**: Consist of a Name, Enabled status, Priority, Conditions, and Destination template.
* **Priorities**: Rules are evaluated in ascending order of their priority numbers (e.g. Priority 1 runs first). Priorities must be unique.
* **Conditions**: Rules evaluate multiple checks with logical **AND** behavior. Individual conditions support:
  - **Extension**: Matches file extensions (comma-separated, case-insensitive).
  - **Filename Contains**: Matches filename substring keywords (comma-separated, case-insensitive).
  - **File Size**: Compares size thresholds (operators `>`, `<`, `>=`, `<=`, `==`, supporting units like `GB`, `MB`, `KB`, `B`).
  - **Regex**: Matches advanced Python regular expressions on filenames.
* **Fallback Behavior**: If a file does not match any active rules, it is categorized as `"Others"` and moved to the fallback folder `Others/` by default.

---

## Image Quality Classification

Image files matching extensions (`jpg`, `jpeg`, `png`, `webp`, `gif`, `bmp`) are automatically classified entirely via size-based rules:

```
Pictures/
├── Low_Quality/          # Files < 1 MB
├── Medium_Quality/       # Files >= 1 MB and < 5 MB
└── High_Quality/         # Files >= 5 MB
```

Destinations support template variables:
* `{extension}`: Replaced by the uppercase file extension (e.g. `JPG`).
* `{filename}`: Replaced by the source filename (e.g. `image.jpg`).

*Example Destination Template*: `Pictures/Low_Quality/{extension}` matches `photo.jpg` resulting in `Pictures/Low_Quality/JPG/photo.jpg`.

---

## Installation

SmartSort is designed for Linux systems. No path modifications are required after installation. The application automatically detects and adapts to the current user's home directory.

### 1. Debian / Ubuntu System Dependencies
Ensure Python 3 and basic graphical environment tools are installed:
```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip libglib2.0-0
```

### 2. Setup Virtual Environment & Dependencies
Initialize the virtual environment inside the repository:
```bash
python3 -m venv smartsort
source smartsort/bin/activate
pip install -r requirements.txt
```

### 3. Run the Application
```bash
python3 main.py
```

---

## Background Service & System Tray

SmartSort can run fully in the background as a Linux desktop service. Closing the dashboard window hides it to the system tray, while file monitoring continues unimpeded.

### System Tray Menu Options
The tray icon context menu provides quick controls:
* **Open Dashboard / Rules / Rule Tester / Settings**: Displays the dashboard window directly at the corresponding tab.
* **Pause / Resume Monitoring**: Temporarily disables or re-enables directory observation.
* **Show Statistics**: Displays files processed, duplicate saves, and error metrics.
* **Open Reports Folder**: Opens the reports directory.
* **Restart / Exit**: Restarts or shuts down SmartSort.

### Dynamic Tray Status Indicators & Branding
The system tray icon updates color and tooltip status dynamically to convey the active operational state of the file organizer:

* 🟡 **Yellow (Startup)**: Application startup / initial folder scan phase.
* 🟢 **Green (Idle/Monitoring)**: Actively watching downloads directory for file events.
* 🔵 **Blue (Processing)**: Currently organizing a file smaller than 1 GB.
* 🟠 **Orange (Processing Large File)**: Currently organizing a large file (1 GB or larger).
* 🔴 **Red (Error)**: Active processing or write error. Persists until the next successful operation.
* ⚫ **Grey (Paused)**: File monitoring has been paused by the user.

#### Tooltip Contexts
Tooltips update dynamically depending on the state, using clean formatting:
* **Idle/Paused Tooltip**:
  ```text
  SmartSort
  Status: Monitoring (or Paused)
  Files Processed: 124
  Rules Active: 10
  ```
* **Processing Tooltip**:
  ```text
  SmartSort
  Status: Processing
  File: movie.mkv
  Size: 850 MB
  ```
* **Error Tooltip**:
  ```text
  SmartSort
  Status: Error
  Last Error: Permission denied
  ```

#### Branded Icon System
SmartSort features a custom branded icon system located in [assets/icons/](file:///home/websrp/project/smartsort/assets/icons/):
* **Main Application Logo** (`logo.png`): Serves as the main window icon, the taskbar icon, the About dialog icon, and the GNOME desktop launcher icon.
* **Multi-Resolution Support**: We keep the full-resolution source icons and generate optimized tray sizes (16x16, 22x22, 24x24, 32x32). PyQt6 automatically loads these sizes to ensure that icons remain extremely sharp on any display panel scaling or top-bar layout.

---

## Daemon Mode

To run SmartSort in a headless environment without a graphical environment:
```bash
python3 main.py --daemon
```
In daemon mode, the application runs entirely in the background, executing logging, notifications, and rule-engine organizing on incoming downloads without GUI memory overhead.

---

## Service & Startup Management

SmartSort provides options to manage startup and execution directly from the GUI Settings panel:

### 1. Auto Start
Toggle the **Start SmartSort Automatically at Login** checkbox. When enabled, this creates a standard Linux autostart desktop entry at `~/.config/autostart/smartsort.desktop`, launching SmartSort in service mode on desktop login.

### 2. Start Minimized
Toggle the **Start SmartSort Minimized (to Tray)** checkbox. When enabled, launching the application initializes the system tray icon directly without opening the dashboard window.

### 3. Systemd User Service Controls
The Settings panel includes GUI buttons to manage the background service at the OS level:
* **Install Service**: Generates a portable, user-specific service script at `~/.config/systemd/user/smartsort.service` and registers it.
* **Start Service**: Starts the background daemon via systemd.
* **Stop Service**: Stops the active systemd service.
* **Restart Service**: Restarts the systemd daemon.

### 4. Terminal Command Line Instructions

You can also manage the SmartSort services directly from your terminal:

* **Enable on Login**:
  ```bash
  systemctl --user enable smartsort.service
  ```
* **Start Service Immediately**:
  ```bash
  systemctl --user start smartsort.service
  ```
* **Stop Service**:
  ```bash
  systemctl --user stop smartsort.service
  ```
* **Disable on Login**:
  ```bash
  systemctl --user disable smartsort.service
  ```
* **Check Service Status**:
  ```bash
  systemctl --user status smartsort.service
  ```
* **View Service Logs**:
  ```bash
  journalctl --user -u smartsort.service -n 50 -f
  ```

#### Comparison of Auto-Launch Methods:
* **GNOME Autostart (`.desktop` entry)**: Best for standard GUI environments. Launches the PyQt6 GUI minimized to the system tray on login, giving you full access to the interactive dashboard, rule editor, and system tray actions.
* **Systemd User Service (`.service` entry)**: Best for headless/server environments or users who prefer a quiet background organizer. Runs in a dedicated background `--daemon` mode, avoiding Qt GUI initialization overhead.
* *Note: Avoid running both concurrently to prevent redundant directory watchers and race conditions.*

---

## Configuration

Settings are stored in `config/config.json` and are fully customizable in the GUI:
* **Downloads folder**: Monitored path. Resolves `~/Downloads` dynamically to the current user's profile path.
* **Start Minimized**: If enabled, starts hidden in the system tray.
* **Autostart**: Automatically registers startup script.
* **Theme**: Supports `System Theme`, `Dark Mode`, and `Light Mode`.
* **Notifications**: Toggle DBus desktop notification alerts.
* **Duplicate detection**: Performs SHA256 checksum checks to avoid duplicate writes.
* **Conflict resolution**: Collision policy (`rename`, `overwrite`, `skip`).
* **Large file threshold**: Warning size string (e.g. `2.5GB`, `500MB`).

---

## Path Handling

SmartSort automatically resolves user home directories dynamically based on the current active user, meaning that no user-specific hardcoded paths are required in the default configuration files.

### Example

**Configuration:**
```json
{
  "downloads_folder": "~/Downloads"
}
```

**Runtime Expansion:**
* User **alice**: `~/Downloads` &rarr; `/home/alice/Downloads`
* User **bob**: `~/Downloads` &rarr; `/home/bob/Downloads`

---

## Machine-Specific Paths

Examples:
* `/home/websrp/project/smartsort`

Users installing SmartSort should update these paths for their environment.

---

## Technical Notes

Path resolution uses:
* `pathlib.Path.expanduser()`

This allows SmartSort to automatically adapt to the active Linux user at runtime without requiring manual path modifications in `config/config.json`.

---

## Rule Examples

### Example: Large Videos
* **Conditions**:
  - Extension = `.mkv, .mp4`
  - File Size = `> 2.5GB`
* **Destination**: `Videos/Big_Videos`

### Example: College Papers
* **Conditions**:
  - Filename contains = `assignment, semester, syllabus`
  - Extension = `.pdf, .docx`
* **Destination**: `Documents/College`

---

## Rule Tester

Before activating a rule, use the **Rule Tester** sandbox tab in the GUI to verify behavior. Enter a test filename, size (e.g. `2MB`), and extension, then click **Test** to view which rule matches and preview the target destination path.

---

## Reports

System logs and development summaries are stored under `reports/`:
* [phase2_implementation_report.md](reports/phase2_implementation_report.md): Refactoring changes, issue tracker, architecture layouts, and root cause analysis.
* [test_results.md](reports/test_results.md): Pytest execution log results.
* [migration_notes.md](reports/migration_notes.md): Notes on automatic conversions of legacy categories configurations.
* [size_threshold_fix_report.md](reports/size_threshold_fix_report.md): Large file settings size parsing bugfix report.
* [path_portability_fix_report.md](reports/path_portability_fix_report.md): SmartSort portability improvement report describing home directory tilde expansion.
* [readme_update_report.md](reports/readme_update_report.md): Report on the documentation updates and portability validation.
* [handover_report.md](reports/handover_report.md): SmartSort portability & documentation update handover report.
* [phase4_background_service_report.md](reports/phase4_background_service_report.md): Background service daemon and tray integration report.
* [ui_modernization_report.md](reports/ui_modernization_report.md): GNOME Adwaita UI design modernization report.
* [service_installation_report.md](reports/service_installation_report.md): User systemd automation installation report.
* [startup_automation_fix_report.md](reports/startup_automation_fix_report.md): Report on startup automation fixes, path replacements, and systemd integration.
* [background_startup_report.md](reports/background_startup_report.md): Report on true background operation, GNOME Autostart integration, and system tray startup robustness.
* [config_initialization_fix_report.md](reports/config_initialization_fix_report.md): Report on configuration initialization fixes, defaults validation, and crash prevention.
* [tray_status_indicator_report.md](reports/tray_status_indicator_report.md): Report on dynamic system tray status indicators, tooltips, and state management.
* [icon_system_implementation_report.md](reports/icon_system_implementation_report.md): Report on SmartSort branded icon system and dynamic tray status indicator implementation.

---

## Testing

Automated tests check conditions, priorities, variables, config integrity, and log retention.

Run tests using the venv launcher:
```bash
PYTHONPATH=. ./smartsort/bin/pytest
```

---

## Roadmap

The following enhancements are planned for future updates:
* **Rule Import/Export**: Save and load rules to share setups across systems.
* **Rule Profiles**: Switch configurations quickly (e.g. Work, General, Declutter).
* **Statistics Dashboard**: Visual charts showing file volumes, processed files, and duplicates saved over time.
* **Dry Run Mode**: Preview sorting actions without executing copies or deletes.
* **Enhanced Reporting**: HTML layout reports of automated transfers.

---

## Changelog

### Path Portability Improvement

* Removed user-specific default paths
* Added automatic home-directory expansion
* Improved cross-user compatibility

---

## Author

* **Author**: Soumya Ranjan Parida
* **GitHub**: [SmartSort Repository](https://github.com/smartsort-org/SmartSort)

---

## License

License to be decided.
