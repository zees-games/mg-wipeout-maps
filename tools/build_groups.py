#!/usr/bin/env python3
"""Writes groups.json: one download group per imported course, holding everything named worlds/<course id>.* (the glob worlds/<id>.*)

    tools/build_groups.py            # rewrite
    tools/build_groups.py --check    # exit 1 if stale, or a group has no course document

dot-cloud's publisher reads groups.json at the source root and writes each group into the manifest entries
(DotCloudPublisher, GROUPS_FILE), so a client fetches courses/ and cfg/ and the worlds/ groups of the courses
it plays (mg-wipeout's WoWorld.fetch). Shared files (worlds/credits.json, worlds/textures/) stay ungrouped.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = {"credits", "textures"}


def course_ids(root=ROOT):
    """The ids of the courses that have a world: worlds/<id>.json beside a courses/<id>.json."""
    ids = set()
    for name in os.listdir(os.path.join(root, "worlds")):
        m = re.match(r"^([^.]+)\.", name)
        if m and m.group(1) not in SHARED:
            ids.add(m.group(1))
    return sorted(ids)


def build(root=ROOT):
    """groups.json's content, or raises ValueError when a world has no course document."""
    ids = course_ids(root)
    for i in ids:
        if not os.path.isfile(os.path.join(root, "courses", i + ".json")):
            raise ValueError("worlds/%s.* has no courses/%s.json" % (i, i))
    return {i: ["worlds/%s.*" % i] for i in ids}


def text(groups):
    return json.dumps(groups, indent=4) + "\n"


def main(argv):
    path = os.path.join(ROOT, "groups.json")
    try:
        want = text(build())
    except ValueError as e:
        print("build_groups: %s" % e)
        return 1
    if "--check" in argv:
        have = open(path).read() if os.path.isfile(path) else ""
        if have != want:
            print("build_groups: groups.json is stale; run tools/build_groups.py")
            return 1
        return 0
    with open(path, "w") as f:
        f.write(want)
    print("groups.json: %d groups" % len(build()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
