#!/bin/bash
set -e

# Determine project root directory (absolute path)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Building Flatpak package for SmartSort..."

# Read version from src/version.py
VERSION=$(grep -oP 'VERSION\s*=\s*"\K[^"]+' "$PROJECT_ROOT/src/version.py")
if [ -z "$VERSION" ]; then
    echo "Error: Could not read version from src/version.py"
    exit 1
fi
echo "Version detected: $VERSION"

BUILD_DIR="$SCRIPT_DIR/app_dir"
REPO_DIR="$SCRIPT_DIR/repo"

# Clean previous build artifacts
rm -rf "$BUILD_DIR" "$REPO_DIR"

echo "Initializing Flatpak build..."
flatpak build-init "$BUILD_DIR" com.smartsort.SmartSort org.kde.Platform org.kde.Sdk 6.9

echo "Bootstrapping pip inside sandbox..."
flatpak build "$BUILD_DIR" python3 -m ensurepip --root=/app

echo "Installing Python dependencies inside sandbox..."
flatpak build "$BUILD_DIR" env PYTHONPATH=/app/usr/lib/python3.12/site-packages python3 -m pip install --no-index --find-links="$SCRIPT_DIR/python-wheels" --prefix=/app -r "$SCRIPT_DIR/requirements_flatpak.txt"

echo "Cleaning up build-time pip tools from sandbox..."
flatpak build "$BUILD_DIR" rm -rf /app/usr

echo "Copying source files..."
flatpak build "$BUILD_DIR" mkdir -p /app/bin
flatpak build "$BUILD_DIR" cp -r "$PROJECT_ROOT/src" "$PROJECT_ROOT/main.py" "$PROJECT_ROOT/assets" /app/bin/

# Copy default config template
flatpak build "$BUILD_DIR" mkdir -p /app/bin/config
flatpak build "$BUILD_DIR" cp "$PROJECT_ROOT/config/config.default.json" /app/bin/config/config.default.json

echo "Installing launcher script..."
flatpak build "$BUILD_DIR" install -D -m 755 "$SCRIPT_DIR/smartsort.sh" /app/bin/smartsort

echo "Installing desktop entry and icons..."
flatpak build "$BUILD_DIR" install -D -m 644 "$PROJECT_ROOT/assets/icons/logo_square.png" /app/share/icons/hicolor/scalable/apps/com.smartsort.SmartSort.png
flatpak build "$BUILD_DIR" install -D -m 644 "$SCRIPT_DIR/com.smartsort.SmartSort.desktop" /app/share/applications/com.smartsort.SmartSort.desktop

echo "Setting permissions and finish args..."
flatpak build-finish "$BUILD_DIR" \
  --socket=fallback-x11 \
  --socket=wayland \
  --share=ipc \
  --device=dri \
  --filesystem=xdg-download \
  --talk-name=org.freedesktop.Notifications \
  --talk-name=org.kde.StatusNotifierWatcher \
  --command=smartsort

echo "Exporting Flatpak build to repository..."
flatpak build-export "$REPO_DIR" "$BUILD_DIR"

echo "Generating Flatpak bundle file..."
mkdir -p "$PROJECT_ROOT/build/flatpak"
flatpak build-bundle "$REPO_DIR" "$PROJECT_ROOT/build/flatpak/smartsort_${VERSION}.flatpak" com.smartsort.SmartSort

# Clean up temporary directories
echo "Cleaning up temporary files..."
rm -rf "$BUILD_DIR" "$REPO_DIR"

echo "Flatpak build complete. Generated smartsort_${VERSION}.flatpak in build/flatpak/."
