#!/bin/bash
set -e

# Determine project root directory and script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Target directory for python wheels
WHEELS_DIR="$SCRIPT_DIR/python-wheels"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements_flatpak.txt"

# Clean old wheels
rm -rf "$WHEELS_DIR"
mkdir -p "$WHEELS_DIR"

# Dynamically detect Python version inside Flatpak org.kde.Platform//6.9 runtime
echo "Detecting Python version inside Flatpak KDE 6.9 Platform..."
PYTHON_VERSION=$(flatpak run --runtime=org.kde.Platform//6.9 --command=python3 org.kde.Platform//6.9 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "3.12")

echo "Detected Flatpak Python version: $PYTHON_VERSION"

# Derive ABI tag (e.g. cp312)
ABI_TAG="cp${PYTHON_VERSION//./}"
echo "Target ABI tag: $ABI_TAG"

# Download all packages and transitive dependencies as binary wheels
echo "Downloading dependencies from PyPI..."
pip3 download \
  --dest "$WHEELS_DIR" \
  --python-version "$PYTHON_VERSION" \
  --implementation cp \
  --abi "$ABI_TAG" \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 \
  --platform manylinux_2_28_x86_64 \
  --platform any \
  -r "$REQUIREMENTS_FILE"

echo "Successfully generated offline wheels repository under $WHEELS_DIR/"
