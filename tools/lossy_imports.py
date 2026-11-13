#!/usr/bin/env python3
"""Make the staged library textures import lossy with mipmaps.

pbr-library/ and model-library/ are staged from the shared stores, whose
.import files use Godot's default (lossless, no mipmaps). Shipped that way
the maps pack was 1.4 GiB of textures and the web page ran out of memory
fetching it for solo. The family convention (dot-map docs/surfaces.md,
dot-cloud docs/sources.md) is lossy WebP (compress/mode=1) with mipmaps.

    tools/lossy_imports.py [root]          rewrite the .import files
    tools/lossy_imports.py --check [root]  exit 1 if any still need it

publish.sh runs this before publishing, so a fresh staging cannot ship
lossless textures again.
"""
import os
import sys

STORES = ("pbr-library", "model-library", "worlds")
SWAPS = (
    ("compress/mode=0\n", "compress/mode=1\n"),
    ("mipmaps/generate=false\n", "mipmaps/generate=true\n"),
)


def fixed(text):
    if 'importer="texture"' not in text:
        return text
    for old, new in SWAPS:
        text = text.replace(old, new)
    return text


def main(argv):
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    root = args[0] if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    todo = 0
    for store in STORES:
        for dirpath, _dirs, files in os.walk(os.path.join(root, store)):
            for name in files:
                if not name.endswith(".import"):
                    continue
                path = os.path.join(dirpath, name)
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                new = fixed(text)
                if new == text:
                    continue
                todo += 1
                if not check:
                    tmp = path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write(new)
                    os.replace(tmp, path)
    verb = "need lossy+mipmaps" if check else "made lossy+mipmaps"
    print(f"lossy_imports: {todo} texture import(s) {verb}")
    return 1 if (check and todo) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
