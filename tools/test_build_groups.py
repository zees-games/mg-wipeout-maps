#!/usr/bin/env python3
"""Regression checks for build_groups: python3 -I tools/test_build_groups.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_groups as g


def touch(root, rel):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").close()


def main():
    failed = 0
    with tempfile.TemporaryDirectory() as root:
        for rel in ("worlds/wo_a.json", "worlds/wo_a.bin", "worlds/wo_a.doc.json", "worlds/wo_ab.json",
                    "worlds/credits.json", "worlds/textures/t.webp", "courses/wo_a.json", "courses/wo_ab.json"):
            touch(root, rel)
        groups = g.build(root)
        for ok, what in ((sorted(groups) == ["wo_a", "wo_ab"], "one group per course, shared files left out"),
                         (groups["wo_a"] == ["worlds/wo_a."], "the prefix ends in a dot so wo_ab is not wo_a's"),
                         (g.text(groups).endswith("}\n"), "text ends with a newline")):
            print(("ok   " if ok else "FAIL ") + what)
            failed += not ok
        touch(root, "worlds/wo_orphan.json")
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
