#!/usr/bin/env python3
"""Writes groups.json: one download group per imported course, holding its world (worlds/<course id>.*) and the shared
library art that world's licence names (pbr-library/<set>/<tier>/, model-library/<model dir>/), plus a catch-all
"library" group for the rest of both libraries, so no library file is ungrouped.

    tools/build_groups.py            # rewrite
    tools/build_groups.py --check    # exit 1 if stale, or a group has no course document

dot-cloud's publisher reads groups.json at the source root and writes each group into the manifest entries
(DotCloudPublisher, GROUPS_FILE), so a client fetches courses/ and cfg/ and the worlds/ groups of the courses
it plays (mg-wipeout's WoWorld.fetch). Shared files (worlds/credits.json, worlds/textures/) stay ungrouped. A file
named by several courses carries each of their groups. The library paths come from the tracked worlds/<id>.json, so
--check works without the staged libraries; dot-map draws a set or model it cannot find as a stand-in.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = {"credits", "CREDITS", "textures"}
LIBRARY = "library"


def course_ids(root=ROOT):
    """The ids of the courses that have a world: worlds/<id>.json beside a courses/<id>.json."""
    ids = set()
    for name in os.listdir(os.path.join(root, "worlds")):
        m = re.match(r"^([^.]+)\.", name)
        if m and m.group(1) not in SHARED:
            ids.add(m.group(1))
    return sorted(ids)


def _store(licence, key, default):
    """The library folder a licence's store points at, relative to the pack root ("../pbr-library" -> "pbr-library")."""
    return os.path.normpath(os.path.join("worlds", str(licence.get(key, default)))).replace(os.sep, "/")


def library_dirs(root, i):
    """The pack folders (each ending in "/") of the PBR sets and models that worlds/<i>.json's licence names."""
    with open(os.path.join(root, "worlds", i + ".json")) as f:
        licence = json.load(f).get("licence", {})
    dirs = set()
    pbr = _store(licence, "pbr_store", "../pbr-library")
    for t in licence.get("textures", []):
        if t.get("kind") == "pbr":
            dirs.add("%s/%s/%s/" % (pbr, os.path.basename(str(t["file"])), t.get("tier", "1k")))
    models = _store(licence, "model_store", "../model-library")
    for m in licence.get("model_stand_ins", []):
        if m.get("store_file"):
            dirs.add("%s/%s/" % (models, os.path.dirname(str(m["store_file"]))))
    return sorted(dirs)


def build(root=ROOT):
    """groups.json's content, or raises ValueError when a world has no course document."""
    ids = course_ids(root)
    for i in ids:
        if not os.path.isfile(os.path.join(root, "courses", i + ".json")):
            raise ValueError("worlds/%s.* has no courses/%s.json" % (i, i))
    groups = {i: ["worlds/%s.*" % i] + library_dirs(root, i) for i in ids}
    stores = sorted({d.split("/")[0] + "/" for i in ids for d in groups[i][1:]})
    if stores:
        groups[LIBRARY] = stores
    return groups


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
    print("groups.json: %d groups" % len(json.loads(want)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
