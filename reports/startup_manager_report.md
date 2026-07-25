# Startup and Background Service Management Redesign Report

This report documents the design and implementation of the redesigned **Startup Manager** and **Background Service Manager** for SmartSort. The updates decouple startup capabilities from background process management, introduce unified package detection, and implement a self-healing auto-repair mechanism.

---

## 1. Package Detection Layer (`src/utils/packaging.py`)

Rather than scattered platform checks, the system centralizes runtime package state checks through a unified environment wrapper:
- **`PackageType` Enum**: Defines `SOURCE`, `DEBIAN`, `APPIMAGE`, and `FLATPAK` states.
- **`detect_package_type()`**: Runs path, capability, and container check algorithms to return the precise environment context.
- Used universally across:
  - Startup launch verification
  - Autostart path and command generators
  - Graphical icon installations
  - Settings UI page layouts

---

## 2. Startup Manager (`src/utils/autostart.py`)

Manages standard XDG startup configurations (`~/.config/autostart/smartsort.desktop`) based on the running package type:

- **SOURCE**: Uses Python interpreter with absolute path to `main.py`:
  `Exec="/usr/bin/python3" "/path/to/main.py" --service`
- **DEBIAN**: Launches the package's global wrapper command:
  `Exec=/usr/bin/smartsort --service`
- **APPIMAGE**: Runs the portable AppImage bundle path:
  `Exec="/path/to/SmartSort.AppImage" --service`
- **FLATPAK**: Executes the container execution command directly:
  `Exec=flatpak run com.smartsort.SmartSort --service`

Toggling the startup checkbox immediately creates or unlinks the desktop entry and notifies the user via desktop portals.

---

## 3. Background Service Manager (`src/gui/main_window.py`)

Background service controls are displayed in the **Background Monitoring** settings group box, tailored by package capabilities:

### Debian & Source Runtimes
Exposes granular service administration actions:
- **Install Service**: Creates systemd service file `~/.config/systemd/user/smartsort.service`, reloads daemon, enables, and starts it.
- **Remove Service**: Stops and disables the service, unlinks the file, and reloads daemon.
- **Start / Stop / Restart**: Commands user-level systemd process status directly.
- **Enable / Disable**: Updates systemd autostart boot registration.

### AppImage Portable Runtime
Provides package-relocation aware actions:
- **Install Background Service**: Writes a systemd user unit executing the current AppImage path.
- **Remove**: Stops, disables, and deletes the unit file.
- **Update**: Re-points the service configuration dynamically to the current AppImage location.

### Flatpak Sandbox Runtime
- Shows label: *"Background services are not available inside the Flatpak sandbox."*
- All background service controls are hidden, avoiding runtime exceptions.

---

## 4. Self-Healing & Automatic Repair Mechanism

On every launch of SmartSort, the system triggers `verify_and_repair_startup_config` after one second:
1. **Verification**: Checks if the autostart checkbox expectation in configuration matches reality.
2. **Missing / Corrupted Detection**: Checks for missing desktop files or corrupted files (lacking standard headers or pointing to wrong Exec commands).
3. **AppImage Relocation Check**: Determines if the running AppImage differs from the desktop entry path.
4. **One-Click Repair**: Offers the user a modal dialog to rebuild/repoint configurations. If accepted, repairs take place immediately and notify the user.

---

## 5. Settings UI Layout Upgrades

The **Settings** page has been restructured into two main sections:
- **Application Startup**: Contains checkboxes for *"Start SmartSort automatically when I log in"* and *"Start minimized to tray"*, plus theme selections. Toggling these checkbox controls saves settings and triggers system changes immediately.
- **Background Monitoring**: Houses the tailored systemd status labels and command buttons per runtime capability.
