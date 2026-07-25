#!/bin/bash
set -e

# Determine project root directory (absolute path)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Preparing RPM build files for SmartSort..."

# Read version from src/version.py
VERSION=$(grep -oP 'VERSION\s*=\s*"\K[^"]+' "$PROJECT_ROOT/src/version.py")
if [ -z "$VERSION" ]; then
    echo "Error: Could not read version from src/version.py"
    exit 1
fi
echo "Version detected: $VERSION"

# Ensure target build directory exists
mkdir -p "$PROJECT_ROOT/build/rpm"

# Generate spec file with dynamic version replacement
SPEC_OUT="$PROJECT_ROOT/build/rpm/smartsort-${VERSION}.spec"
cat "$SCRIPT_DIR/smartsort.spec" | sed "s/^Version:.*/Version: ${VERSION}/" > "$SPEC_OUT"
echo "Generated versioned spec file at $SPEC_OUT"

# Create source tarball
TEMP_DIR="$(mktemp -d)"
TAR_DIR="$TEMP_DIR/smartsort-${VERSION}"
mkdir -p "$TAR_DIR"

# Copy source tree files
cp "$PROJECT_ROOT/main.py" "$TAR_DIR/"
cp -r "$PROJECT_ROOT/src" "$TAR_DIR/"
cp -r "$PROJECT_ROOT/assets" "$TAR_DIR/"
mkdir -p "$TAR_DIR/config"
cp "$PROJECT_ROOT/config/config.default.json" "$TAR_DIR/config/config.default.json"

# Package tarball
tar -czf "$PROJECT_ROOT/build/rpm/smartsort-${VERSION}.tar.gz" -C "$TEMP_DIR" "smartsort-${VERSION}"
rm -rf "$TEMP_DIR"
echo "Created source archive at build/rpm/smartsort-${VERSION}.tar.gz"

# Try to compile RPM if rpmbuild is available
if command -v rpmbuild >/dev/null 2>&1; then
    echo "rpmbuild detected. Attempting RPM package compilation..."
    RPM_TOP_DIR="$PROJECT_ROOT/build/rpm/rpmbuild"
    mkdir -p "$RPM_TOP_DIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    
    # Copy source tarball and spec to rpmbuild tree
    cp "$PROJECT_ROOT/build/rpm/smartsort-${VERSION}.tar.gz" "$RPM_TOP_DIR/SOURCES/"
    cp "$SPEC_OUT" "$RPM_TOP_DIR/SPECS/"
    
    # Build package
    rpmbuild --define "_topdir $RPM_TOP_DIR" -ba "$RPM_TOP_DIR/SPECS/smartsort-${VERSION}.spec"
    
    # Copy built RPMs to build/rpm/
    find "$RPM_TOP_DIR/RPMS" -name "*.rpm" -exec cp {} "$PROJECT_ROOT/build/rpm/" \;
    find "$RPM_TOP_DIR/SRPMS" -name "*.rpm" -exec cp {} "$PROJECT_ROOT/build/rpm/" \;
    
    # Cleanup rpmbuild tree
    rm -rf "$RPM_TOP_DIR"
    echo "RPM package compiled successfully!"
else
    echo "Warning: rpmbuild is not installed. Skipping binary RPM generation."
    echo "Sources and spec file are ready in build/rpm/. You can run 'rpmbuild -ba smartsort-${VERSION}.spec' on an RPM-based system."
fi
