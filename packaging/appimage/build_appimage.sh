#!/bin/bash
set -e

# Setup AppDir
APPDIR="SmartSort.AppDir"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/smartsort"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

# Copy application files
cp -r ../../src ../../config ../../main.py ../../assets "$APPDIR/usr/share/smartsort/"

# Ensure AppRun is executable
chmod +x AppRun
cp AppRun "$APPDIR/"

# Setup desktop and icon
cat << 'EOF' > "$APPDIR/usr/share/applications/smartsort.desktop"
[Desktop Entry]
Name=SmartSort
Comment=Intelligent Download Organizer
Exec=AppRun
Icon=smartsort
Terminal=false
Type=Application
Categories=Utility;
EOF

cp ../../assets/icons/logo.png "$APPDIR/smartsort.png"
cp ../../assets/icons/logo.png "$APPDIR/usr/share/icons/hicolor/scalable/apps/smartsort.png"

echo "AppDir setup complete. Run appimagetool on SmartSort.AppDir to generate AppImage."
