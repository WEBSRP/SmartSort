#!/bin/bash
set -e

# Determine project root directory (absolute path)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Building Debian package for SmartSort..."

# Read version from src/version.py
VERSION=$(grep -oP 'VERSION\s*=\s*"\K[^"]+' "$PROJECT_ROOT/src/version.py")
if [ -z "$VERSION" ]; then
    echo "Error: Could not read version from src/version.py"
    exit 1
fi
echo "Version detected: $VERSION"

BUILD_DIR="$SCRIPT_DIR/smartsort_${VERSION}_all"
echo "Creating temporary build directory at: $BUILD_DIR"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# 1. Create directory structure
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/systemd/user"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$BUILD_DIR/usr/share/smartsort"
mkdir -p "$BUILD_DIR/usr/share/smartsort/config"

# 2. Generate control file with dynamic version replacement
cat "$SCRIPT_DIR/DEBIAN/control" | sed "s/^Version:.*/Version: ${VERSION}/" > "$BUILD_DIR/DEBIAN/control"

# 3. Copy other DEBIAN maintainer scripts (postinst, postrm, prerm)
cp "$SCRIPT_DIR/DEBIAN/postinst" "$BUILD_DIR/DEBIAN/"
cp "$SCRIPT_DIR/DEBIAN/postrm" "$BUILD_DIR/DEBIAN/"
cp "$SCRIPT_DIR/DEBIAN/prerm" "$BUILD_DIR/DEBIAN/"

# Set maintainer scripts permissions (required by dpkg)
chmod 755 "$BUILD_DIR/DEBIAN/postinst"
chmod 755 "$BUILD_DIR/DEBIAN/postrm"
chmod 755 "$BUILD_DIR/DEBIAN/prerm"

# 4. Copy source code files & assets
cp "$PROJECT_ROOT/main.py" "$BUILD_DIR/usr/share/smartsort/"
cp -r "$PROJECT_ROOT/src" "$BUILD_DIR/usr/share/smartsort/"
cp -r "$PROJECT_ROOT/assets" "$BUILD_DIR/usr/share/smartsort/"
cp "$PROJECT_ROOT/config/config.default.json" "$BUILD_DIR/usr/share/smartsort/config/config.default.json"

# 5. Copy wrapper script
cat << 'EOF' > "$BUILD_DIR/usr/bin/smartsort"
#!/bin/bash
export PYTHONPATH=/usr/share/smartsort
exec python3 /usr/share/smartsort/main.py "$@"
EOF
chmod 755 "$BUILD_DIR/usr/bin/smartsort"

# 6. Copy desktop launcher & systemd service
cp "$SCRIPT_DIR/smartsort.desktop" "$BUILD_DIR/usr/share/applications/"
cp "$SCRIPT_DIR/smartsort.service" "$BUILD_DIR/usr/lib/systemd/user/"

# 7. Copy icons
cp "$PROJECT_ROOT/assets/icons/logo.png" "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps/smartsort.png"

# 8. Copy hicolor tray subdirectories/sizes automatically
echo "Packing tray size icons..."
for size in 16x16 22x22 24x24 32x32; do
    mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/$size/apps"
    for color in blue green grey orange red yellow; do
        SRC_ICON="$PROJECT_ROOT/assets/icons/tray_${color}_${size}.png"
        if [ -f "$SRC_ICON" ]; then
            cp "$SRC_ICON" "$BUILD_DIR/usr/share/icons/hicolor/$size/apps/tray_${color}.png"
        fi
    done
done

# Copy scalable tray icons to scalable directory
for color in blue green grey orange red yellow; do
    SRC_ICON="$PROJECT_ROOT/assets/icons/tray_${color}.png"
    if [ -f "$SRC_ICON" ]; then
        cp "$SRC_ICON" "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps/tray_${color}.png"
    fi
done

# 9. Build Debian package using dpkg-deb
echo "Compiling Debian package..."
dpkg-deb --build --root-owner-group "$BUILD_DIR" "$PROJECT_ROOT/build/deb/smartsort_${VERSION}_all.deb"

# 10. Clean up temporary build tree
echo "Cleaning up temporary files..."
rm -rf "$BUILD_DIR"

echo "Build successful! Created package at $PROJECT_ROOT/build/deb/smartsort_${VERSION}_all.deb"
