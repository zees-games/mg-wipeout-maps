#!/bin/bash
# Publishes this maps pack (id mg-wipeout-maps); a server mounts it, a client only for worlds/ meshes (maps_delivery: client).
#   tools/publish.sh [--version V | --bump patch] [--site URL --token-file F --dry-run ...]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# pbr-library/ and model-library/ are staged (gitignored) and must ship, hence --include-ignored; their store
# imports are lossless without mipmaps, which made the pack 1.4 GiB and crashed the web page, so make them lossy first.
python3 -I "$HERE/tools/lossy_imports.py" "$HERE"
exec "$HERE/../dot-cloud/tools/publish_pack.sh" publish --source "$HERE" --id mg-wipeout-maps --exclude-dir tools --include-ignored \
    --lock "$HERE/content.lock.json" "$@"
