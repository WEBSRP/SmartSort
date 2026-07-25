#!/bin/bash
set -e

# Determine project root directory (absolute path)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Building AppImage for SmartSort..."

# Read version from src/version.py
VERSION=$(grep -oP 'VERSION\s*=\s*"\K[^"]+' "$PROJECT_ROOT/src/version.py")
if [ -z "$VERSION" ]; then
    echo "Error: Could not read version from src/version.py"
    exit 1
fi
echo "Version detected: $VERSION"

APPDIR="$SCRIPT_DIR/SmartSort.AppDir"
echo "Creating temporary AppDir at: $APPDIR"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/smartsort"
mkdir -p "$APPDIR/usr/share/smartsort/config"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

# 1. Copy source code files & assets
cp "$PROJECT_ROOT/main.py" "$APPDIR/usr/share/smartsort/"
cp -r "$PROJECT_ROOT/src" "$APPDIR/usr/share/smartsort/"
cp -r "$PROJECT_ROOT/assets" "$APPDIR/usr/share/smartsort/"
cp "$PROJECT_ROOT/config/config.default.json" "$APPDIR/usr/share/smartsort/config/config.default.json"

# 2. Copy AppRun wrapper to root and make it executable
cp "$SCRIPT_DIR/AppRun" "$APPDIR/"
chmod +x "$APPDIR/AppRun"

# 3. Create desktop launcher at root and in usr/share
cat << 'EOF' > "$APPDIR/smartsort.desktop"
[Desktop Entry]
Name=SmartSort
Comment=Intelligent Download Organizer
Exec=AppRun
Icon=smartsort
Terminal=false
Type=Application
Categories=Utility;
EOF
cp "$APPDIR/smartsort.desktop" "$APPDIR/usr/share/applications/"

# 4. Copy icons to root and usr/share
cp "$PROJECT_ROOT/assets/icons/logo.png" "$APPDIR/smartsort.png"
cp "$PROJECT_ROOT/assets/icons/logo.png" "$APPDIR/usr/share/icons/hicolor/scalable/apps/smartsort.png"

# 5. Build AppImage using appimagetool
echo "Compiling AppImage..."
chmod +x "$SCRIPT_DIR/appimagetool"
ARCH=x86_64 "$SCRIPT_DIR/appimagetool" "$APPDIR" "$PROJECT_ROOT/build/appimage/SmartSort-${VERSION}-x86_64.AppImage"

# 6. Clean up temporary AppDir
echo "Cleaning up temporary files..."
rm -rf "$APPDIR"

echo "Build successful! Created AppImage at $PROJECT_ROOT/build/appimage/SmartSort-${VERSION}-x86_64.AppImage"
