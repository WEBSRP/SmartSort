<div align="center">

# 🚀 SmartSort

### Intelligent Download Organizer for Linux

Organize your Downloads folder automatically — fast, lightweight and built natively for Debian.

<p align="center">
  <img src="assets/animation.gif" alt="SmartSort Demo" width="900">
</p>

<p align="center">
  <strong>Drop a file. SmartSort does the rest.</strong>
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Debian](https://img.shields.io/badge/Debian-12+-A81D33?style=for-the-badge&logo=debian)
![PyQt6](https://img.shields.io/badge/PyQt6-Desktop-41CD52?style=for-the-badge&logo=qt)
![License](https://img.shields.io/github/license/WEBSRP/SmartSort?style=for-the-badge)
![Release](https://img.shields.io/github/v/release/WEBSRP/SmartSort?style=for-the-badge)

</p>

<p align="center">

Automatically monitors your Downloads folder, intelligently categorizes files and keeps your system organized in real time.

</p>

</div>

---

# ✨ Features

- 📂 Real-time Downloads folder monitoring
- 📄 Automatic file categorization
- ⚙️ Custom user-defined sorting rules
- 📦 Duplicate detection
- 🔔 Desktop notifications
- 🖥️ System tray integration
- 🎨 Modern PyQt6 interface
- 🚀 Lightweight background service
- 🐧 Native Debian package
- 🔓 Fully Open Source

---

# 🎬 Demo

SmartSort continuously watches your Downloads folder.

Whenever a new file appears, it is analysed and automatically moved to its appropriate destination.

```
Downloads
│
├── report.pdf
├── holiday.mp4
├── wallpaper.png
├── archive.zip
├── music.mp3
└── installer.deb

            │
            ▼

      🚀 SmartSort

     Detects
        │
     Analyses
        │
   Applies Rules
        │
     Organizes

            ▼

📄 Documents
🎬 Videos
🖼 Pictures
📦 Archives
🎵 Music
⚙ Packages
```

No manual sorting.
No clutter.

Just download and continue working.

---

# 📁 Supported Categories

| Category | Examples |
|-----------|-----------|
| 📄 Documents | PDF, DOCX, PPTX, XLSX, TXT |
| 🖼 Images | PNG, JPG, JPEG, GIF, SVG |
| 🎬 Videos | MP4, MKV, AVI, MOV |
| 🎵 Audio | MP3, WAV, FLAC |
| 📦 Archives | ZIP, RAR, 7Z, TAR |
| 💻 Executables | DEB, AppImage, BIN |
| 💾 Disk Images | ISO |
| 📁 Others | Custom Rules |

---

# 🧹 Smart Filename Cleanup

Automatically detects and renames generic, meaningless, or excessively long filenames before categorizing and moving them.

### Examples

- `_.jpg` → `reddit.jpg` (or `image.jpg` fallback)
- `download.pdf` → `github.pdf` (or `document.pdf` fallback)
- `IMG_0001.png` → `pinterest.png`
- `53+ Trèfle à quatre feuilles Wallpapers...jpeg` → `wallpaperflare.jpeg`

### Configuration

Enable or disable in **Settings → Advanced Settings → Enable Smart Filename Cleanup** or in `config.json`:

```json
{
    "smart_filename_cleanup": true,
    "filename_min_length": 4,
    "filename_max_length": 80
}
```

### Limitations

- Source website detection uses local extended attributes (`user.xdg.referrer.url` / `user.xdg.origin.url`) set by Linux browsers (Chrome, Firefox). If no metadata is present, it uses intelligent extension-based category fallbacks (`image.jpg`, `document.pdf`, `video.mp4`, etc.).
- Network requests are never performed to fetch metadata.

---

# 🔔 Clickable Notifications

When a file is successfully processed, SmartSort sends a desktop notification.

Clicking the notification automatically opens the destination directory in your default desktop file manager (Nautilus, Dolphin, Thunar, etc.) and highlights/selects the organized file.

### Highlighting Hierarchy

1. **`org.freedesktop.FileManager1` DBus `ShowItems`** (highlights the file in GNOME, KDE, etc.)
2. **`xdg-open`** (opens the parent directory as a fallback)
3. **`gio open`** (opens the parent directory as a secondary fallback)

Notifications reuse the existing **Enable Desktop Notifications** setting in Settings.

---

# 🗂 Directory Organizer

Organize any folder on demand directly from the SmartSort Dashboard.

- **Selective or Recursive Scanning**: Organize only root files or process entire directory trees.
- **Dry-Run Preview**: Inspect planned moves and category distributions before modifying any files.
- **6-Stage Copy-Verify-Delete Safety**: Cryptographic SHA-256 integrity verification guarantees zero data loss.
- **Content Duplicate Preservation**: Duplicates with matching hashes are safely preserved untouched without overwriting destinations.
- **Searchable Markdown Index**: Automatically generates `SmartSort_Arrangement.md` with offline clickable `file:///` links.

---

# 📦 Installation

Download the latest Debian package from the **Releases** page.

```bash
sudo dpkg -i smartsort_1.1.6_all.deb

sudo apt-get install -f
```

Launch **SmartSort** from your Applications menu.

---

# 🛠 Build From Source

Clone the repository

```bash
git clone https://github.com/WEBSRP/SmartSort.git

cd SmartSort
```

Create a virtual environment

```bash
python3 -m venv .venv

source .venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run SmartSort

```bash
python main.py
```

---

# 🧪 Testing

Run the complete test suite

```bash
pytest
```

Current Status

- ✅ All tests passing
- ✅ GitHub Actions verified
- ✅ Debian package builds successfully
- ✅ Fresh installation verified

---

# 📂 Repository Structure

```
SmartSort
│
├── assets/
│   ├── animation.gif
│   └── icons/
│
├── docs/
├── packaging/
├── reports/
├── src/
├── tests/
│
├── main.py
├── pyproject.toml
└── README.md
```

---

# 🧠 How It Works

```
File Created

      │

      ▼

Detect Extension

      │

      ▼

Check User Rules

      │

      ▼

Determine Category

      │

      ▼

Move File

      │

      ▼

Desktop Notification
```

Everything happens automatically in the background.

---

# 📈 Why SmartSort?

Instead of manually cleaning your Downloads folder every few days...

SmartSort organizes everything the moment it arrives.

Whether you're downloading:

- University notes
- Movies
- Music
- Source code
- Archives
- Software packages
- Images

SmartSort keeps everything exactly where it belongs.

---

# 🛣 Roadmap

- ✅ Intelligent file categorization
- ✅ Custom sorting rules
- ✅ Desktop notifications
- ✅ Debian packaging
- ✅ GitHub Actions CI
- ✅ Modern PyQt6 UI
- 🔄 AI-assisted file classification
- 🔄 Rule marketplace
- 🔄 Plugin support

---

# 🤝 Contributing

Contributions are always welcome.

If you'd like to improve SmartSort:

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Open a Pull Request

Bug reports and feature requests are appreciated.

---

# 📜 License

This project is licensed under the MIT License.

See the LICENSE file for details.

---

<div align="center">

## ⭐ If SmartSort saves you time, consider starring the repository.

Made with ❤️ using Python & PyQt6

</div>
