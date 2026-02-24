#!/bin/sh
set -eu

SCRIPT_DIR=$(dirname -- "$0")
cd "$SCRIPT_DIR"
SCRIPT_DIR=$(pwd)
cd ..
ROOT_DIR=$(pwd)

cd "$ROOT_DIR"
pnpm run build:frontend

if command -v docker >/dev/null 2>&1; then
  docker build -t awim-deck-backend "$ROOT_DIR/backend"
  docker run --rm -v "$ROOT_DIR/backend:/backend" awim-deck-backend
elif command -v podman >/dev/null 2>&1; then
  podman build -t awim-deck-backend "$ROOT_DIR/backend"
  podman run --rm -v "$ROOT_DIR/backend:/backend" awim-deck-backend
else
  make -C backend
fi

python3 -m py_compile "$ROOT_DIR/main.py"

sh ./scripts/package-plugin.sh
