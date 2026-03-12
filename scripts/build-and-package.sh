#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(dirname -- "$SCRIPT_DIR")

cd "$ROOT_DIR"
pnpm run build:frontend

if [ "$ROOT_DIR" = "/plugin" ] && [ -d /out ]; then
    printf '%s\n' "Skipping local zip packaging inside Decky builder."
    exit 0
fi

sh ./scripts/package-plugin.sh
