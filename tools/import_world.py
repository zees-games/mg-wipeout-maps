#!/usr/bin/env python3
"""Imports a community map as a course: its mesh through dot-map's converter, its moving parts as pieces.

    python3 -I tools/import_world.py tools/imports/<course id>.json

The import file names the source .bsp, its credit, and the parts only a person can write (start, finish,
checkpoints, route, anything the map has no mover for). The mesh goes to worlds/<id>.{json,bin}; the course
to courses/<id>.json. The converter is dot-map's (the sibling checkout, or $DOTBSP_PATH); nothing here
reads a BSP itself. Rules, per mover and volume the converter lists:

    tracktrain between two corners   -> pusher along the track (a punch and back, not a glide)
    func_rotating about the vertical -> spinner at its middle (speed capped at MAX_SPIN)
    trigger_hurt of 100 or more      -> kill box, unless the import file lists its model under "attached"
    func_brush the map toggles away  -> listed under "hidden" in the import file: left out of the mesh (a door that
                                        shuts the spawn room until the round starts would box the runners in)
    ladder volume                    -> ladder piece the player climbs (a spec's "ladder_as": "bouncer" makes a bounce
                                        pad at its foot instead, for a course routed over one)
    spec "tune": {"<mover name>": {"period": 9, "duty": 0.35}} -> fields overwritten on that mover's piece (a stand-in
                                        trace asks for a slower punch than the map's own speed gives)
    spec "stage": [[min x,y,z],[max x,y,z]] -> generated pieces outside that box are dropped
    everything else (buttons, other rotators, pushes, secret teleports, timed hurts) -> listed, not built
"""

import itertools
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
BSP = os.environ.get("DOTBSP_PATH") or os.path.join(REPO, "..", "dot-map", "tools", "bsp")
MAX_SPIN = 120.0


def r(x):
    return round(float(x), 2)


