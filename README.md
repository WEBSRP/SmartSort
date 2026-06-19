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

## Systemd Service

To run SmartSort as an automatic background service on startup:

### 1. Copy the Service Configuration
```bash
mkdir -p ~/.config/systemd/user/
cp smartsort.service ~/.config/systemd/user/
```

### 2. Start and Enable the Service
```bash
systemctl --user daemon-reload
systemctl --user enable smartsort.service
systemctl --user start smartsort.service
```

### 3. Check Service Logs
```bash
systemctl --user status smartsort.service
```

---

## Configuration

Settings are stored in `config/config.json` and configurable in the GUI Settings panel:
* **Downloads folder**: Path to directory monitored by the observer. SmartSort automatically resolves `~/Downloads` to the current user's Downloads folder.
* **Notifications**: Toggle to push DBus alerts for successful transfers and errors.
* **Duplicate detection**: Check SHA256 hashes of matching files. If identical, skips transfer and preserves the original.
* **Conflict resolution**: Collision policy on filename overlaps:
  - `rename` (Default): Appends increments (e.g. `_1`, `_2`) to destination file.
  - `overwrite`: Overwrites the target file.
  - `skip`: Skips copying.
* **Large file threshold**: Size string (e.g., `2.5GB`, `500MB`) specifying size threshold for large file warnings.

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
