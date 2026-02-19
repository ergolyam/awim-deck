#!/bin/sh
set -eu

SCRIPT_DIR=$(dirname -- "$0")
cd "$SCRIPT_DIR"
SCRIPT_DIR=$(pwd)
cd ..
ROOT_DIR=$(pwd)

PLUGIN_DIR_NAME="awim-deck"
VERSION=$(node -p "require('./package.json').version")
OUT_ROOT="$ROOT_DIR/out"
STAGE_DIR="$OUT_ROOT/$PLUGIN_DIR_NAME"
ZIP_NAME="$PLUGIN_DIR_NAME-v$VERSION.zip"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"
mkdir -p "$STAGE_DIR/bin"
mkdir -p "$STAGE_DIR/dist"

cp -r "$ROOT_DIR/dist/." "$STAGE_DIR/dist/"
cp "$ROOT_DIR/backend/out/awim" "$STAGE_DIR/bin/awim"
chmod +x "$STAGE_DIR/bin/awim"
cp "$ROOT_DIR/main.py" "$STAGE_DIR/main.py"
cp "$ROOT_DIR/plugin.json" "$STAGE_DIR/plugin.json"
cp "$ROOT_DIR/package.json" "$STAGE_DIR/package.json"
cp "$ROOT_DIR/license" "$STAGE_DIR/license"
cp "$ROOT_DIR/readme.md" "$STAGE_DIR/readme.md"

cd "$OUT_ROOT"
rm -f "$ZIP_NAME"
python3 -m zipfile -c "$ZIP_NAME" "$PLUGIN_DIR_NAME"
