#!/usr/bin/env python3
"""Regression checks for import_world.pieces_from: python3 -I tools/test_import_world.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import import_world as w


def main():
    manifest = {
        "movers": [
            {"classname": "prop_door_rotating", "kind": "rotate", "model": None, "entity": 536, "targetname": "dd"},
            {"classname": "func_rotating", "kind": "spin", "model": 3, "start_on": True, "axis": [0, 1, 0],
             "mins": [-2, 0, -2], "maxs": [2, 1, 2], "origin": [0, 0, 0], "degrees_per_second": 30.0},
        ],
        "volumes": [{"kind": "hurt", "model": None, "entity": 9, "brushes": []}],
    }
    pieces, notes = w.pieces_from(manifest, {})
    failed = 0
    for ok, what in ((len(pieces) == 1 and pieces[0]["kind"] == "spinner", "other movers kept"),
                     (sum("WARNING" in n for n in notes) == 2, "each model-less entity warned")):
        print(("ok   " if ok else "FAIL ") + what)
        failed += not ok
    print("%d failed" % failed)
    sys.exit(1 if failed else 0)


main()
