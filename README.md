<div align="center">

# 🚀 SmartSort

### Intelligent Download Organizer for Linux

Automatically detects, categorizes and organizes your downloads in real time.

<!-- Hero Video -->
https://github.com/YOUR_USERNAME/SmartSort/raw/main/assets/animation.mp4

---

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Debian](https://img.shields.io/badge/Debian-Supported-A81D33?style=for-the-badge&logo=debian)
![PyQt6](https://img.shields.io/badge/PyQt6-GUI-41CD52?style=for-the-badge&logo=qt)
![License](https://img.shields.io/github/license/YOUR_USERNAME/SmartSort?style=for-the-badge)

**Built for users who never want to manually organize their Downloads folder again.**

</div>

---

# ✨ What SmartSort Does

SmartSort continuously monitors your Downloads folder and automatically moves files into the correct destination based on intelligent rules.

```
Downloads
│
├── report.pdf
├── movie.mp4
├── image.png
├── archive.zip
├── music.mp3
└── setup.deb

        │
        ▼

      SmartSort

        │
        ▼

📄 Documents
🎬 Videos
🖼 Pictures
📦 Archives
🎵 Music
⚙ Packages
```

---

# ⚡ Features

- 📂 Real-time download monitoring
- 📄 Automatic file categorization
- 🎯 Custom sorting rules
- 📦 Duplicate detection
- 🖥 Modern PyQt6 desktop interface
- 🔔 Desktop notifications
- ⚙ System tray integration
- 🚀 Lightweight and fast
- 🐧 Native Debian package

---

# 🎬 Demo

The animation above shows SmartSort working in real time.

✔ Detects a new file

✔ Identifies its category

✔ Organizes it automatically

No manual dragging.

No clutter.

No wasted time.

---

# 📁 Supported Categories

| File Type | Destination |
|-----------|-------------|
| PDF, DOCX, TXT | Documents |
| PNG, JPG, GIF | Pictures |
| MP4, MKV, AVI | Videos |
| MP3, FLAC | Music |
| ZIP, RAR, 7Z | Archives |
| DEB | Packages |
| Others | Custom Rules |

---

# 📦 Installation

Download the latest Debian package from the Releases page.

```bash
sudo dpkg -i smartsort_1.0.3_all.deb
sudo apt-get install -f
```

Launch SmartSort from the Applications menu.

---

# 🛠 Build from Source

```bash
git clone https://github.com/WEBSRP/SmartSort.git

cd SmartSort

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

python main.py
```

---

# 🧪 Testing

```bash
pytest
```

Current Status

- ✅ All tests passing
- ✅ Debian package builds successfully
- ✅ GitHub Actions validated

---

# 📂 Project Structure

```
SmartSort/
│
├── assets/
├── docs/
├── packaging/
├── reports/
├── src/
├── tests/
├── main.py
└── README.md
```

---

# 💡 Why SmartSort?

Downloads folders become messy quickly.

SmartSort quietly watches in the background and keeps everything organized automatically, so your files are always where you expect them to be.

---

# 🛣 Roadmap

- [x] Intelligent file categorization
- [x] Custom rules
- [x] Debian packaging
- [x] GitHub Actions CI
- [x] Modern desktop UI
- [ ] AI-powered file classification
- [ ] Rule marketplace
- [ ] Cloud sync (optional)

---

# 🤝 Contributing

Issues, ideas and pull requests are welcome.

If you'd like to improve SmartSort, feel free to open an issue or submit a PR.

---

# 📜 License

MIT License

---

<div align="center">

### ⭐ If SmartSort saves you time, consider starring the repository.

Made with ❤️ using Python & PyQt6

</div>