def solve(a, b):
    """Solves the 3x3 system a.x = b by Cramer's rule; None when singular."""
    def det(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    d = det(a)
    if abs(d) < 1e-9:
        return None
    out = []
    for c in range(3):
        m = [row[:] for row in a]
        for i in range(3):
            m[i][c] = b[i]
        out.append(det(m) / d)
    return out


def brush_bounds(planes):
    pts = []
    for i, j, k in itertools.combinations(range(len(planes)), 3):
        x = solve([planes[n][:3] for n in (i, j, k)], [planes[n][3] for n in (i, j, k)])
        if x and all(sum(p[c] * x[c] for c in range(3)) <= p[3] + 1e-3 for p in planes):
            pts.append(x)
    if not pts:
        return None
    return [min(p[c] for p in pts) for c in range(3)], [max(p[c] for p in pts) for c in range(3)]


def volume_bounds(vol):
    boxes = [b for b in (brush_bounds(br) for br in vol.get("brushes", [])) if b]
    if not boxes:
        return None
    return ([min(b[0][c] for b in boxes) for c in range(3)], [max(b[1][c] for b in boxes) for c in range(3)])


def yaw_toward(dx, dz):
    """The yaw whose -Z faces (dx, dz): a piece's forward is -Z turned about Y."""
    return math.degrees(math.atan2(-dx, -dz))


def pieces_from(manifest, spec):
    pieces, notes = [], []
    box = spec.get("stage")
    tune = spec.get("tune", {})
    attached = set(spec.get("attached", []))
    for m in manifest["movers"]:
        cls = m["classname"]
        if m.get("model") is None:
            # A prop-model mover (prop_door_rotating) has no brush model to build a piece from.
            notes.append("WARNING %s %s: no brush model, skipped" % (cls, m.get("targetname") or m.get("entity")))
            continue
        name = m.get("targetname") or "model %d" % m["model"]
        if m["kind"] == "path" and len(m.get("path", [])) >= 2 and "path" in m and m.get("speed", 0) > 0:
            corners = [p["at"] for p in m["path"] if "at" in p][:2]
            lo, hi = m["mins"], m["maxs"]
            centre = [(lo[c] + hi[c]) / 2 for c in range(3)]
            size = [hi[c] - lo[c] for c in range(3)]
            a, b = corners
            dx, dz = b[0] - a[0], b[2] - a[2]
            dist = math.hypot(dx, dz)
            if dist < 0.5:
                notes.append("%s: path under 0.5 m, not built" % name)
                continue
            off = [centre[c] - m["origin"][c] for c in range(3)]
            yaw = yaw_toward(dx, dz)
            along = abs(math.sin(math.radians(yaw))) > 0.5
            # size is (across, up, along the push): the pusher's local Z is the way it travels.
            across, depth = (size[2], size[0]) if along else (size[0], size[2])
            # A bar resting at its track's start stands where the ledge it sweeps from ends: the spec's
            # "pusher_inset" moves the rest position that far along the track so a runner can take off.
            inset = min(float(spec.get("pusher_inset", 0.0)), dist * 0.5)
            ux, uz = dx / dist, dz / dist
            a = [a[0] + ux * inset, a[1], a[2] + uz * inset]
            dist -= inset
            pieces.append({"kind": "pusher", "at": [r(a[0] + off[0]), r(a[1] + off[1]), r(a[2] + off[2])],
                           "size": [r(max(across, 0.3)), r(max(size[1], 0.3)), r(max(depth, 0.25))],
                           "reach": r(dist), "period": r(2 * dist / m["speed"] + 1.0), "duty": 0.55,
                           "phase": 0.0, "yaw": r(yaw), "source": name})
        elif m["kind"] == "spin" and m.get("start_on") and abs(m["axis"][1]) > 0.9 and m["maxs"][0] - m["mins"][0] > 1.0:
            lo, hi = m["mins"], m["maxs"]
            pieces.append({"kind": "spinner", "at": [r(m["origin"][0]), r(lo[1]), r(m["origin"][2])],
                           "arm_length": r(max(hi[0] - lo[0], hi[2] - lo[2]) / 2), "arm_height": 0.6, "arms": 2,
                           "speed": r(min(m["degrees_per_second"], MAX_SPIN)), "hub_radius": 0.3, "yaw": 0.0, "source": name})
        elif m["kind"] != "button":
            notes.append("%s %s (%s): no equivalent, not built" % (cls, name, m["kind"]))
    for v in manifest["volumes"]:
        if v.get("model") is None:
            notes.append("WARNING %s volume %s: no brush model, skipped" % (v.get("kind"), v.get("targetname") or v.get("entity")))
            continue
        b = volume_bounds(v)
        if b is None:
            continue
        lo, hi = b
        centre = [(lo[c] + hi[c]) / 2 for c in range(3)]
        size = [max(hi[c] - lo[c], 0.1) for c in range(3)]
        if v["kind"] == "hurt":
            if v["model"] in attached or v.get("disabled") or float(v.get("damage", 0)) < 100:
                notes.append("hurt model %d (damage %s%s): not built" % (
                    v["model"], v.get("damage"), ", disabled" if v.get("disabled") else ""))
                continue
            pieces.append({"kind": "kill", "at": [r(c) for c in centre], "size": [r(s) for s in size], "yaw": 0.0})
        elif v["kind"] == "ladder":
            if spec.get("ladder_as") == "bouncer":
                pieces.append({"kind": "bouncer", "at": [r(centre[0]), r(lo[1] + 0.1), r(centre[2])],
                               "size": [r(max(size[0], 1.2)), 0.2, r(max(size[2], 1.2))], "power": 13.5, "yaw": 0.0})
            else:
                pieces.append({"kind": "ladder", "at": [r(c) for c in centre], "size": [r(max(x, 0.1)) for x in size]})
        elif v["kind"] in ("push", "gravity", "teleport"):
            notes.append("%s volume %s: no equivalent, not built" % (v["kind"], v.get("targetname") or v["model"]))
    for p in pieces:
        p.update(tune.get(p.get("source", ""), {}))
    if box:
        # Generated pieces outside the stage the course plays are scenery in the mesh only: a mover or kill
        # box in a part nobody reaches would still be simulated and sent in STAGE.
        lo, hi = box
        kept = [p for p in pieces if all(lo[c] <= p["at"][c] <= hi[c] for c in range(3))]
        notes.append("stage box dropped %d of %d generated pieces" % (len(pieces) - len(kept), len(pieces)))
        pieces = kept
    drop = set(spec.get("drop", []))
    if drop:
        pieces = [p for p in pieces if p["kind"] not in drop]
    return pieces, notes


def main():
    spec_path = sys.argv[1]
    spec = json.load(open(spec_path))
    cid = spec["id"]
    worlds = os.path.join(REPO, "worlds")
    os.makedirs(worlds, exist_ok=True)
    subprocess.run([sys.executable, "-I", os.path.join(BSP, "bsp.py"), "mesh", os.path.expanduser(spec["source"]),
                    "--out", os.path.join(worlds, cid), "--scale", "hull", "--author", spec["credit"]["author"],
                    "--page", spec["credit"]["page"]], check=True, stdout=subprocess.DEVNULL)
    manifest = json.load(open(os.path.join(worlds, cid + ".json")))
    generated, notes = pieces_from(manifest, spec)
    skip = sorted({m["model"] for m in manifest["movers"] if m.get("model") is not None} | {v["model"] for v in manifest["volumes"] if v["model"]}
                  | set(spec.get("hidden", [])))
    doc = {k: spec[k] for k in ("format", "kind", "id", "name", "author", "blurb", "theme", "water_height",
                                "course_seconds", "start", "finish", "checkpoints", "route") if k in spec}
    doc["pieces"] = [{"kind": "world", "mesh": cid, "skip": skip}] + generated + spec.get("pieces", [])
    for p in doc["pieces"]:
        p.pop("source", None)
    if "toys" in spec:
        doc["toys"] = spec["toys"]
    with open(os.path.join(REPO, "courses", cid + ".json"), "w") as out:
        out.write(json.dumps(doc, indent=1) + "\n")
    print("%s: %d generated pieces" % (cid, len(generated)))
    for n in notes:
        print("  - " + n)


if __name__ == "__main__":
    main()
