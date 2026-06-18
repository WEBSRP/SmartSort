# SmartSort

SmartSort is an automated file organizer for Linux that monitors your Downloads directory and sorts files into categories based on extensions, filenames, and size.

## Features

- **Real-time Monitoring**: Uses `watchdog` to detect new files instantly.
- **Safe Transfer**: Copy -> Verify (SHA256) -> Delete workflow ensures zero data loss.
- **Intelligent Categorization**: Sorts by extension and keywords (e.g., Cybersecurity, College).
- **Large File Protection**: Requests confirmation before moving files >= 2.5 GB.
- **Duplicate Detection**: Prevents overwriting identical files using hash comparison.
- **GUI Dashboard**: Built with PyQt6 for easy management and log viewing.
- **Systemd Integration**: Runs as a background service.

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repo_url>
   cd smartsort
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python3 main.py
   ```

## Service Setup

To run SmartSort as a background service:

1. **Copy the service file**:
   ```bash
   cp smartsort.service ~/.config/systemd/user/
   ```

2. **Reload systemd and enable**:
   ```bash
   systemctl --user daemon-reload
   ```

3. **Start the service**:
   ```bash
   systemctl --user start smartsort.service
   ```

## Configuration

Settings and rules are stored in `config/config.json`. You can manage these directly through the "Settings" and "Rules" tabs in the GUI.

## Safety First

- **Offline**: No cloud services, no telemetry, no internet access required.
- **Data Integrity**: Files are never deleted unless the copy is verified with a SHA256 hash.
- **Error Handling**: All exceptions are logged, and critical errors trigger desktop notifications.
