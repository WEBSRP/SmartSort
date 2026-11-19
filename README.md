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

SmartSort uses filenames, file contents and your rules to organize downloads locally. It works offline without an AI model.

</p>

</div>

---

# ✨ Features

- 📂 Real-time Downloads monitoring with optional subfolder scanning
- 📄 Local sorting by file type and purpose
- ⚙️ Custom sorting rules with a preview in Rule Tester
- 📦 SHA-256 verification before removing a duplicate source copy
- 🔔 Desktop notifications
- 🖥️ System tray integration
- 🎨 Light and dark PyQt6 themes
- 🚀 Lightweight background service
- 🐧 Native Debian package with a single-instance dashboard
- 🔓 Fully Open Source

---

# 🎬 Demo

SmartSort continuously watches your Downloads folder.

With desktop defaults enabled, a download such as `forest_wallpaper.jpg` can go to Pictures/Wallpapers. A generic photo goes to Pictures when there are no clues about its purpose.

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
   Chooses folder
        │
     Organizes

            ▼

📄 Documents
🎬 Videos
🖼 Pictures
📦 Archives
🎵 Music
⚙ Applications
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
| 📁 Others | Files with no recognized category |

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

Open **Organize folder**, choose a folder and review the proposed destinations. All moves in this batch stay inside the selected folder.

- **Scan subfolders.** Content intelligence includes subfolders by default. Recognized projects and app bundles stay together. Put an empty `.smartsort-ignore` file inside a custom folder to protect it.
- **Review moves.** Inspect the proposed paths, confidence and reasons before running the batch.
- **Verify transfers.** SmartSort checks the copied file’s SHA-256 before removing the source. With duplicate detection enabled, a verified match removes the incoming copy and keeps the existing destination.
- **Reverse moves.** Choose **Reverse moves** in the completion popup or on the folder page within **10 minutes**, while SmartSort is open. It restores files to their original paths, including removed duplicate copies, and reports conflicts if files have changed.
- **Open the arrangement report.** Enable the optional Markdown index to get local file links in `SmartSort_Arrangement.md`.

---

# 📦 Installation

From the directory containing the SmartSort 1.2.12 Debian package, run the following command.

```bash
sudo apt install ./smartsort_1.2.12_all.deb
```

Launch **SmartSort** from your Applications menu.

To use content/context-based sorting, open **Settings → File intelligence**,
select **Content intelligence — analyze all files**, and **Save settings**.
For a manual override, select **Use this rule in Content intelligence** in the rule editor.
**Rules first** applies your enabled rules in priority order. Dashboard and Organize folder show the active mode.
Restart a separately running background service after saving its settings.

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

Run the complete test suite using Qt’s offscreen backend

```bash
QT_QPA_PLATFORM=offscreen python3 -m pytest
```

Local verification for 1.2.12

- ✅ 1,735 tests passed and one was skipped
- ✅ Debian package built and its contents checked
- ✅ Folder organization and reversal tested from the extracted package

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

Inspect File

      │

      ▼

Check Sorting Mode

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
- ✅ Offline, rule-based purpose detection
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

This project is licensed under the GNU General Public License v3.0.

See the LICENSE file for details.

---

<div align="center">

## ⭐ If SmartSort saves you time, consider starring the repository.

Made with ❤️ using Python & PyQt6

</div>

In **Content intelligence** mode, **Organize folder** includes subfolders by
default, and the Downloads watcher also watches new files in nested folders.
Use **Preview → Review moves** to sort an existing folder tree. Turn off
**Include subfolders** for a top-level folder preview, or disable the separate
Downloads subfolder option in Settings.


Recursive sorting keeps recognizable app bundles and project folders intact.
For any custom folder that should remain together, add an empty
`.smartsort-ignore` file inside it before sorting.

**Rule Tester** now uses the saved sorting mode, including Content intelligence.
Choose **Existing file — content analysis** to preview a real file's destination,
confidence and reasons without moving it. Filename/size tests show available
filename/type evidence. For example, `leetcode_two_sum.png` can route to
`Pictures/Coding_Challenges` from its name. SmartSort does not interpret image pixels.
See [Rule Tester](docs/rule-tester.md).

Loose code is grouped by language, such as `Code/Shell` and `Code/Python`;
real-file intelligence can refine it to `Projects/Source/<language>`. Recognized
project folders stay intact, including when an internal subfolder is selected.

Home-based download sorting reuses the Linux desktop's existing Pictures, Videos,
Music and Documents folders. Academic, work and code categories live under
Documents. See [desktop destination folders](docs/desktop-folders.md).
