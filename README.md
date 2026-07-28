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

# ⚡ Installation

Download the latest Debian package from the **Releases** page.

```bash
sudo dpkg -i smartsort_1.0.3_all.deb

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
