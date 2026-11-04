#!/bin/bash
# Publishes this maps pack (id mg-wipeout-maps); a server mounts it, a client only for worlds/ meshes (maps_delivery: client).
#   tools/publish.sh [--version V | --bump patch] [--site URL --token-file F --dry-run ...]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$HERE/../dot-cloud/tools/publish_pack.sh" publish --source "$HERE" --id mg-wipeout-maps --exclude-dir tools \
    --lock "$HERE/content.lock.json" "$@"
