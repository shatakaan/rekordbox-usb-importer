#!/bin/bash
set -e
# Playlist Converter — reproducible build script
# Usage: bash build/build.sh
# Output: dist/PlaylistConverter.app, dist/PlaylistConverter-1.0.0.dmg

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
source .venv/bin/activate

echo "=== Step 1: PyInstaller ==="
pyinstaller build/app.spec

echo "=== Step 2: Verify ad-hoc signature ==="
codesign --verify --verbose dist/PlaylistConverter.app
echo "Signature OK"

echo "=== Step 3: dmgbuild ==="
dmgbuild \
  -s build/dmgbuild_settings.py \
  -D app=dist/PlaylistConverter.app \
  "Playlist Converter" \
  dist/PlaylistConverter-1.0.0.dmg

echo "=== Build complete ==="
echo "  App:  dist/PlaylistConverter.app"
echo "  DMG:  dist/PlaylistConverter-1.0.0.dmg"
du -sh dist/PlaylistConverter.app dist/PlaylistConverter-1.0.0.dmg
