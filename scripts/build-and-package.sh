#!/bin/sh
set -eu

SCRIPT_DIR=$(dirname -- "$0")
cd "$SCRIPT_DIR"
SCRIPT_DIR=$(pwd)
cd ..
ROOT_DIR=$(pwd)

cd "$ROOT_DIR"
pnpm run build:frontend

sh ./scripts/package-plugin.sh
