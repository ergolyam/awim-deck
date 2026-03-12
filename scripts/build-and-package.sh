#!/bin/sh
set -eu

SCRIPT_DIR=$(dirname -- "$0")
cd "$SCRIPT_DIR"
SCRIPT_DIR=$(pwd)
cd ..
ROOT_DIR=$(pwd)

cd "$ROOT_DIR"
pnpm run build:frontend

if [ "$ROOT_DIR" = "/plugin" ] && [ -d /out ]; then
    printf '%s\n' "Skipping local zip packaging inside Decky builder."
    exit 0
fi

sh ./scripts/package-plugin.sh
