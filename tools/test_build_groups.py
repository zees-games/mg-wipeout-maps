#!/usr/bin/env python3
"""Regression checks for build_groups: python3 -I tools/test_build_groups.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_groups as g


def touch(root, rel):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").close()


def world(root, i, textures=(), models=()):
    """worlds/<i>.json with a licence naming PBR sets (name, tier) and model store files."""
    licence = {"pbr_store": "../pbr-library", "model_store": "../model-library",
               "textures": [{"kind": "generated", "file": "textures/gen.png"}]
               + [{"kind": "pbr", "file": "pbr/" + n, "tier": t} for n, t in textures],
               "model_stand_ins": [{"store_file": f} for f in models]}
    os.makedirs(os.path.join(root, "worlds"), exist_ok=True)
    with open(os.path.join(root, "worlds", i + ".json"), "w") as f:
        json.dump({"licence": licence}, f)


def main():
    failed = 0
    with tempfile.TemporaryDirectory() as root:
        world(root, "wo_a", [("Wood01", "1k"), ("Rock02", "2k")], ["kenney/kit/a.glb", "kenney/kit/b.glb"])
        world(root, "wo_ab")
        for rel in ("worlds/wo_a.bin", "worlds/wo_a.doc.json",
                    "worlds/credits.json", "worlds/CREDITS.md", "worlds/textures/t.webp", "courses/wo_a.json", "courses/wo_ab.json"):
            touch(root, rel)
        groups = g.build(root)
        for ok, what in ((sorted(groups) == ["library", "wo_a", "wo_ab"], "one group per course and library, shared files left out"),
                         (groups["wo_ab"] == ["worlds/wo_ab.*"], "the prefix ends in a dot so wo_ab is not wo_a's"),
                         (groups["wo_a"] == ["worlds/wo_a.*", "model-library/kenney/kit/", "pbr-library/Rock02/2k/",
                                             "pbr-library/Wood01/1k/"], "a course takes the sets and model dirs its licence names, once each"),
                         (groups["library"] == ["model-library/", "pbr-library/"], "the library group catches the rest of both stores"),
                         (g.text(groups).endswith("}\n"), "text ends with a newline")):
            print(("ok   " if ok else "FAIL ") + what)
            failed += not ok
        world(root, "wo_orphan")
        try:
            g.build(root)
            ok = False
        except ValueError:
            ok = True
        print(("ok   " if ok else "FAIL ") + "a world without a course document is refused")
        failed += not ok
    print("%d failed" % failed)
    sys.exit(1 if failed else 0)


main()
