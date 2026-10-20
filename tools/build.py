#!/usr/bin/env python3
"""Writes every course and arena in this repository as the JSON document mg-wipeout reads.

    tools/build.py            # rewrite courses/*.json
    tools/build.py --check    # exit 1 if any file on disk differs from what this would write

WHY A BUILDER AND NOT HAND-WRITTEN JSON: a course is a few hundred numbers that depend on
each other. Moving one gap moves every piece after it, every checkpoint and every route point
a stand-in follows; written by hand that is forty edits and one of them missed. Here a course
is a sequence of SECTIONS on a cursor that runs down -Z from the start pad, and each section
places its pieces, its route points and its checkpoint together.

The JSON is still the truth the game reads, and is committed: a server installs documents, not
this script. `--check` is what CI runs, so a hand edit to a .json that this file does not know
about is caught rather than silently overwritten by the next build.

Every length is metres, every angle degrees, every time seconds. The movement these are sized
against is mg-wipeout's defaults: a 7 m/s run and a 1.25 m jump at 20 m/s^2, which clears about
4.9 m of flat gap at a run and rises onto about 1.1 m. A gap here is never over 3.4 m and a
step up never over 0.8 m, so every jump is made with room; what is hard is the timing.
"""

import json
import math
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "courses")
AUTHOR = "mg-wipeout"


def r(value):
    """Two decimals: the documents are read by people as well as by the game."""
    return round(float(value), 2)


def v(*values):
    return [r(x) for x in values]


# --- Trapdoor tiles: whether a column can be crossed ----------------------------
#
# [b]Every column of a grid crossable, with room.[/b] A tile's schedule is a hash of the grid's
# seed and its index, so a seed can lay a column where one row comes back up just as the row
# before it drops: Trapdoor Run's last grid (seed 53) had two columns nobody who kept to their
# column could cross (a 0.1 s window), and a field of stand-ins funnelled into the third. This
# is mg-wipeout's WoCourse.tile_cycle and tile_crossing_clear (a runner lined up on the column
# at the stand point, setting off from a stand) and the same numbers, so the builder can
# refuse a grid the game would have to work round. Keep the two in step.

TILE_RUN = 7.0                  # WoConfig.run_speed
TILE_WALK = 7.0 * 0.45          # run_speed * walk_speed_scale: the jump onto the first row
TILE_START = 0.1                # WoGame.TILE_START_SECONDS
TILE_SLOW = 0.9                 # WoCourse.TILE_SLOW
TILE_MARGIN = 0.08              # WoCourse.TILE_MARGIN_SECONDS
TILE_PLAYER_RADIUS = 0.35       # WoCourse.PLAYER_RADIUS
TILE_PLAN_RATE = 16             # WoCourse.TILE_PLAN_RATE
TILE_PLAN_SLOTS = 128           # WoCourse.TILE_PLAN_SLOTS

TILE_TICK_RATE = 64             # WoGame.tick_rate

# Seconds on end, once a period, that every column must be clear to set off for. Before this
# check (2026-10-13) Trapdoor Run's last grid had two columns that never were and one for
# 0.39 s, its turned grid one that never was, First Splash's grid one and Grand Tour's one for
# 0.09 s; a field crossed in the others. The seeds chosen then give every column 0.72 to
# 1.28 s.
TILE_FAIR_WINDOW = 0.5


def _mix(value):
    """WoCourse._mix: a small integer hash, the same on every platform."""
    x = (value ^ 0x5bd1e995) & 0x7fffffff
    x = ((x >> 15) ^ x) * 0x2c1b3c6d & 0x7fffffff
    x = ((x >> 12) ^ x) * 0x297a2d39 & 0x7fffffff
    return ((x >> 15) ^ x) & 0x7fffffff


def tile_cycle(spec, index, t):
    """WoCourse.tile_cycle: where a tile is in its cycle, 0..1; it is down below `down`."""
    offset = (_mix(int(spec["seed"]) * 7919 + index * 104729) % 1000) / 1000.0
    return (t / spec["period"] + offset) % 1.0


def _tile_up_over(spec, index, start, until):
    cycle = tile_cycle(spec, index, start)
    if cycle < spec["down"]:
        return False
    return (1.0 - cycle) * spec["period"] > until - start


def _tile_stand(spec, index, standing, arrive, now, dt):
    start = max(int(math.ceil(arrive / dt)), 0)
    if start >= len(standing):
        return
    cycle = tile_cycle(spec, index, now + start * dt)
    if cycle < spec["down"]:
        return
    until = min(start + int((1.0 - cycle) * spec["period"] / dt), len(standing))
    for k in range(start, until):
        standing[k] = max(standing[k], 1)
    if until > start:
        standing[start] = 2


def tile_column_clear(spec, col, back, now):
    """Whether a runner standing `back` metres before the grid's middle, lined up on column
    `col`, who sets off at `now` seconds, gets over every row (WoCourse.tile_crossing_clear
    asked from a deck, from a stand, with all of its margin). Rows are crossed toward the
    grid's local -Z, which is the way the builder lays them."""
    rows, cols, tile = spec["rows"], spec["cols"], spec["tile"]
    pitch = tile + spec["gap"]
    order = [(rows - 1 - k) * cols + col for k in range(rows)]
    middles = [(k - (rows - 1) * 0.5) * pitch for k in range(rows)]
    along = -back
    half = tile * 0.5
    dt = 1.0 / TILE_PLAN_RATE
    near = middles[0] - half
    walked = max(near - along, 0.0)
    fast_on = now + max(near - TILE_PLAYER_RADIUS - along, 0.0) / TILE_WALK
    slow_mid = now + TILE_START + walked / (TILE_WALK * TILE_SLOW) \
        + max(middles[0] - max(near, along), 0.0) / (TILE_RUN * TILE_SLOW)
    if not _tile_up_over(spec, order[0], fast_on - TILE_MARGIN, slow_mid + TILE_MARGIN):
        return False
    standing = [0] * TILE_PLAN_SLOTS
    _tile_stand(spec, order[0], standing, slow_mid - now, now, dt)
    to_next_fast = max(pitch - half - TILE_PLAYER_RADIUS - 0.6, 0.0) / TILE_RUN
    for i in range(rows):
        last = i == rows - 1
        following = [0] * TILE_PLAN_SLOTS
        found = False
        for k in range(TILE_PLAN_SLOTS):
            if standing[k] == 0:
                continue
            t = now + k * dt
            delay = 0.0 if standing[k] == 2 else TILE_START
            off_slow = delay + (half + TILE_PLAYER_RADIUS) / (TILE_RUN * TILE_SLOW)
            to_mid_slow = delay + pitch / (TILE_RUN * TILE_SLOW)
            if not _tile_up_over(spec, order[i], t, t + off_slow + TILE_MARGIN):
                continue
            if last:
                return True
            if not _tile_up_over(spec, order[i + 1], t + to_next_fast - TILE_MARGIN, t + to_mid_slow + TILE_MARGIN):
                continue
            found = True
            _tile_stand(spec, order[i + 1], following, k * dt + to_mid_slow, now, dt)
        if not found:
            return False
        standing = following
    return False


def tile_column_window(spec, col, back):
    """The longest run of ticks, in seconds, in which a runner standing `back` metres before the
    grid's middle on column `col` may set off and get over: asked every tick (mg-wipeout's 64
    a second), as a waiting stand-in asks it. A column whose moments come one or two ticks at a
    time is not one a runner can take: the stand-in that saw one go clear started walking and
    the next tick it was not, and Trapdoor Run's first grid (seed 304, clear at 37% of the
    sixteenths of a second WoCourse.tile_column_crossable asks at) had a column nobody crossed."""
    ticks = int(round(spec["period"] * TILE_TICK_RATE))
    clear = [tile_column_clear(spec, col, back, k / TILE_TICK_RATE) for k in range(ticks)]
    if all(clear):
        return spec["period"]
    best = run = 0
    for ok in clear + clear:
        run = run + 1 if ok else 0
        best = max(best, run)
    return best / TILE_TICK_RATE


def tile_column_windows(spec, back):
    """Every column's window (`tile_column_window`), the shorter of the one from the stand point
    and the one from 1.5 m behind it, where a stand-in waiting for its column steps back to."""
    return [min(tile_column_window(spec, col, back), tile_column_window(spec, col, back + 1.5))
            for col in range(spec["cols"])]


class Course:
    """A course built forward from the start pad, one section at a time.

    The cursor is the FRONT edge of the last thing placed (`z`, decreasing as the course goes
    on), at height `y` (the top of the ground), on the line `x`.
    """

    def __init__(self, cid, name, blurb, theme, water=-6.0, seconds=0.0):
        self.doc = {
            "format": 1,
            "kind": "course",
            "id": cid,
            "name": name,
            "author": AUTHOR,
            "blurb": blurb,
            "theme": theme,
            "water_height": water,
            "start": {"at": [0, 0, 0], "size": [10, 8], "yaw": 0},
        }
        if seconds:
            self.doc["course_seconds"] = seconds
        self.pieces = []
        self.route = []
        self.checkpoints = []
        self.dressing = []
        # (z, x) at every route point: where the course is, for placing the stands beside it.
        self.spine = []
        self.x = 0.0
        self.y = 0.0
        self.z = -4.0
        # [b]Frames: how a course turns.[/b] Every section is written as if the course ran
        # down -Z, in the frame it was placed in: `frames[i]` is that frame's origin and
        # heading in the world (degrees, positive turning left, the way a piece's `yaw`
        # turns). A turn starts a new frame; `build()` carries everything into the world. A
        # course that never turns stays in frame 0, which is the world, so its document is
        # the same to the byte as before turns existed.
        self.frames = [(0.0, 0.0, 0.0)]
        self.f = 0
        # Which branch of a fork the cursor is on (0: the one way everybody goes), and
        # whether that branch is the risky one. See `fork`.
        self.branch = 0
        self.risky = False
        # The middle of the pad's front first: the pad is wider than the ground after it, and
        # somebody restarting at its side who ran straight at the next point went off the edge.
        self.point(-3.2, reach=1.0)

    # --- primitives -----------------------------------------------------------

    def add(self, **piece):
        for key, value in list(piece.items()):
            if isinstance(value, float):
                piece[key] = r(value)
        piece["_f"] = self.f
        piece["_r"] = len(self.route)
        self.pieces.append(piece)
        return len(self.pieces) - 1

    def _route(self, point):
        point["_f"] = self.f
        if self.branch:
            point["branch"] = self.branch
            if self.risky:
                point["risky"] = True
        self.route.append(point)

    def _spine(self, entry):
        self.spine.append(entry + (self.f,))

    def _checkpoint(self, checkpoint):
        if self.branch:
            raise SystemExit("%s: a checkpoint inside a fork's branch, which the other branch never crosses"
                             % self.doc["id"])
        checkpoint["_f"] = self.f
        self.checkpoints.append(checkpoint)

    def _dress(self, item):
        item["_f"] = self._dress_frame
        self.dressing.append(item)

    def _last_point(self):
        """The last route point on the way the cursor is going: inside a fork's branch, the
        other branch's points are not behind it."""
        for point in reversed(self.route):
            if point.get("branch", 0) in (0, self.branch):
                return point
        return None

    def _last_z(self):
        """The z of the last route point in this frame (one placed before a turn carried into
        it), or far behind when there is none."""
        last = self._last_point()
        if last is None:
            return 1e9
        if last["_f"] == self.f:
            return last["at"][2]
        wx, wz = self._world(last["_f"], last["at"][0], last["at"][2])
        return self._local(self.f, wx, wz)[1]

    def point(self, z, x=None, y=None, **flags):
        self._route({"at": v(self.x if x is None else x, self.y if y is None else y, z), **flags})
        self._spine((z, self.x if x is None else x, self.y if y is None else y))

    def deck(self, length, width=6.0, role="deck", thick=1.0, x=None):
        """Ground from the cursor forward `length` metres, its top at the cursor's height."""
        cx = self.x if x is None else x
        self.add(kind="box", at=v(cx, self.y - thick / 2, self.z - length / 2),
                 size=v(width, thick, length), role=role)
        self.z -= length

    def lead_in(self, metres=3.5):
        """A point on the line `metres` short of the edge, so a runner lines up before a jump.

        A stand-in coming off a sweeper half a metre to one side, or put back at a checkpoint at
        the side of the deck, ran at the take-off point on a diagonal and jumped sideways off
        the first ball every time. Only when it is ahead of the last point: behind it, the
        runner would turn round for it."""
        last = self._last_z()
        if last > self.z + metres + 0.8:
            self.point(self.z + metres)

    def stand(self, z, reach=0.6):
        """A point to stand at before something to board, unless the last point is already at
        or past it: a run-out ends with a point 1.5 m short of its edge, and a stand point half
        a metre BEHIND that one was reached the moment the first was, so the runner never
        slowed for it and jumped onto Trapdoor Run's tiles at a run, two rows too far."""
        last = self._last_z()
        if last > z + 0.3:
            self.point(z, reach=reach)
        else:
            self._last_point()["reach"] = reach

    def gap(self, length, rise=0.0, dx=0.0):
        """A jump: a point just short of the edge that says jump, and the gap itself."""
        self.lead_in()
        self.point(self.z + 0.5, jump=True, reach=0.55)
        self.z -= length
        self.y += rise
        self.x += dx

    def ahead(self, metres=1.0, **flags):
        """A route point `metres` onto whatever is placed next."""
        self.point(self.z - metres, **flags)

    def checkpoint(self, width=6.0, back=1.6):
        """A checkpoint across the ground just placed, `back` metres from its edge."""
        self._checkpoint({"at": v(self.x, self.y, self.z + back), "size": v(width, 4.0, 2.4)})

    def safe(self, length=9.0, width=6.0):
        """Plain deck with a checkpoint near its START: a runner put back here has the rest of
        it to get up to speed and line up. A checkpoint a metre and a half from the next jump,
        which is where the old courses had them, put a runner back with no run-up at all, and
        a stand-in fell off the first ball from it over and over."""
        self.run_out(length, width)
        self.checkpoint(width, back=length - 2.0)

    # --- sections -------------------------------------------------------------

    def run_out(self, length=8.0, width=6.0):
        self.deck(length, width)
        self.point(self.z + 1.5)

    def side_sweeper(self, length=14.0, width=6.0, speed=80.0, height=0.55, arms=2, phase=0.0, side=1):
        """A deck with a low arm swinging across it from a post at its side. Jump it.

        The arm reaches just short of the far edge, so the far edge is a place a careful runner
        can stand; and the deck is longer than the arm's sweep, so there is ground before it to
        watch it from.
        """
        z0 = self.z
        self.deck(length, width)
        hub_x = self.x + side * (width / 2 + 0.6)
        hub_z = z0 - length / 2
        arm = width + 0.4
        self.add(kind="spinner", at=v(hub_x, self.y, hub_z), arm_length=arm, arm_height=height,
                 arm_thickness=0.35, speed=speed, arms=arms, phase=phase)
        self.point(self.z + 1.2)

    def high_sweeper(self, length=14.0, width=6.0, speed=70.0, arms=2, phase=0.0, side=1):
        """An arm at head height, swinging across from a post at the side. Duck it.

        1.45 m up and 0.3 m thick: its underside is at 1.3 m, over a crouched player (0.9 m)
        and through a standing one (1.8 m). Running crouched is slow, which is the price.
        """
        z0 = self.z
        self.deck(length, width)
        hub_x = self.x + side * (width / 2 + 0.6)
        self.add(kind="spinner", at=v(hub_x, self.y, z0 - length / 2), arm_length=width + 0.4,
                 arm_height=1.45, arm_thickness=0.3, hub_height=2.2, speed=speed, arms=arms,
                 phase=phase)
        self.point(self.z + 1.2)

    def centre_spinner(self, size=11.0, speed=70.0, height=0.6, arms=2, phase=0.0):
        """A square deck with a post in the middle and arms round it; run round the post."""
        z0 = self.z
        self.deck(size, size)
        hub_z = z0 - size / 2
        arm = size / 2 - 0.3
        self.add(kind="spinner", at=v(self.x, self.y, hub_z), arm_length=arm, arm_height=height,
                 arm_thickness=0.35, speed=speed, arms=arms, phase=phase, hub_radius=0.6)
        # Round the post, hopping the arms: with three or four of them on a deck this size the
        # window to walk through untouched is too short to wait for.
        side = self.x - size / 2 + 2.9
        # Straight on first, then out to the side: a diagonal from the narrower ground before
        # cut across its corner and into the water.
        self._route({"at": v(self.x, self.y, z0 - 0.8)})
        self._route({"at": v(side, self.y, z0 - 2.2)})
        # And back to the middle well short of the far edge, so whatever comes next is run at
        # straight: back to the middle at the edge itself, the jump that follows went sideways.
        self._route({"at": v(side, self.y, self.z + 3.4)})
        self._route({"at": v(self.x, self.y, self.z + 1.6)})
        # And four metres of plain deck after it: the arms reach to within 0.3 m of the edge,
        # and a stand-in hopping the last one came down two metres to the side of the jump
        # that followed and took it sideways into the water.
        self.deck(4.0)

    def balls(self, count=3, radius=1.5, spacing=3.6, first=3.2, last=2.6):
        """Big balls to hop across, top to top. Land on the top or slide off it.

        Under a running jump apart (4.0 of 4.9 m): a jump is cut short in the air by
        holding back, never stretched, so a top a full jump away is one any slower take-off
        falls short of.
        """
        lift = 0.4
        self.lead_in()
        self.point(self.z + 0.6, jump=True, reach=0.55)
        z = self.z - first
        for i in range(count):
            self.add(kind="ball", at=v(self.x, self.y + lift - radius, z), radius=radius, role="hazard")
            self._route({"at": v(self.x, self.y + lift, z), "jump": True, "reach": 0.75})
            z -= spacing
        self.z = z + spacing - last
        self.point(self.z - 1.2)

    def stones(self, spots, size=1.3, sink=0.3, until=None, wait=False):
        """Small square stones over the water, hopped one to the next: `spots` are (metres on
        from the cursor, metres across) for each stone's middle.

        Their tops are `sink` below the deck before, so the first hop is a small step down and
        the last a small step up. Measured from a ported course's rooms (Dan's Course), where the
        stones are a metre and a quarter and scattered, not in a line: every hop is under the
        balls' 3.6 m centre to centre, which is the one a stand-in is known to clear."""
        self.lead_in()
        self.point(self.z + 0.6, jump=True, reach=0.55)
        z0 = self.z
        for dz, dx in spots:
            top = self.y - sink
            self.add(kind="box", at=v(self.x + dx, top - 0.3, z0 - dz), size=v(size, 0.6, size), role="deck")
            point = {"at": v(self.x + dx, top, z0 - dz), "jump": True, "reach": 0.7}
            if wait:
                # Stand on the stone until the way to the next is clear of every bar: a bar
                # sweeping along a room crosses a stone for a second, and a stand-in that
                # hopped as it came fell on it nineteen times in Dan's third room.
                point["wait"] = True
            self._route(point)
        self.z = z0 - (until if until is not None else spots[-1][0] + size / 2 + 0.8)
        self.point(self.z - 0.4)

    def laser(self, at, across, along, reach, period, duty=0.4, phase=0.0, height=0.3, rest=None, over=None,
              start=None):
        """A low bar that sweeps through the stones: a pusher whose ram is a thin bar a hand's
        breadth over their tops, so it is jumped, and whose home is clear of every stone.

        `at` is (metres on from the cursor, metres across) of the bar's middle at rest, `across`
        the bar's length across the way (the sweep goes along the course, 0 yaw) or, with
        `along`, its length when the sweep goes across it (90 / -90 yaw on `rest` = +1 or -1: the
        side it rests on). `over` is the height of what it sweeps over, default the cursor's;
        `start` the z `at` counts from, default the cursor (after `stones`, the cursor is past them)."""
        top = self.y if over is None else over
        z0 = self.z if start is None else start
        if rest is None:
            size = v(across, height, 0.25)
            piece = dict(yaw=0.0)
        else:
            size = v(along, height, 0.25)
            piece = dict(yaw=90.0 if rest > 0 else -90.0)
        self.add(kind="pusher", at=v(self.x + at[1], top + 0.05 + height / 2, z0 - at[0]), size=size,
                 reach=reach, period=period, duty=duty, phase=phase, **piece)

    def lily_pads(self, count=4, radius=1.8, speed=45.0, spacing=3.6, swing=0.4, first=3.2, last=2.4):
        """Small turning discs over the water, side to side, to hop across centre to centre.

        The balls' rhythm with the opposite problem: a pad is flat and easy to land on, and it
        CARRIES you -- stand on one and you are turned off the line to the next. So the hop is
        taken at once, from the middle, where the carry is least (the edge of a 1.6 m pad at
        55 degrees a second moves 1.5 m/s; its middle, nothing). Alternate pads turn the other
        way, so standing still is never safe in the same direction twice.

        [b]Nearly in line, at the balls' spacing.[/b] The first version zig-zagged 2.2 m across
        and a stand-in fell 56 times on the first pad: a jump is steered very little in the
        air, so it landed past the centre and wide of it, walked back to the centre, and took
        the next hop carrying that walk's momentum backwards into the pond. 0.4 m either side
        is a line a player can see is not straight, and one a jump can still follow.
        """
        self.lead_in()
        self.point(self.z + 0.6, jump=True, reach=0.55)
        z = self.z - first
        for i in range(count):
            x = self.x + (-swing if i % 2 == 0 else swing)
            self.add(kind="turntable", at=v(x, self.y - 0.3, z), radius=radius, thickness=0.6,
                     speed=speed if i % 2 == 0 else -speed, role="hazard")
            self._route({"at": v(x, self.y, z), "jump": True, "reach": 0.7, "onward": True})
            z -= spacing
        self.z = z + spacing - radius - last
        self.point(self.z - 1.2)

    def mover_crossing(self, length=9.0, size=4.0, period=6.0, phase=0.0, dx=0.0):
        """A gap only a mover crosses: step on at one end, step off at the other."""
        near = self.z
        far = self.z - length
        start = v(self.x, self.y - 0.4, near - size / 2 - 0.3)
        end = v(self.x + dx, self.y - 0.4, far + size / 2 + 0.3)
        self.add(kind="mover", **{"from": start, "to": end}, size=v(size, 0.6, size), period=period,
                 phase=phase)
        # A point two metres back to wait at, then the mover's middle and the far side as
        # things to land on: a stand-in runs from the wait point and jumps at whichever edge it
        # reaches, and stays on the mover until the far side is in reach.
        self.stand(near + 2.0)
        self._route({"at": v(start[0], self.y, start[2]), "board": True, "ride": True,
                           "reach": 0.9})
        self._route({"at": v(self.x + dx, self.y, far - 1.4), "board": True, "reach": 0.9})
        self.z = far
        self.x += dx

    def turntable(self, radius=5.0, speed=35.0, spinner_speed=0.0):
        """A disc that turns. Across the middle is steady; the rim is a ride.

        With a spinner on it the way across is 1.6 m off the middle, round the hub, and the
        jump onto it is taken on that line: taken down the middle, a stand-in in the air
        steered sideways at the point beside it, came down running across the disc at six
        metres a second and went off its side (Spin Cycle, a field of eight, sixteen falls)."""
        # The arms against the disc, not with it: an arm turning nearly as the disc does sits
        # on a rider and pushes them round with it, too slowly to hop (a disc at 40 with arms
        # at 50 put seventeen of a field of sixteen in the water).
        if spinner_speed and abs(spinner_speed - speed) < 60.0:
            raise SystemExit("%s: a spinner on a turntable turns within 60 degrees a second of it" % self.doc["id"])
        off = -1.6 if spinner_speed else 0.0
        if off:
            self.point(self.z + 3.5, x=self.x + off)
            self.point(self.z + 0.6, x=self.x + off, jump=True, reach=0.55)
        else:
            self.lead_in()
            self.point(self.z + 0.6, jump=True, reach=0.55)
        centre_z = self.z - 1.4 - radius
        self.add(kind="turntable", at=v(self.x, self.y - 0.3, centre_z), radius=radius,
                 thickness=0.6, speed=speed)
        if spinner_speed:
            self.add(kind="spinner", at=v(self.x, self.y, centre_z), arm_length=radius - 0.2,
                     arm_height=0.6, speed=spinner_speed, arms=2, hub_radius=0.5)
            self._route({"at": v(self.x - 1.6, self.y, centre_z + radius - 1.2)})
            self._route({"at": v(self.x - 1.6, self.y, centre_z - radius + 1.2), "jump": True,
                               "reach": 0.6})
        else:
            self._route({"at": v(self.x, self.y, centre_z + radius - 1.0)})
            self._route({"at": v(self.x, self.y, centre_z - radius + 1.0), "jump": True,
                               "reach": 0.6})
        self.z = centre_z - radius - 1.4
        self.point(self.z - 1.2)

    def pusher_alley(self, width=2.6, count=3, period=2.6, reach=2.4, step=4.5, length=None):
        """A narrow walkway with rams that strike across it from alternate sides, a step apart.

        4.5 m apart, waited for 2.4 m short of each: at 3.5 m, somebody stopping for the next
        ram slid into its reach, and somebody waiting was in reach of the one behind.
        """
        z0 = self.z
        self.deck((count + 1) * step, width)
        for i in range(count):
            z = z0 - step * (i + 1)
            side = 1 if i % 2 == 0 else -1
            # The ram rests just off the walkway's edge and strikes across it.
            rest_x = self.x + side * (width / 2 + 0.9)
            self.add(kind="pusher", at=v(rest_x, self.y + 0.9, z), size=v(1.6, 1.6, 1.4),
                     yaw=90.0 if side > 0 else -90.0, reach=reach, period=period,
                     duty=0.35, phase=0.27 * i)
            self.add(kind="box", at=v(rest_x + side * 1.1, self.y + 0.8, z), size=v(0.6, 2.6, 2.0),
                     role="pillar")
            self._route({"at": v(self.x, self.y, z + 2.4), "wait": True, "reach": 0.7})
        self._route({"at": v(self.x, self.y, self.z + 1.0)})

    def pendulums(self, width=3.0, count=3, period=3.0, swing=55.0, step=4.2, length=None, radius=0.95):
        """A beam with hammers swinging across it, a step apart, and room between them.

        The hammers are 4.2 m apart and somebody waiting for the next one waits half way
        between two: at 3.2 m the ball behind reached a person standing still in front of it.
        """
        z0 = self.z
        self.deck((count + 1) * step, width)
        for i in range(count):
            z = z0 - step * (i + 1)
            self.add(kind="pendulum", pivot=v(self.x, self.y + 6.2, z), length=5.0, radius=radius,
                     swing=swing, period=period, phase=0.31 * i, yaw=0.0)
            self._route({"at": v(self.x, self.y, z + step / 2), "wait": True, "reach": 0.7})
        self._route({"at": v(self.x, self.y, self.z + 1.0)})

    def tiles(self, cols=3, rows=4, tile=2.0, period=3.2, down=0.28, seed=1):
        """A grid of tiles, each of which drops out on its own schedule and comes back."""
        gap = 0.3
        pitch = tile + gap
        depth = rows * pitch - gap
        self.stand(self.z + 2.0)
        z0 = self.z - 1.2
        centre_z = z0 - depth / 2
        self.add(kind="tiles", at=v(self.x, self.y - 0.25, centre_z), cols=cols, rows=rows,
                 tile=tile, gap=gap, thickness=0.5, period=period, down=down, seed=seed)
        spec = {"rows": rows, "cols": cols, "tile": tile, "gap": gap, "period": period, "down": down, "seed": seed}
        windows = tile_column_windows(spec, self._last_z() - centre_z)
        if min(windows) < TILE_FAIR_WINDOW:
            raise SystemExit("%s: the tiles with seed %d have a column clear too briefly to cross (%s s on end "
                             "by column; %.1f s at least): choose another seed or period" % (
                                 self.doc["id"], seed, ", ".join("%.2f" % w for w in windows), TILE_FAIR_WINDOW))
        for row in range(rows):
            z = z0 - tile / 2 - row * pitch
            self._route({"at": v(self.x, self.y, z), "board": True, "reach": 0.6})
        self.z = z0 - depth - 1.2
        self.point(self.z - 1.2, board=True)

    def rollers(self, count=3, radius=1.1, speed=70.0, length=6.0, spacing=3.4, first=3.2, last=2.6):
        """Logs across the way, rolling. Hop from top to top; stand still and go backwards.

        Spaced like the balls, a running jump apart: logs a stride apart were overshot.
        """
        self.lead_in()
        self.point(self.z + 0.6, jump=True, reach=0.55)
        z = self.z - first
        for i in range(count):
            self.add(kind="roller", at=v(self.x, self.y - radius, z), length=length, radius=radius,
                     speed=speed if i % 2 == 0 else -speed)
            self._route({"at": v(self.x, self.y, z), "jump": True, "reach": 0.75})
            z -= spacing
        self.z = z + spacing - last
        self.point(self.z - 1.2)

    def seesaws(self, count=3, length=5.0, width=4.0, amplitude=14.0, period=4.0, gap=1.6):
        """Planks that tip on a slow cycle. Cross one while it is level."""
        for i in range(count):
            self.point(self.z + 0.5, jump=True, reach=0.55)
            self.z -= gap
            centre = self.z - length / 2
            self.add(kind="seesaw", at=v(self.x, self.y - 0.25, centre), size=v(width, 0.5, length),
                     amplitude=amplitude, period=period, phase=0.33 * i)
            self._route({"at": v(self.x, self.y, centre)})
            self.z -= length
        self.point(self.z - 1.2)

    def conveyor_climb(self, length=12.0, width=4.0, rise=2.0, speed=3.0):
        """A ramp with the belt running against you."""
        pitch = math.degrees(math.atan2(rise, length))
        slope = math.hypot(length, rise)
        centre = v(self.x, self.y + rise / 2 - 0.25 * math.cos(math.radians(pitch)), self.z - length / 2)
        self.add(kind="ramp", at=centre, size=v(width, 0.5, slope), pitch=pitch, role="pillar")
        # The belt lies ON the ramp: the same pitch, a few centimetres proud of it. A belt laid
        # flat at the ramp's middle height was a wall half way up it.
        self.add(kind="conveyor", at=v(self.x, self.y + rise / 2 + 0.03, self.z - length / 2),
                 size=v(width * 0.8, 0.06, slope * 0.95), speed=-speed, pitch=pitch)
        self.z -= length
        self.y += rise
        self.point(self.z + 0.6)

    def flat_belt(self, length=12.0, width=4.0, speed=3.5):
        """A flat belt running backwards: the run is slower than it looks."""
        z0 = self.z
        self.deck(length, width, role="pillar", thick=0.8)
        self.add(kind="conveyor", at=v(self.x, self.y + 0.03, z0 - length / 2),
                 size=v(width * 0.9, 0.06, length * 0.96), speed=-speed)
        self.point(self.z + 1.0)

    def bouncer_up(self, rise=3.5, power=13.0):
        """A pad that throws you up onto the next level."""
        self.add(kind="bouncer", at=v(self.x, self.y - 0.2, self.z - 1.4), size=v(2.4, 0.4, 2.4),
                 power=power)
        self.add(kind="box", at=v(self.x, self.y - 0.5, self.z - 1.4), size=v(3.2, 0.6, 3.2), role="pillar")
        self.point(self.z - 1.4, reach=0.5)
        self.z -= 2.6
        self.y += rise
        self.point(self.z - 1.4)

    def waterfalls(self, count=3, width=6.0, spacing=6.5, period=3.2, duty=0.4, slime=False, height=4.5,
                   stagger=0.37):
        """A deck with curtains of water (or slime) pouring across it, pushing whoever is under one
        off the side. Wait for one to stop, run through, wait for the next.

        A curtain is on for `duty` of its period, which leaves a window of over a second and a
        half at 3.2 s; each comes down `stagger` of a period after the one before, so the windows
        do not line up and the run is a series of waits, never one dash. Alternate curtains pour
        off alternate sides. The wait point is 2.4 m short of each: the curtain is 1.2 m thick,
        and somebody standing 1 m short of a pouring one was in its splash.
        """
        z0 = self.z
        self.deck(spacing * count + 2.0, width)
        tint = [0.55, 0.92, 0.35] if slime else [0.55, 0.80, 0.98]
        for i in range(count):
            z = z0 - spacing * (i + 0.5) - 1.0
            self.add(kind="fall", at=v(self.x, self.y, z), size=v(width, height, 1.2), period=period,
                     duty=duty, phase=stagger * i, push=9.0, yaw=0.0 if i % 2 == 0 else 180.0, tint=tint)
            self._route({"at": v(self.x, self.y, z + 2.4), "wait": True, "reach": 0.7})
            self._spine((z + 2.4, self.x, self.y))
        self.point(self.z + 1.0)

    def trampolines(self, count=3, power=10.0, pad=3.2, gap=3.0, first=2.6):
        """Bouncy pads over the water: land on one and it throws you up and on to the next.

        A runner arriving at a run leaves each pad at the run and comes down a pad later: at
        10 m/s up a bounce lasts a second, about seven metres at a run, so pads 3.2 m deep with
        3 m of water between are a bounce apart, landing a metre in. Steering in the air is what
        it asks (the route's points are tops, braked toward); missing a pad is the water.
        """
        self.lead_in()
        self.point(self.z + 0.6, jump=True, reach=0.55)
        z = self.z - first - pad / 2
        for i in range(count):
            self.add(kind="bouncer", at=v(self.x, self.y - 0.2, z), size=v(3.2, 0.4, pad), power=power)
            self.add(kind="box", at=v(self.x, self.y - 0.6, z), size=v(3.6, 0.5, pad + 0.4), role="pillar")
            self._route({"at": v(self.x, self.y, z), "bounce": True, "reach": 1.2})
            self._spine((z, self.x, self.y))
            z -= pad + gap
        self.z = z + pad + gap - pad / 2 - first
        self.point(self.z - 1.2)

    def beam(self, length=10.0, width=1.0):
        """A narrow beam, run straight down its middle."""
        self.deck(length, width)
        self.point(self.z + 1.2)

    def finish(self, size=10.0):
        self.deck(size, size, role="safe")
        self.doc["finish"] = {
            "at": v(self.x, self.y, self.z + size - 1.6),
            "size": v(size, 4.0, 2.0),
            "lounge": v(self.x, self.y, self.z + size / 2 - 1.0),
        }
        self._finish_f = self.f
        self.point(self.z + size / 2)

    # --- turns, curves, climbs and forks ----------------------------------------
    #
    # [b]A course is a show, not a corridor.[/b] Every course used to run down one straight line;
    # these bend it, lift it and split it, out of pieces every game build already has (a turn
    # is a round deck, a climb a ramp), so a course that only turns plays on any mg-wipeout.
    # A fork needs one from 2026-10-12 on: its document says `format` 2, which an older game
    # refuses with a sentence instead of sending its stand-ins down both branches in turn.

    def _world(self, f, x, z):
        ox, oz, h = self.frames[f]
        if f == 0:
            return x, z
        c, s = math.cos(math.radians(h)), math.sin(math.radians(h))
        return ox + x * c + z * s, oz - x * s + z * c

    def _local(self, f, wx, wz):
        ox, oz, h = self.frames[f]
        if f == 0:
            return wx, wz
        c, s = math.cos(math.radians(h)), math.sin(math.radians(h))
        dx, dz = wx - ox, wz - oz
        return dx * c - dz * s, dx * s + dz * c

    def _pivot(self, x, z, angle):
        """A new frame whose origin is local (x, z) of this one, turned by `angle` degrees."""
        wx, wz = self._world(self.f, x, z)
        self.frames.append((wx, wz, self.frames[self.f][2] + angle))
        self.f = len(self.frames) - 1
        self.x = 0.0
        self.z = 0.0

    def turn(self, angle, radius=4.5):
        """A round deck where the course changes direction by `angle` degrees (positive turns
        left, as a piece's `yaw` does). Round so any angle meets it cleanly: the deck before
        and the deck after both run a metre into it. Two centimetres proud of them, so two
        coplanar tops never fight over the same pixels.

        A runner reaches the middle and turns there: at a run a stand-in carries about a metre
        past a point it changes direction at, and the disc has four and a half."""
        cz = self.z - radius + 1.0
        self.add(kind="cylinder", at=v(self.x, self.y - 0.5 + 0.02, cz), radius=radius, height=1.0,
                 role="deck")
        self.point(cz, reach=1.0)
        self._pivot(self.x, cz, angle)
        self.z = -(radius - 1.0)

    def curve(self, angle, length=16.0, steps=4, width=6.0):
        """A bend: `steps` straight lengths of deck, each turned a share of `angle` at a round
        joint (a disc as wide as the deck, which covers both the wedge a turned box leaves on
        the inside and the one it overlaps on the outside). A point at every joint, so a
        stand-in runs the arc rather than cutting its corner over the water."""
        seg = length / steps
        share = angle / float(steps)
        for _ in range(steps):
            self.deck(seg, width)
            self.add(kind="cylinder", at=v(self.x, self.y - 0.5 + 0.02, self.z), radius=width / 2,
                     height=1.0, role="deck")
            self.point(self.z, reach=1.0)
            self._pivot(self.x, self.z, share)

    def kink(self, angle, width=6.0):
        """A change of direction at the cursor with nothing but a round joint as wide as the
        deck: the deck before ends at its middle and the deck after starts there. A point on
        it, so a stand-in turns where the deck does."""
        self.add(kind="cylinder", at=v(self.x, self.y - 0.5 + 0.02, self.z), radius=width / 2,
                 height=1.0, role="deck")
        self.point(self.z, reach=1.0)
        self._pivot(self.x, self.z, angle)

    def detour(self, out, back=None, angle=30.0, side=1, width=6.0):
        """The long way round: off to `side` (+1 left) at `angle`, `out(course)` built on the
        way out, a turn back of twice the angle, `back(course)` on the way back, padded to the
        same length so the course comes back onto its own line, and a turn onto it. What a
        fork's safe branch is made of: the same distance down the course takes longer."""
        # Four and a half metres after each kink before anything: a stand-in turns at the kink
        # and needs a run at whatever comes first (Trapdoor Run's trampolines, a metre and a
        # half after one, were jumped from a standing start into the water forty times).
        self.kink(side * angle, width)
        self.deck(4.5, width)
        out(self)
        self.deck(2.0, width)
        leg = -self.z
        self.kink(-2.0 * side * angle, width)
        if back is not None:
            self.deck(4.5, width)
            back(self)
        self.leg_to(leg, radius=1.0, width=width)
        self.kink(side * angle, width)

    def u_turn(self, side=1, spacing=16.0, radius=4.5):
        """Two turns of 90 degrees the same way: the course comes back alongside itself,
        `spacing` metres over (centre to centre). A switchback is a climb, a u_turn, a climb.

        Sixteen metres by default: a side sweeper's arm reaches ten metres from the line on
        its own side, and the builder refuses a hazard that reaches another part of the
        course (`_check_shape`)."""
        self.turn(90.0 * side, radius)
        self.deck(spacing - 2.0 * (radius - 1.0), 6.0)
        self.turn(90.0 * side, radius)

    def leg_to(self, length, radius=4.5, width=6.0):
        """Plain deck to where the middle of a `turn` of `radius` would be `length` metres from
        the middle of the turn this leg started at: how a spiral's sides are made shorter each
        time round, whatever sections are on them."""
        end = -length + (radius - 1.0)
        if self.z < end - 0.01:
            raise SystemExit("%s: a leg is already longer than %s m" % (self.doc["id"], length))
        if self.z - end > 0.05:
            self.deck(self.z - end, width)

    def climb(self, length=10.0, rise=2.0, width=6.0):
        """A plain ramp up (or down, with a negative rise): a height change with nothing on it
        but the run. Under fifteen degrees, which a run takes without slowing."""
        pitch = math.degrees(math.atan2(rise, length))
        slope = math.hypot(length, rise)
        centre = v(self.x, self.y + rise / 2 - 0.25 * math.cos(math.radians(pitch)), self.z - length / 2)
        self.add(kind="ramp", at=centre, size=v(width, 0.5, slope), pitch=pitch, role="deck")
        self.z -= length
        self.y += rise
        self.point(self.z + 0.6)

    def teleport(self, dx, dz, dy=0.0, angle=0.0, width=3.0, length=3.0, tint=None):
        """A pad that sends a runner to the start of the next section: `dx`, `dz` metres from the
        cursor in this frame (anywhere, even back beside the course), `dy` higher, the way
        ahead turned `angle` degrees. The next section starts there as if it were the start of
        a new frame, so it needs 3 m of deck first (the runner lands 1.5 m in).

        The pad is solid, a still box of the `safe` role like a bouncer. The route has a point
        on the pad and one where the runner lands; a stand-in sent across carries on from the
        nearest point to where it stands (mg-wipeout does that, so the pad's own point need not
        be reached). Anywhere the layout puts the destination, keep it clear of the route by
        the same seven metres as any two legs: `_check_shape` measures along the route, and the
        sent runner skips the length between."""
        if self.branch:
            raise SystemExit("%s: a teleport inside a fork's branch" % self.doc["id"])
        pad = self.add(kind="teleport", at=v(self.x, self.y - 0.3, self.z - length / 2),
                       size=v(width, 0.6, length), role="safe", to=v(0, 0, 0))
        self.point(self.z - length * 0.6, reach=1.0)
        old = self.f
        self.z -= length
        self._pivot(self.x + dx, self.z + dz, angle)
        self.y += dy
        landing = self._world(self.f, 0.0, -1.5)
        lx, lz = self._local(old, landing[0], landing[1])
        piece = self.pieces[pad]
        piece["to"] = v(lx, self.y + 0.2, lz)
        piece["_nf"] = self.f
        if tint:
            piece["tint"] = tint
        self.point(-1.5, reach=1.0)

    def fork(self, safe, risky, spread=9.0, width=6.0, depth=7.0):
        """The way splits in two and joins again: `safe(course)` builds the left branch and
        `risky(course)` the right, each from the far edge of a wide deck, on its own lane
        `spread` metres to the side. The risky branch is meant to be the faster one; the
        stand-ins take it by `wo_bot_risk`, harder ones more often.

        Each branch must end facing the way it started and at the height it started; the
        shorter is lengthened with plain deck so both meet one wide deck, where the course
        goes on down the middle. No checkpoint inside a branch (the other branch never
        crosses it): `_checkpoint` refuses one."""
        full = 2.0 * spread + width
        self.deck(depth, full)
        self.point(self.z + depth - 2.0)
        z0, x0, y0, f0 = self.z, self.x, self.y, self.f
        ends = []
        for number, (build, risky_branch, side) in enumerate(((safe, False, -1), (risky, True, 1)), start=1):
            self.f, self.x, self.y, self.z = f0, x0 + side * spread, y0, z0
            self.branch, self.risky = number, risky_branch
            # Across the wide deck to the lane first: run straight from the middle at whatever
            # the branch starts with, and the line crosses water beside the lane (Trapdoor
            # Run's detour: ten falls a field at its first kink).
            self.point(z0 + 1.5)
            # And three metres of lane before the branch's own sections: the run from the middle
            # comes onto the lane at an angle, and a jump three metres after it was taken
            # sideways off Grand Tour's first ball by most of a field.
            self.deck(3.0, width)
            build(self)
            if abs(((self.frames[self.f][2] - self.frames[f0][2]) + 180.0) % 360.0 - 180.0) > 0.01:
                raise SystemExit("%s: a fork's branch ends facing another way" % self.doc["id"])
            if abs(self.y - y0) > 0.01:
                raise SystemExit("%s: a fork's branch ends at another height" % self.doc["id"])
            wx, wz = self._world(self.f, self.x, self.z)
            lx, lz = self._local(f0, wx, wz)
            ends.append((number, risky_branch, lx, lz))
        join = min(end[3] for end in ends)
        for number, risky_branch, lx, lz in ends:
            self.f, self.x, self.y, self.z = f0, lx, y0, lz
            self.branch, self.risky = number, risky_branch
            if lz - join > 0.05:
                self.deck(lz - join, width)
            self.point(join + 1.0)
        self.branch, self.risky = 0, False
        self.f, self.x, self.y, self.z = f0, x0, y0, join
        self.deck(depth, full)
        self.point(self.z + depth / 2)
        self.doc["format"] = 2

    # --- the show -------------------------------------------------------------

    def where(self, z, f=None):
        """The course's (x, y) nearest to `z` in frame `f`, from the route."""
        f = self._dress_frame if f is None else f
        spine = [p for p in self.spine if p[3] == f] or self.spine
        best = min(spine, key=lambda p: abs(p[0] - z))
        return best[1], best[2]

    def stands(self, z0, z1, side=1, rows=6, gap=7.0, text="", seed=1, tint=(0.95, 0.35, 0.25)):
        """A grandstand beside the course between z0 and z1, on `side` (+1 is +X), facing it."""
        mid = (z0 + z1) / 2
        x, y = self.where(mid)
        self._dress({"kind": "stands", "at": v(x + side * gap, y + 0.6, mid),
                              "size": v(abs(z1 - z0), rows * 0.55, rows * 0.9), "yaw": 90.0 if side > 0 else -90.0,
                              "seed": seed, "text": text, "tint": v(*tint)})

    def banner(self, z, side=1, gap=5.0, width=10.0, text="", tint=(0.95, 0.35, 0.25)):
        x, y = self.where(z)
        self._dress({"kind": "banner", "at": v(x + side * gap, y, z), "size": v(width, 1.6, 0.2),
                              "yaw": 90.0 if side > 0 else -90.0, "text": text, "tint": v(*tint)})

    def lights(self, z, side=1, gap=12.0, height=14.0):
        x, y = self.where(z)
        self._dress({"kind": "lights", "at": v(x + side * gap, y, z), "size": v(3, height, 1),
                              "yaw": 90.0 if side > 0 else -90.0})

    def screen(self, z, side=1, gap=10.0, width=9.0, text="", tint=(0.98, 0.70, 0.18)):
        """A big screen beside the course, turned to face runners coming toward it."""
        x, y = self.where(z)
        self._dress({"kind": "screen", "at": v(x + side * gap, y, z), "size": v(width, width * 0.45, 0.4),
                              "yaw": 180.0 - 25.0 * side, "text": text, "tint": v(*tint)})

    def flags(self, z, side=1, gap=5.5, length=18.0, seed=1):
        x, y = self.where(z)
        self._dress({"kind": "flags", "at": v(x + side * gap, y, z), "size": v(length, 5, 0.2),
                              "yaw": 90.0 if side > 0 else -90.0, "seed": seed})

    def event(self, tint=(0.95, 0.35, 0.25), every=45.0, text="WIPEOUT"):
        """The big-event dressing along a whole course: stands down both sides in turn, light
        towers between them, flags at the start, a screen at the start and one before the
        finish, and banners on the stands' backs. Placed after the course is built, from its
        route, so a course's dressing follows its shape."""
        self._dress_frame = 0
        if len(self.frames) > 1:
            self._event_turning(tint, every, text)
            return
        end = self.z
        self.flags(-10.0, side=1, seed=3)
        self.flags(-10.0, side=-1, seed=7)
        self.screen(-14.0, side=-1, gap=12.0, text="")
        z = -18.0
        side = 1
        seed = 1
        while z - 26.0 > end + 12.0:
            self.stands(z, z - 26.0, side=side, seed=seed, text=text, tint=tint)
            self.lights(z - 30.0, side=side, gap=13.0)
            z -= every
            side = -side
            seed += 1
        self.screen(end + 18.0, side=1, gap=12.0)
        self.stands(end + 14.0, end - 6.0, side=-1, rows=8, seed=seed + 1, text="FINISH", tint=tint)

    def _clear(self, f, x0, x1, z0, z1, margin=3.0):
        """Whether the rectangle (local to frame `f`) is clear of the course: no route point and
        no piece within `margin` of it, so a grandstand never stands on the next leg."""
        lo_x, hi_x = min(x0, x1) - margin, max(x0, x1) + margin
        lo_z, hi_z = min(z0, z1) - margin, max(z0, z1) + margin
        for item in self.route + self.pieces:
            at = item.get("at", item.get("pivot", item.get("from")))
            wx, wz = self._world(item["_f"], at[0], at[2])
            lx, lz = self._local(f, wx, wz)
            if lo_x <= lx <= hi_x and lo_z <= lz <= hi_z:
                return False
        return True

    def _event_turning(self, tint, every, text):
        """`event` for a course that turns: stands down each straight long enough for one, on
        whichever side is clear of every other part of the course, a light tower behind each.
        Nothing is placed where it would stand on another leg; a course coiled tight gets
        fewer stands, never one in the way."""
        self.flags(-10.0, side=1, seed=3)
        self.flags(-10.0, side=-1, seed=7)
        if self._clear(0, -12.0, -16.0, -10.0, -18.0):
            self.screen(-14.0, side=-1, gap=12.0, text="")
        seed = 1
        side = 1
        last_f = self.f
        for f in range(len(self.frames)):
            zs = [p[0] for p in self.spine if p[3] == f]
            if not zs:
                continue
            top = min(max(zs), -18.0) if f == 0 else max(zs)
            bottom = min(zs) + (12.0 if f == last_f else 0.0)
            z = top - 2.0
            self._dress_frame = f
            while z - 26.0 > bottom:
                x, _ = self.where(z - 13.0)
                for s in (side, -side):
                    if self._clear(f, x + s * 5.5, x + s * 14.5, z, z - 30.0):
                        self.stands(z, z - 26.0, side=s, seed=seed, text=text, tint=tint)
                        self.lights(z - 30.0, side=s, gap=13.0)
                        seed += 1
                        side = -s
                        break
                z -= every
        self._dress_frame = last_f
        end = self.z
        x, _ = self.where(end + 4.0)
        for s in (-1, 1):
            if self._clear(last_f, x + s * 5.5, x + s * 14.5, end + 14.0, end - 6.0):
                self.stands(end + 14.0, end - 6.0, side=s, rows=8, seed=seed + 1, text="FINISH", tint=tint)
                break
        for s in (1, -1):
            if self._clear(last_f, x + s * 10.0, x + s * 15.0, end + 15.0, end + 21.0):
                self.screen(end + 18.0, side=s, gap=12.0)
                break
        self._dress_frame = 0

    # --- the document -----------------------------------------------------------

    def _to_world(self, item, keys=("at", "from", "to", "pivot"), turn_yaw=True):
        f = item.pop("_f", 0)
        h = self.frames[f][2]
        if f == 0:
            return
        for key in keys:
            if key in item:
                x, y, z = item[key]
                wx, wz = self._world(f, x, z)
                item[key] = v(wx, y, wz)
        if turn_yaw and h:
            yaw = (item.get("yaw", 0.0) + h + 180.0) % 360.0 - 180.0
            item["yaw"] = r(0.0 if abs(yaw) < 0.005 else yaw)

    def _hazards_near(self, at, margin=1.2):
        """The hazards whose reach includes `at`, with a metre to spare: a checkpoint (where a
        fall puts you back) must be in none. One was, on the first long First Splash: the
        restart was at the far end of the sweeper's arc and a stand-in was knocked in again as
        it stood up. Along and across each hazard's own frame, so it holds round a turn."""
        near = []
        for piece in self.pieces:
            kind = piece["kind"]
            if kind not in ("spinner", "pendulum", "pusher", "fall"):
                continue
            anchor = piece.get("at", piece.get("pivot"))
            h = math.radians(piece["_h"])
            dx, dz = at[0] - anchor[0], at[2] - anchor[2]
            across = dx * math.cos(h) - dz * math.sin(h)
            along = dx * math.sin(h) + dz * math.cos(h)
            if abs(at[1] - anchor[1]) > 3.5 and kind != "pendulum":
                continue
            if kind == "spinner":
                if math.hypot(dx, dz) < piece["arm_length"] + margin - 0.2:
                    near.append(piece)
            elif kind == "pendulum":
                if abs(along) < piece["radius"] + margin and abs(across) < 8.0 and abs(at[1] - anchor[1]) < 8.0:
                    near.append(piece)
            elif kind in ("pusher", "fall"):
                if abs(along) < piece["size"][2] / 2 + margin and abs(across) < 8.0:
                    near.append(piece)
        return near

    def _along(self):
        """How far along the route each point is, metres, walking each branch of a fork from
        the point before it; the point after a fork is as far as its shorter branch."""
        along = []
        last = {}
        fork_from = 0
        for i, point in enumerate(self.route):
            b = point.get("branch", 0)
            if i == 0:
                along.append(0.0)
                continue
            if b:
                prev = last.get(b, fork_from)
                along.append(along[prev] + math.dist(self.route[prev]["at"], point["at"]))
                last[b] = i
                continue
            if last:
                along.append(min(along[j] + math.dist(self.route[j]["at"], point["at"]) for j in last.values()))
                last = {}
            else:
                along.append(along[i - 1] + math.dist(self.route[i - 1]["at"], point["at"]))
            fork_from = i
        return along

    def _check_shape(self):
        """Refuses a course that runs into itself: two parts of the route closer than seven
        metres across (at any height under twelve) that are thirty metres apart along it, or a hazard that
        reaches a part of the route it was not placed on. A turning course can lay a leg
        beside another; this is what keeps it from laying one ON another."""
        along = self._along()
        for i in range(len(self.route)):
            for j in range(i + 1, len(self.route)):
                a, b = self.route[i], self.route[j]
                if a.get("branch", 0) and b.get("branch", 0):
                    continue
                if along[j] - along[i] < 30.0:
                    continue
                pa, pb = a["at"], b["at"]
                # Above or below counts too: a leg laid over another hides it from the camera and
                # drops whoever falls off it onto a part of the course already run.
                if math.hypot(pa[0] - pb[0], pa[2] - pb[2]) < 7.0 and abs(pa[1] - pb[1]) < 12.0:
                    raise SystemExit("%s: the route at %s runs into itself at %s" % (self.doc["id"], pa, pb))
        for piece in self.pieces:
            if piece["kind"] not in ("spinner", "pendulum", "pusher", "fall"):
                continue
            home = along[min(piece["_r"], len(along) - 1)]
            for j, point in enumerate(self.route):
                if abs(along[j] - home) < 25.0:
                    continue
                if piece in self._hazards_near(point["at"], margin=0.6):
                    raise SystemExit("%s: a %s at %s reaches the route at %s" % (
                        self.doc["id"], piece["kind"], piece.get("at", piece.get("pivot")), point["at"]))

    def build(self):
        for piece in self.pieces:
            piece["_h"] = self.frames[piece["_f"]][2]
            if "_nf" in piece:
                # Where the sent runner faces: the heading of the frame they land in.
                piece["heading"] = r(self.frames[piece.pop("_nf")][2])
            self._to_world(piece)
        for point in self.route:
            self._to_world(point, turn_yaw=False)
        for checkpoint in self.checkpoints:
            self._to_world(checkpoint)
        for item in self.dressing:
            self._to_world(item)
        finish = self.doc["finish"]
        finish["_f"] = getattr(self, "_finish_f", 0)
        self._to_world(finish, keys=("at", "lounge"))
        if "yaw" in finish:
            # The finish's own fields in the order a straight course writes them, then its turn.
            finish["yaw"] = finish.pop("yaw")
        for checkpoint in self.checkpoints:
            near = self._hazards_near(checkpoint["at"])
            if near:
                raise SystemExit("%s: the checkpoint at %s is in reach of %s" % (
                    self.doc["id"], checkpoint["at"], ", ".join(p["kind"] for p in near)))
        self._check_shape()
        for piece in self.pieces:
            piece.pop("_h", None)
            piece.pop("_r", None)
        self.doc["pieces"] = self.pieces
        self.doc["checkpoints"] = self.checkpoints
        self.doc["route"] = self.route
        if self.dressing:
            self.doc["dressing"] = self.dressing
        self.doc["toys"] = START_PEN_TOYS
        return self.doc


# dot-props' toys, read by mg-wipeout (a game from before them ignores the field). Loose ones only,
# by the family's rule for a competitive game: a person walks through a ball and pushes it, so it
# never holds a runner up or covers anybody, where a pad or a trampoline would be a way past an
# obstacle. A beach ball in each back corner of the start pen, to bat about while the gate is up;
# the pen's walls keep them in, and one the field carries out and into the water goes home.
START_PEN_TOYS = [
    {"toy": "beach_ball", "at": [-3.8, 0.0, 2.8]},
    {"toy": "beach_ball", "at": [3.8, 0.0, 2.8]},
]

THEMES = {
    "noon": {"sky": [0.42, 0.66, 0.92], "horizon": [0.80, 0.88, 0.95], "water": [0.12, 0.45, 0.62]},
    "lagoon": {"sky": [0.30, 0.70, 0.86], "horizon": [0.78, 0.92, 0.92], "water": [0.08, 0.55, 0.58]},
    "dusk": {"sky": [0.38, 0.36, 0.62], "horizon": [0.95, 0.66, 0.48], "water": [0.18, 0.24, 0.42],
             "sun": [1.0, 0.78, 0.60]},
    "storm": {"sky": [0.36, 0.42, 0.50], "horizon": [0.64, 0.68, 0.72], "water": [0.14, 0.26, 0.32]},
    "mint": {"sky": [0.50, 0.78, 0.80], "horizon": [0.86, 0.95, 0.90], "water": [0.10, 0.50, 0.46]},
    "space": {"sky": [0.05, 0.06, 0.14], "horizon": [0.20, 0.16, 0.34], "water": [0.04, 0.05, 0.12],
              "sun": [0.70, 0.74, 1.0]},
    "peach": {"sky": [0.56, 0.62, 0.86], "horizon": [0.98, 0.84, 0.72], "water": [0.16, 0.38, 0.60],
              "sun": [1.0, 0.90, 0.78]},
}


# --- The courses ----------------------------------------------------------------
#
# [b]Long enough to be a race, and the first play test is why.[/b] First Splash was finished in
# 22 s on a first try and every course was over before a field of runners had spread out. Each
# course is now about four to six minutes of sections for a stand-in that never makes a mistake
# (60 to 90 s; mg-wipeout's headless_courses measures it), which is a good run; a field of
# medium stand-ins takes half as long again with its falls, and the course's clock
# (`course_seconds`) is about three of those runs. mg-wipeout's tools/race_times measures the
# field per difficulty; docs/stand-ins.md there has the numbers.
#
# Checkpoints sit on plain deck after a hazard, never in one's reach (`build` refuses it).

def first_splash():
    c = Course("wo_first_splash", "First Splash",
               "The premiere, in front of a full house: a little of everything, gently, round the bay and up the hill, and then not so gently.",
               THEMES["noon"], seconds=300.0)
    c.run_out(8)
    c.gap(2.4)
    c.deck(6)
    c.side_sweeper(length=14, speed=60)
    c.safe(9)
    # Round to the right, along the front of the stands.
    c.turn(-90)
    c.deck(4)
    c.balls(count=3)
    c.deck(6)
    c.waterfalls(count=2, period=3.4, duty=0.35)
    c.safe(9)
    c.mover_crossing(length=9, period=6.0)
    c.deck(4)
    # And back the way the course started, in a long bend.
    c.curve(90, length=16, steps=4)
    c.deck(4)
    c.trampolines(count=3)
    c.safe(9)
    # Up the hill, where the hammers are.
    c.climb(length=10, rise=2.0)
    c.deck(3)
    c.pendulums(width=3.4, count=2, period=3.2)
    c.deck(4)
    c.high_sweeper(length=14, speed=55, side=-1)
    c.safe(9)
    c.turn(90)
    c.deck(4)
    c.lily_pads(count=3, speed=45)
    c.deck(5)
    c.rollers(count=2, speed=60.0)
    c.safe(9)
    c.tiles(cols=3, rows=3, period=3.4, down=0.24, seed=10)
    c.deck(5)
    c.turn(-90)
    c.deck(4)
    c.side_sweeper(length=13, speed=75, arms=2, side=-1, phase=30)
    c.safe(9)
    # Down off the hill to the water's edge for the last of it.
    c.climb(length=10, rise=-2.0)
    c.deck(3)
    c.waterfalls(count=3, period=3.2, duty=0.38, slime=True)
    c.deck(4)
    c.seesaws(count=2, amplitude=12, period=4.2)
    c.safe(9)
    c.balls(count=4, radius=1.6)
    c.deck(4)
    c.gap(2.2)
    c.finish()
    c.event(tint=(0.95, 0.35, 0.25), text="FIRST SPLASH")
    return c.build()


def spin_cycle():
    c = Course("wo_spin_cycle", "Spin Cycle",
               "Turntables, and arms that turn on top of them, and a course that turns with them. Nothing here stands still.",
               THEMES["lagoon"], seconds=300.0)
    c.run_out(6)
    c.turntable(radius=5.0, speed=30.0)
    c.safe(9)
    c.centre_spinner(size=11, speed=65)
    c.gap(2.4)
    c.safe(9)
    c.turn(90)
    c.deck(4)
    c.turntable(radius=5.5, speed=-40.0, spinner_speed=55.0)
    c.deck(6)
    c.lily_pads(count=4, speed=50)
    c.safe(9)
    c.curve(-90, length=16, steps=4)
    c.deck(4)
    c.side_sweeper(length=12, speed=95, arms=3)
    c.gap(2.6)
    c.deck(5)
    c.centre_spinner(size=12, speed=75, arms=3, phase=30)
    c.gap(2.2)
    c.safe(9)
    c.turn(-90)
    c.deck(4)
    c.turntable(radius=6.0, speed=45.0, spinner_speed=-60.0)
    c.deck(5)
    c.side_sweeper(length=14, speed=80, arms=2, side=-1, phase=60)
    c.safe(9)
    c.turn(90)
    c.deck(4)
    c.lily_pads(count=5, speed=50)
    c.deck(4)
    c.turntable(radius=5.0, speed=-35.0)
    c.safe(9)
    c.turntable(radius=5.5, speed=40.0, spinner_speed=-55.0)
    c.deck(4)
    c.gap(2.6)
    c.finish()
    c.event(tint=(0.20,0.72,0.80), text="SPIN CYCLE")
    return c.build()


def big_balls():
    c = Course("wo_big_balls", "Big Balls",
               "Six sets of balls round the bay and up the hill, each set bigger and further apart, wrecking balls between them, and the stands loving every splash.",
               THEMES["peach"], seconds=300.0)
    c.run_out(8)
    c.balls(count=3, radius=1.4)
    c.safe(9)
    c.pendulums(width=4.6, count=2, period=3.4, radius=1.4)
    c.deck(2)
    c.balls(count=4, radius=1.6)
    c.safe(9)
    c.turn(-90)
    c.deck(4)
    c.trampolines(count=2)
    c.deck(5)
    c.balls(count=3, radius=1.8)
    c.safe(9)
    c.pendulums(width=4.6, count=3, period=3.0, radius=1.4, swing=60)
    c.deck(2)
    c.balls(count=5, radius=1.6)
    c.safe(9)
    c.curve(90, length=16, steps=4)
    c.deck(4)
    c.climb(length=10, rise=2.0)
    c.deck(4)
    c.waterfalls(count=2, period=3.0, duty=0.4)
    c.deck(2)
    c.balls(count=4, radius=1.8, spacing=4.0)
    c.safe(9)
    c.side_sweeper(length=14, speed=70, arms=2)
    c.safe(9)
    c.turn(90)
    c.deck(4)
    c.balls(count=4, radius=1.6)
    c.deck(4)
    c.climb(length=10, rise=-2.0)
    c.safe(9)
    c.balls(count=6, radius=1.7, spacing=3.8)
    c.deck(4)
    c.finish()
    c.event(tint=(0.98, 0.52, 0.20), text="BIG BALLS")
    return c.build()


def punch_alley():
    c = Course("wo_punch_alley", "Punch Alley",
               "Narrow walkways and rams that strike across them, and slime to wait out between. Wait for the window.",
               THEMES["storm"], seconds=300.0)
    c.run_out(8)
    c.pusher_alley(count=3, period=2.6)
    c.safe(9)
    c.flat_belt(length=12, speed=3.0)
    c.deck(4)
    c.pusher_alley(count=4, period=2.2, reach=2.6)
    c.safe(9)
    c.waterfalls(count=3, period=3.0, duty=0.42, slime=True)
    c.safe(9)
    c.gap(2.6)
    c.deck(5)
    c.pusher_alley(count=3, period=1.8)
    c.safe(9)
    c.flat_belt(length=14, speed=3.5)
    c.deck(4)
    c.pusher_alley(count=5, period=2.4, reach=2.6)
    c.safe(9)
    c.high_sweeper(length=14, speed=65, arms=2)
    c.safe(9)
    c.gap(2.2)
    c.deck(4)
    c.pusher_alley(count=2, period=1.8)
    c.gap(2.2)
    c.finish()
    c.event(tint=(0.85,0.30,0.30), text="PUNCH ALLEY")
    return c.build()


def trapdoor_run():
    c = Course("wo_trapdoor_run", "Trapdoor Run",
               "Floors that drop out from under you, rides across the gaps between them, pads that throw you on, and at every fork the choice: the long jumps or the spinning pads straight across, or the long way round on the rides.",
               THEMES["mint"], seconds=330.0)
    c.run_out(8)
    c.tiles(cols=3, rows=4, period=3.4, down=0.25, seed=436)
    c.safe(9)
    c.mover_crossing(length=10, period=6.5)
    c.deck(5)

    def by_ride(k):
        k.deck(4)
        k.detour(lambda d: d.mover_crossing(length=9, period=7.0),
                 lambda d: d.mover_crossing(length=8, period=6.5, phase=0.5), angle=35.0)
        k.deck(3)

    def by_the_long_jumps(k):
        k.deck(5)
        k.gap(3.0)
        k.deck(3)
        k.gap(3.2)
        k.deck(3)
        k.gap(3.4)
        k.deck(4)

    c.fork(by_ride, by_the_long_jumps)
    c.safe(9)
    c.bouncer_up(rise=3.0)
    c.deck(6)
    c.turn(90)
    c.deck(4)
    c.tiles(cols=3, rows=3, period=2.8, down=0.28, seed=59)
    c.safe(9)
    c.trampolines(count=3)
    c.deck(5)
    c.mover_crossing(length=11, period=7.0)
    c.safe(9)
    c.turn(-90)
    c.deck(4)

    def round_by_ride(k):
        k.deck(4)
        k.detour(lambda d: d.trampolines(count=2),
                 lambda d: d.mover_crossing(length=9, period=7.0), angle=35.0)
        k.deck(3)

    def over_the_pads(k):
        k.deck(4)
        k.lily_pads(count=4, speed=45)
        k.deck(3)

    c.fork(round_by_ride, over_the_pads)
    c.safe(9)
    c.climb(length=14, rise=-3.0)
    c.safe(9)
    c.tiles(cols=3, rows=4, period=3.0, down=0.28, seed=42)
    c.deck(4)
    c.finish()
    c.event(tint=(0.30,0.80,0.55), text="TRAPDOOR RUN")
    return c.build()


def log_roll():
    c = Course("wo_log_roll", "Log Roll",
               "Rolling logs and tipping planks over open water. Keep moving or go backwards.",
               THEMES["lagoon"], seconds=300.0)
    c.run_out(8)
    c.rollers(count=3)
    c.safe(9)
    c.seesaws(count=3, amplitude=12, period=4.2)
    c.safe(9)
    c.rollers(count=4, speed=90.0)
    c.deck(4)
    c.gap(2.4)
    c.deck(5)
    c.lily_pads(count=4, speed=50)
    c.safe(9)
    c.seesaws(count=4, amplitude=14, period=3.8)
    c.deck(5)
    c.rollers(count=5, speed=80.0)
    c.safe(9)
    c.waterfalls(count=2, period=3.2, duty=0.38)
    c.deck(3)
    c.rollers(count=3, speed=100.0)
    c.safe(9)
    c.side_sweeper(length=13, speed=70, arms=2, side=-1)
    c.deck(3)
    c.seesaws(count=3, amplitude=16, period=3.6)
    c.safe(9)
    c.rollers(count=6, speed=75.0)
    c.deck(4)
    c.pendulums(width=3.2, count=2, period=3.0)
    c.deck(4)
    c.gap(2.4)
    c.finish()
    return c.build()


def the_sweeper():
    c = Course("wo_the_sweeper", "The Sweeper",
               "Low arms to jump and high arms to duck, from both sides, round every corner and faster every time, with a crowd that wants to see you go in.",
               THEMES["dusk"], seconds=300.0)
    c.run_out(8)
    c.side_sweeper(length=12, speed=60, height=0.55)
    c.gap(2.2)
    c.side_sweeper(length=12, speed=75, height=0.55, arms=3, phase=40, side=-1)
    c.safe(9)
    c.turn(90)
    c.deck(4)
    c.high_sweeper(length=14, speed=60, arms=2, side=-1)
    c.gap(2.2)
    c.centre_spinner(size=12, speed=80, height=0.6, arms=3)
    c.gap(2.4)
    c.safe(9)
    c.turn(-90)
    c.deck(4)
    c.side_sweeper(length=13, speed=90, height=0.55, arms=2, phase=90)
    c.deck(3)
    c.high_sweeper(length=14, speed=70, arms=2, side=-1, phase=45)
    c.safe(9)
    c.curve(-90, length=16, steps=4)
    c.deck(4)
    c.centre_spinner(size=12, speed=85, height=0.6, arms=3, phase=30)
    c.gap(2.2)
    c.deck(4)
    c.turntable(radius=5.5, speed=-35.0, spinner_speed=70.0)
    c.safe(9)
    c.turn(90)
    c.deck(4)
    c.side_sweeper(length=14, speed=100, height=0.55, arms=3, side=-1)
    c.deck(3)
    c.high_sweeper(length=14, speed=80, arms=3, phase=20, side=1)
    c.safe(9)
    c.turn(90)
    c.deck(4)
    c.centre_spinner(size=13, speed=95, height=0.6, arms=4, phase=10)
    c.gap(2.2)
    c.finish()
    c.event(tint=(0.62, 0.36, 0.82), text="THE SWEEPER")
    return c.build()


SPIRAL = (80.0, 70.0, 56.0)


def uphill_belt():
    c = Course("wo_uphill_belt", "Uphill Belt",
               "Up the hill in switchbacks: up the belts, up the bouncers, through the falls and the hammers, then round the spiral to a finish on the summit.",
               THEMES["noon"], seconds=300.0)
    c.run_out(8)
    c.conveyor_climb(length=12, rise=2.0, speed=2.5)
    c.safe(9)
    c.pendulums(width=3.4, count=2, period=3.0)
    c.deck(4)
    # The first switchback: back down the hill alongside, a level up.
    c.u_turn(side=1, spacing=18)
    c.deck(4)
    c.conveyor_climb(length=14, rise=2.4, speed=3.2)
    c.safe(9)
    c.bouncer_up(rise=3.0)
    c.deck(4)
    c.waterfalls(count=3, period=3.2, duty=0.4)
    c.deck(4)
    # The second: up the hill again, another level up.
    c.u_turn(side=-1, spacing=18)
    c.deck(4)
    c.conveyor_climb(length=16, rise=2.8, speed=3.6)
    c.safe(9)
    c.flat_belt(length=14, speed=4.0)
    c.deck(3)
    c.pendulums(width=3.2, count=3, period=2.8, swing=60)
    c.safe(9)
    # The spiral: four turns the same way round, each side shorter and higher than the one
    # before, to the summit in the middle.
    c.turn(90)
    c.deck(3)
    c.rollers(count=3, speed=70.0)
    c.deck(3)
    c.climb(length=10, rise=2.0)
    c.safe(9)
    c.leg_to(SPIRAL[0])
    c.turn(90)
    c.deck(3)
    c.side_sweeper(length=14, speed=80, arms=2, side=1)
    c.deck(3)
    c.conveyor_climb(length=12, rise=2.2, speed=3.8)
    c.safe(9)
    c.leg_to(SPIRAL[1])
    c.turn(90)
    c.deck(3)
    c.pusher_alley(count=3, period=2.4)
    c.deck(3)
    c.bouncer_up(rise=3.0)
    c.safe(9)
    c.leg_to(SPIRAL[2])
    c.turn(90)
    c.deck(3)
    c.trampolines(count=2)
    c.deck(4)
    c.finish()
    c.event(tint=(0.95,0.75,0.25), text="UPHILL BELT")
    return c.build()


def hammer_gauntlet():
    c = Course("wo_hammer_gauntlet", "Hammer Gauntlet",
               "Narrow beams under swinging hammers, wrecking balls, and rams along the way, up to the high beam and down again. The big crowd came for this one.",
               THEMES["storm"], seconds=300.0)
    c.run_out(8)
    c.pendulums(width=3.0, count=3, period=3.0)
    c.safe(9)
    c.gap(2.2)
    c.beam(length=8, width=1.6)
    c.gap(2.0)
    c.deck(5)
    c.pendulums(width=2.4, count=4, period=2.6, swing=60)
    c.safe(9)
    c.turn(-90)
    c.deck(4)
    c.pusher_alley(count=2, period=2.4)
    c.pendulums(width=2.4, count=2, period=2.2, swing=60)
    c.safe(9)
    c.pendulums(width=4.6, count=3, period=3.4, radius=1.5, swing=50)
    c.safe(9)
    # Up to the high beam: the long one, with the water a long way down.
    c.climb(length=12, rise=2.5)
    c.deck(4)
    c.gap(2.2)
    c.beam(length=12, width=1.4)
    c.gap(2.2)
    c.safe(9)
    c.turn(90)
    c.deck(4)
    c.pusher_alley(count=3, period=2.0)
    c.deck(3)
    c.pendulums(width=2.6, count=4, period=2.4, swing=62)
    c.safe(9)
    c.climb(length=12, rise=-2.5)
    c.deck(4)
    c.waterfalls(count=2, period=2.8, duty=0.4, slime=True)
    c.deck(3)
    c.turn(90)
    c.deck(4)
    c.pendulums(width=3.0, count=3, period=2.6, swing=58)
    c.safe(9)
    c.gap(2.2)
    c.beam(length=10, width=1.4)
    c.gap(2.2)
    c.deck(3)
    c.pendulums(width=4.6, count=2, period=3.0, radius=1.5, swing=55)
    c.deck(3)
    c.finish()
    c.event(tint=(0.20, 0.78, 0.82), text="HAMMER GAUNTLET")
    return c.build()


def grand_tour():
    c = Course("wo_grand_tour", "Grand Tour",
               "The long one, and the season's big night: round the whole bay and up the hill, a bit of everything, two forks to gamble on and no time to stand still.",
               THEMES["peach"], seconds=360.0)
    c.run_out(8)
    c.side_sweeper(length=12, speed=70)
    c.balls(count=3)
    c.safe(9)
    c.turntable(radius=5.0, speed=35)
    c.deck(5)
    c.pusher_alley(count=2, period=2.4)
    c.safe(9)
    c.turn(90)
    c.deck(4)

    def by_the_rollers(k):
        k.deck(3)
        k.rollers(count=3)
        k.deck(3)

    def by_the_ferry(k):
        k.deck(3)
        k.detour(lambda d: d.mover_crossing(length=9, period=7.5),
                 lambda d: d.mover_crossing(length=8, period=6.5, phase=0.3), angle=35.0)
        k.deck(3)

    # Safe is the left lane: the ferry is a wait; the logs are quicker if you stay on them.
    c.fork(by_the_ferry, by_the_rollers)
    c.safe(9)
    c.tiles(cols=3, rows=4, period=3.2, down=0.25, seed=34)
    c.deck(5)
    c.pendulums(width=3.0, count=2, period=3.0)
    c.safe(9)
    c.curve(-90, length=16, steps=4)
    c.deck(4)
    c.waterfalls(count=3, period=3.0, duty=0.4)
    c.deck(4)
    c.trampolines(count=3)
    c.safe(9)
    c.conveyor_climb(length=10, rise=1.6, speed=2.5)
    c.deck(4)
    c.lily_pads(count=4, speed=50)
    c.deck(4)
    c.high_sweeper(length=14, speed=65, side=-1)
    c.safe(9)
    c.turn(-90)
    c.deck(4)

    def over_the_balls(k):
        k.deck(3)
        k.balls(count=3, radius=1.6)
        k.deck(3)

    def round_the_seesaws(k):
        k.deck(3)
        k.detour(lambda d: d.seesaws(count=3, amplitude=12, period=4.4), angle=35.0)
        k.deck(3)

    c.fork(round_the_seesaws, over_the_balls)
    c.safe(9)
    c.pusher_alley(count=3, period=2.2, reach=2.6)
    c.safe(9)
    c.turn(90)
    c.deck(4)
    c.waterfalls(count=2, period=2.8, duty=0.42, slime=True)
    c.safe(9)
    c.side_sweeper(length=13, speed=90, arms=3, side=-1)
    c.deck(4)
    c.centre_spinner(size=11, speed=80, arms=3)
    c.gap(2.4)
    c.finish()
    c.event(tint=(0.98, 0.70, 0.18), text="GRAND TOUR")
    return c.build()


# --- Ported courses -------------------------------------------------------------
#
# Each of these follows one community obstacle course room by room: the room sequence, the
# obstacles and the measures are read from the original's geometry (1 source unit = 0.02 m,
# which makes a source runner's pace a wipeout runner's), and the courses use their own art,
# so only the layout is taken. Credit and links are in the README. The original's doors, lifts
# and teleports become what wipeout has: a hop, a bouncer, a drop, a ride, a ram.

def dans_course():
    c = Course("wo_dans_course", "Dan's Course",
               "A short, hard, unforgiving course in outer space after the original by Dan: stones over the dark, bars to hop, a tower to bounce up, a bridge, laser halls, a long fall to a field of pillars and the rides across it.",
               THEMES["space"], water=-22.0, seconds=480.0)
    c.doc["author"] = "Dan (port)"
    # 1. The start room and the narrow corridor to the first door.
    c.run_out(8)
    c.safe(7.6, width=2.6)
    # 2. Four stones over the pit, a low laser sweeping across all of them (room 3 of 9).
    c.deck(1.0, width=5.1)
    z0 = c.z
    c.stones([(3.0, 0.0), (6.6, 0.0), (10.2, 0.0), (13.8, 0.0)], size=1.5, until=15.4)
    c.laser((8.0, 2.96), across=0, along=11.2, reach=3.9, period=9.0, duty=0.35, rest=1, over=c.y - 0.3,
            start=z0)
    c.deck(3.2, width=5.1)
    c.checkpoint(5.1, back=1.2)
    # 3. Seven stones scattered down a long dark room, three bars sweeping along it.
    c.deck(3.7, width=2.0)
    c.deck(3.2, width=7.68)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, -0.7), (10.8, 0.8), (14.4, 1.0), (18.0, 0.3),
              (21.6, -0.9), (25.2, 0.2)], size=1.5, until=27.0)
    for home, reach, period, phase in ((4.8, 1.8, 11.0, 0.55), (12.0, 7.0, 12.0, 0.45), (21.0, 5.0, 11.0, 0.2)):
        c.laser((home, 0.0), across=7.4, along=0, reach=reach, period=period, duty=0.4, phase=phase,
                over=c.y - 0.3, start=z0)
    c.deck(3.2, width=7.68)
    c.checkpoint(7.68, back=1.2)
    # The rest follows the original's rooms in their order, read from its level file (0.02 m a unit),
    # in plan view: west past the two rooms above, then the tower, a hall that is the one big room
    # (an east wing, a cross, a west wing, stairs down), south down a long corridor, a dark maze,
    # a room with one long bar, a shaft, and the pit of cubes and trains that ends at the winner's
    # chamber. Every turn in it is a left turn but the hall's first.
    # 4. The exit door (a ram that strikes across the corridor) and the corridor to the tower.
    #    Changed: the original's door opens on a timer for a button; a ram on a period is the same wait.
    c.deck(3.0, width=2.6)
    c.checkpoint(2.6, back=1.0)
    c.pusher_alley(width=2.6, count=1, period=3.0, reach=2.4)
    c.deck(5.8, width=2.6)
    # 5. The tower: the original's ladders up its shaft are three bounce pads, the nearest a plain
    #    pad can be to a ladder; the beam out of it is the bridge, and the drop off its end the
    #    hole the original's tunnel floor opens into (a pressure tile that breaks). Left out: the
    #    stub of tunnel past it and the trap room a teleport leads to from there, which sends
    #    a runner back to the start of the same hall: a trap, not a way on, so a race has no
    #    use for it (the teleport piece is used at the end, for the winner's pad).
    c.deck(3)
    c.bouncer_up(rise=3.5)
    c.deck(2)
    c.bouncer_up(rise=3.5)
    c.deck(2)
    c.bouncer_up(rise=3.5)
    c.deck(4)
    c.beam(length=14.0, width=1.6)
    c.gap(5.0, rise=-4.0)
    c.deck(4, width=4.0)
    c.checkpoint(4.0, back=1.2)
    # 6. The hall's east wing: two low bars (hopped), the first three metres in and the second at
    #    seven and a half, then the landing, where the way turns right (north) to the cross.
    z0 = c.z
    c.deck(12.0, width=5.0)
    c.laser((3.0, 0.0), across=5.0, along=0, reach=2.4, period=4.0, duty=0.4, over=c.y, start=z0)
    c.laser((7.5, 0.0), across=5.0, along=0, reach=2.4, period=4.4, duty=0.4, phase=0.5, over=c.y, start=z0)
    c.checkpoint(5.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 7. The cross, a corridor across the hall's middle with two low bars at 4.4 m and 7 m and two
    #    beams to cross between them; then a turn left to the west wing.
    z0 = c.z
    c.deck(12.0, width=4.0)
    c.laser((4.4, 0.0), across=4.0, along=0, reach=2.2, period=4.0, duty=0.4, over=c.y, start=z0)
    c.laser((7.0, 0.0), across=4.0, along=0, reach=2.2, period=4.2, duty=0.4, phase=0.5, over=c.y, start=z0)
    c.beam(length=6.0, width=1.6)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.u_turn(side=1, spacing=14.0, radius=3.0)
    # 8. The west wing: four low bars to hop, then the gate (a ram: the original's gate is shut
    #    except for a window after a button, which is a ram on a long period), then stairs down.
    z0 = c.z
    c.deck(18.0, width=4.0)
    for i, at in enumerate((3.0, 6.5, 10.0, 13.5)):
        c.laser((at, 0.0), across=4.0, along=0, reach=2.2, period=3.8 + 0.3 * i, duty=0.4,
                phase=0.3 * i, over=c.y, start=z0)
    c.checkpoint(4.0, back=1.0)
    c.pusher_alley(width=4.0, count=1, period=5.0, reach=3.0)
    c.deck(2.0, width=4.0)
    c.climb(length=7.04, rise=-1.76, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 9. The south room: the way out is seven metres to the side of the way in, so a ramp-free
    #    shift across (a kink and back) and then the exit corridor.
    c.deck(5.0, width=4.0)
    c.kink(-90.0, width=4.0)
    c.deck(7.0, width=3.0)
    c.kink(90.0, width=3.0)
    c.deck(4.0, width=3.0)
    c.checkpoint(3.0, back=1.0)
    c.deck(8.0, width=2.6)
    # 10. The dark maze: in the original a hurt field of anti-gravity wind, where the way is a
    #     twisting path a few steps wide. Left out: the wind (a deck cannot lift or push a
    #     runner). The path is a snake, 2 m wide, that keeps its turns.
    for k in range(4):
        c.deck(4.0, width=2.0)
        c.kink(90.0, width=2.0)
        c.deck(5.0, width=2.0)
        c.kink(-90.0, width=2.0)
    c.deck(5.0, width=2.0)
    c.checkpoint(2.0, back=1.0)
    c.deck(6.0, width=2.6)
    # 11. Room 9: one bar, very fast, at floor level, sweeping the length of the room (hopped).
    c.deck(3.0, width=8.0)
    c.checkpoint(8.0, back=1.0)
    z0 = c.z
    c.deck(30.0, width=8.0)
    c.laser((6.0, 0.0), across=7.8, along=0, reach=20.0, period=7.0, duty=0.6, over=c.y, start=z0)
    c.deck(3.0, width=8.0)
    c.checkpoint(8.0, back=1.0)
    # 12. The shaft, twelve and a half metres down onto the pit's floor, then a turn east.
    c.deck(2.0, width=8.0)
    c.gap(3.0, rise=-12.5)
    c.deck(5.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.turn(90.0, radius=4.0)
    # 13. The pit: cubes over a floor that kills, hopped one to the next, then the trains
    #     (movers) across the loop between the cube clusters, then the pillars of the east corridor
    #     as stones, the doors that open when shot (rams) and the winner's chamber (the finish).
    #     Changed: the original's way between the north cubes and the south cubes (about 17 m)
    #     is not readable from its entities; the trains are the movers here.
    c.deck(3.0, width=4.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.8), (10.8, -0.6), (14.4, 0.4), (18.0, -0.5), (21.6, 0.0)], size=1.5, until=23.4)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.mover_crossing(length=9.0, size=4.0, period=6.5)
    c.deck(3.0, width=4.0)
    c.mover_crossing(length=9.0, size=4.0, period=6.0, phase=0.3)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.stones([(3.6, 0.0), (7.2, 0.6), (10.8, -0.6), (14.4, 0.4)], size=1.5, until=16.2)
    c.deck(3.0, width=3.0)
    c.checkpoint(3.0, back=1.0)
    c.pusher_alley(width=3.0, count=2, period=3.0, reach=2.0)
    c.deck(3.0, width=3.0)
    # 14. The winner's teleport: the original's last pad sends the winner to a chamber well away
    #     from the pit (30 m beside and 6 m down in the plan view), and that is the finish.
    c.teleport(dx=30.0, dz=0.0, dy=-6.0, width=3.0)
    c.finish()
    return c


def office_course():
    c = Course("wo_office_course", "Office Course",
               "A one-life run through an office block: a choice of ways over a pit, a floor that gives way underfoot, doors that slide shut, vending machines to hop, a laser along a corridor, three ladders (one is the way), a plate floor, a spinning vent, low lasers, a climb and a long jump, and a winner's teleport to the disco.",
               THEMES["peach"], water=-24.0, seconds=480.0)
    c.doc["author"] = "mg office coursee (port)"
    # The rooms follow the original's trap list (its own order, 1 to 12), each placed from the
    # entities in its level file (0.02 m a unit) read in plan view: the start room, a pit south
    # of it, a long run east, a corridor of doors going north past a row of vending machines, a
    # corridor west with one laser, three ladders going south, then the upper floors going west,
    # a vent room, a room of low lasers and the rope cave that ends at the winner's teleport.
    # 1. The start room, then the pit with two breakable platforms (trap 1: choose left or right,
    #    one of the two gives way). Changed: the original's choice is a coin toss; here the left is
    #    stones and the right a plain jump, the faster of the two.
    c.run_out(8)
    c.safe(14.0, width=6.0)

    def by_stones(k):
        k.stones([(3.4, 0.0), (6.8, 0.0)], size=1.5, until=8.5)

    def by_jump(k):
        k.gap(3.2)

    c.fork(by_stones, by_jump, spread=4.0, width=3.5, depth=5.0)
    c.checkpoint(6.0, back=1.2)
    c.turn(90.0, radius=3.0)
    # 2. "Run!" (trap 2): twenty-five metres east over a floor that gives way under the runner.
    #    Changed: the original's floor is one slab that breaks when stepped on; here a field of
    #    tiles that drop out on their own schedule is the nearest thing a stand-in can read.
    c.deck(30.0, width=5.1)
    c.tiles(cols=3, rows=6, tile=1.6, period=3.4, down=0.3, seed=3)
    c.deck(4.0, width=5.1)
    c.checkpoint(5.1, back=1.2)
    c.turn(90.0, radius=3.0)
    # 3. Five sliding doors (trap 3), each striking across the corridor in turn; the corridor runs
    #    north. Changed: the doors are rams on a period, spread a little wider than the original's.
    c.deck(3.0, width=3.2)
    c.pusher_alley(width=3.2, count=5, period=2.8, reach=2.6, step=4.5)
    c.deck(3.0, width=3.2)
    c.checkpoint(3.2, back=1.0)
    # 4. Vending machines to hop (trap 4): stones, higher than the floor, over a pit.
    c.deck(3.0, width=3.2)
    z0 = c.z
    c.stones([(3.4, 0.0), (6.8, 0.7), (10.2, -0.7), (13.6, 0.5), (17.0, 0.0)], size=1.7, until=18.8)
    c.deck(3.0, width=3.2)
    c.checkpoint(3.2, back=1.0)
    c.turn(90.0, radius=3.0)
    # 5. The moving laser (trap 5): one low bar sweeping the length of a corridor going west.
    z0 = c.z
    c.deck(48.0, width=5.1)
    c.laser((38.0, 0.0), across=5.0, along=0, reach=6.0, period=6.0, duty=0.45, over=c.y, start=z0)
    c.deck(8.0, width=5.1)
    c.checkpoint(5.1, back=1.0)
    c.turn(90.0, radius=3.0)
    # 6. The ladders (trap 6, only one of the three kills): three bounce pads, the nearest a plain
    #    pad can be to a ladder.
    c.deck(3.0, width=4.0)
    for _ in range(3):
        c.bouncer_up(rise=2.6)
        c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 7. The invisible floor (trap 7): an ordinary floor here, ten metres west, at the top of the
    #    ladders.
    c.deck(10.0, width=5.1)
    c.checkpoint(5.1, back=1.0)
    # 8. The platforms to choose (trap 8): a field of plates, three across, that drop out in turn.
    c.tiles(cols=3, rows=4, tile=1.8, period=3.2, down=0.3, seed=1)
    c.deck(4.0, width=5.1)
    c.checkpoint(5.1, back=1.0)
    c.turn(90.0, radius=3.0)
    # 9. The spinning vent (trap 9), over a drop to the lower floor.
    c.climb(length=16.0, rise=-4.0, width=6.0)
    c.deck(3.0, width=11.0)
    c.centre_spinner(size=11.0, speed=60.0, height=0.6, arms=2)
    c.deck(3.0, width=11.0)
    c.checkpoint(6.0, back=1.0)
    # 10. The easy lasers (trap 10): four low bars across a corridor, a few metres apart.
    z0 = c.z
    c.deck(16.0, width=4.0)
    for i, at in enumerate((3.0, 6.5, 10.0, 13.5)):
        c.laser((at, 0.0), across=4.0, along=0, reach=2.2, period=3.8 + 0.3 * i, duty=0.4,
                phase=0.3 * i, over=c.y, start=z0)
    c.checkpoint(4.0, back=1.0)
    # 11. The walls to jump around (trap 11): beams past the corners of a wall, a turn between.
    c.deck(3.0, width=4.0)
    c.beam(length=7.0, width=1.6)
    c.deck(2.0, width=4.0)
    c.turn(90.0, radius=3.0)
    c.beam(length=7.0, width=1.6)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 12. The climb and the long jump (trap 12): a pad up, a ledge, and the longest jump in the
    #     course (3.4 m, nearly the most a run clears), the rope cave of the original.
    c.deck(3.0, width=4.0)
    c.bouncer_up(rise=3.0)
    c.deck(3.0, width=4.0)
    c.gap(3.4)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 13. The winner's teleport to the disco: the original's last pad sends the winner to a room
    #     far from the course (about 40 m away and down), and that is the finish. Left out: the
    #     disco's powers, its lasers and its tesla coil, for the next rounds.
    c.deck(3.0, width=3.0)
    c.teleport(dx=24.0, dz=0.0, dy=-6.0, width=3.0)
    c.finish()
    return c


def pauls_course():
    c = Course("wo_pauls_course", "Pauls Mine Course",
               "A very hard one-life course in a mine: carts crossing a lava hall, a memorised path of blocks, falling lava to time, jumping stones, a climb up out of the lava, a room of blocks that blow up, a long spiral fall, two stretches of beams that throw you up and a spiral back to the top.",
               THEMES["dusk"], water=-52.0, seconds=540.0)
    c.doc["author"] = "Paul (port)"
    # The original is one long row of halls from west to east, which is a straight line here, then
    # a shaft down, a long hall back east along the bottom, and a spiral rise. Its own list of ten
    # obstacles is the order; each hall's length is read from its level file (0.02 m a unit) in
    # plan and side view: the top row is 160 m, the bottom row 126 m.
    # 0. The start room and the halls before the first obstacle (a nuke room and a passage).
    c.run_out(8)
    c.safe(30.0, width=6.0)
    c.checkpoint(6.0, back=1.2)
    # 1. The minecarts (obstacle 1): a lava hall 33 m long with three sets of carts crossing it.
    #    Changed: a cart that cannot be touched is a mover crossing, a platform that carries you.
    for i, period in enumerate((6.5, 6.0, 5.5)):
        c.deck(3.0, width=4.0)
        c.mover_crossing(length=9.0, size=4.0, period=period, phase=0.3 * i)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 2. The moving path (obstacle 2): a path of blocks over lava, which the player has to
    #    memorise. Changed: tiles that drop out on their own schedule are the nearest a stand-in
    #    can read; the grid is the original's twenty-six blocks, fifteen metres of them.
    c.deck(3.0, width=5.0)
    c.tiles(cols=3, rows=5, tile=1.8, period=3.4, down=0.25, seed=1)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 3. The lava jump (obstacle 3): three streams of lava fall across the way in turn; "don't
    #    jump too early". The curtains are waterfalls that push the runner off.
    c.waterfalls(count=3, width=4.0, period=3.4, duty=0.4)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 4. The standard jumping stones (obstacle 4).
    c.deck(3.0, width=3.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.7), (10.8, -0.6), (14.4, 0.5), (18.0, 0.0)], size=1.6, until=19.8)
    c.deck(3.0, width=3.0)
    c.checkpoint(3.0, back=1.0)
    # 5. The lava climb (obstacle 5): two towers twelve metres high, climbed before the lava that
    #    rises behind the climber gets there. Left out: the rising lava. The climb is a switchback
    #    of ramps, the last with a belt against the climber, which is the pressure.
    c.deck(3.0, width=4.0)
    c.climb(length=17.0, rise=4.4, width=4.0)
    c.u_turn(side=1, spacing=14.0, radius=3.0)
    c.climb(length=17.0, rise=4.4, width=4.0)
    c.u_turn(side=-1, spacing=14.0, radius=3.0)
    c.conveyor_climb(length=17.0, width=4.0, rise=4.4, speed=2.5)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 6. The room of TNT (obstacle 6): a field of blocks that blow up, five across and three
    #    deep in the original. Changed: tiles that drop out.
    c.tiles(cols=3, rows=4, tile=1.8, period=3.2, down=0.25, seed=1)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 7. The spiral fall (obstacle 7): a shaft with rings to avoid, a hundred and sixty metres
    #    deep. Changed: a spiral of ramps down, two turns, thirty-five metres: the fall is what a
    #    stand-in cannot be asked to survive.
    c.deck(3.0, width=4.0)
    for _ in range(2):
        for _ in range(4):
            c.climb(length=17.0, rise=-4.4, width=4.0)
            c.turn(90.0, radius=3.0)
    c.checkpoint(4.0, back=1.0)
    # 8. The anti-gravity beams, the easy stage (obstacle 8): beams that throw the runner up and
    #    along. Changed: pads that bounce you on to the next.
    c.deck(2.0, width=4.0)
    c.trampolines(count=2, power=10.0)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 9. The insane stage (obstacle 9): the same on narrower pads with stones between.
    c.deck(2.0, width=3.0)
    z0 = c.z
    c.stones([(3.0, 0.0), (6.6, 0.5), (10.2, -0.5), (13.8, 0.4), (17.4, 0.0)], size=1.6, until=19.2)
    c.deck(2.0, width=3.0)
    c.trampolines(count=2, power=10.0)
    c.deck(3.0, width=3.0)
    c.checkpoint(3.0, back=1.0)
    # 10. The spiral rise (obstacle 10): a spiral of ramps up, two turns, to the top.
    c.deck(3.0, width=4.0)
    for _ in range(2):
        for _ in range(4):
            c.climb(length=17.0, rise=4.4, width=4.0)
            c.turn(-90.0, radius=3.0)
    c.deck(3.0, width=4.0)
    c.finish()
    return c


def scary_course():
    c = Course("wo_scary_course", "Scary Course",
               "A haunted house to run in one life: a pit of stones, a collapsing floor, a mover over a hall, a beam over the killer pit, low bars down a corridor, spinning arms, a long room of stones, a turning disc, a long climb, crushing walls, a tile room and the seesaws to the door.",
               THEMES["storm"], water=-30.0, seconds=480.0)
    c.doc["author"] = "mg scary course v2 (port)"
    # No list of rooms came with the original, so the order is the corridors' own, followed in
    # its level file in plan view (0.02 m a unit): the spawn hall, south to a pit and a small
    # collapsing room, east to a big hall and a pit with a bridge, south down a corridor of low
    # bars, west along a hall of spinning arms, north up a long room, west to a turning disc,
    # north up a tall room to the upper floors, east past crushing walls and a room of tiles,
    # then the upper hall back over the spawn hall (kept twelve metres above it) and north to the
    # last big room and the door.
    # 1. The spawn hall, then the passage south.
    c.run_out(6)
    c.safe(8.0, width=6.0)
    c.checkpoint(6.0, back=1.2)
    c.turn(90.0, radius=3.0)
    # 2. The pit room: platforms over a floor that hurts.
    c.deck(6.0, width=3.0)
    c.deck(1.0, width=5.0)
    z0 = c.z
    c.stones([(3.4, 0.0), (6.8, 0.8), (10.2, -0.8), (13.6, 0.4)], size=1.6, until=15.4)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 3. The small room whose floor gives way.
    c.deck(2.0, width=4.0)
    c.tiles(cols=3, rows=3, tile=1.8, period=3.4, down=0.28, seed=1)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # 4. The big hall east, a ride across it, and the bridge over the killer pit.
    c.deck(4.0, width=4.0)
    c.mover_crossing(length=9.0, size=4.0, period=6.5)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.beam(length=10.0, width=1.6)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 5. The corridor of low bars going south. The original has eight, a metre and a third
    #    apart; here four, a fair distance apart.
    z0 = c.z
    c.deck(18.0, width=5.0)
    for i, at in enumerate((3.5, 7.0, 10.5, 14.0)):
        c.laser((at, 0.0), across=5.0, along=0, reach=2.2, period=3.8 + 0.3 * i, duty=0.4,
                phase=0.3 * i, over=c.y, start=z0)
    c.checkpoint(5.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 6. The hall of spinning arms going west: four on poles in the original, two sweepers here.
    c.deck(4.0, width=6.0)
    c.side_sweeper(length=14.0, width=6.0, speed=70.0, arms=2, side=1)
    c.deck(5.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.side_sweeper(length=14.0, width=6.0, speed=65.0, arms=2, phase=0.5, side=-1)
    c.deck(5.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 7. The long room going north: stones over a floor that hurts.
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4), (18.0, -0.3), (21.6, 0.0)], size=1.7,
             until=23.4)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # 8. The turning disc, in a hall going west.
    c.deck(4.0, width=6.0)
    c.turntable(radius=5.0, speed=30.0)
    c.deck(4.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 9. The tall room: a long climb, thirteen metres, up to the upper floors.
    c.deck(3.0, width=5.0)
    c.climb(length=17.0, rise=4.4, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.climb(length=17.0, rise=4.4, width=5.0)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.climb(length=17.0, rise=4.4, width=5.0)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 10. The small rooms of the upper floor: three stones over three hurting floors.
    c.deck(3.0, width=4.0)
    z0 = c.z
    c.stones([(3.4, 0.0), (6.8, 0.6), (10.2, -0.5)], size=1.6, until=12.0)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 11. The hall of crushing walls: four walls moving across it in the original.
    c.pusher_alley(width=5.0, count=4, period=3.0, reach=3.0, step=4.5)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(6.0, width=5.0)
    c.turn(-90.0, radius=3.0)
    # 12. The room of tiles.
    c.deck(3.0, width=5.0)
    c.tiles(cols=3, rows=4, tile=1.8, period=3.2, down=0.28, seed=1)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # 13. The upper hall going east, over the spawn hall: stones over a floor that hurts.
    c.deck(4.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.8), (10.8, -0.8), (14.4, 0.6), (18.0, -0.5), (21.6, 0.0)], size=1.6,
             until=23.4)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # 14. The last big room going north: planks that tip over a floor that hurts, then the door.
    c.deck(4.0, width=5.0)
    c.seesaws(count=3, amplitude=12, period=4.4)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(4.0, width=5.0)
    c.finish()
    return c


def lego_course():
    c = Course("wo_lego_course", "Lego Course",
               "A hard brick-toy course to run in one life: a floor that collapses, a pit of stones, two spinning bars, a ride over a pit, a beam, a hall of tiles, a turning bar, a ride on rails, low bars, doors in the floor, stones, a long ride and the last gate of bars.",
               THEMES["storm"], water=-30.0, seconds=540.0)
    c.doc["author"] = "The_Prodigy (port)"
    # Rooms in the order of the original's corridors, in plan view (0.02 m a unit): the spawn
    # hall in the north-east corner, south to a room of four breakable blocks and a pit, west
    # along the hall of two spinning bars, over a pit on moving platforms, west again over a
    # small room and a long pit to the far end, north to a big floor of tiles, east to a room
    # with a turning bar, on moving rails, then the long way north: low bars, floors that open,
    # a room of stones, a ride on rails and the last gate of bars.
    # 1. The spawn hall, then the passage south.
    c.run_out(6)
    c.safe(8.0, width=6.0)
    c.checkpoint(6.0, back=1.2)
    c.deck(6.0, width=4.0)
    # 2. Four blocks that break under you, then the pit.
    c.tiles(cols=3, rows=4, tile=1.8, period=3.4, down=0.28, seed=1)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4)], size=1.7, until=16.2)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 3. The hall of two spinning bars lying on the floor.
    c.deck(3.0, width=6.0)
    c.side_sweeper(length=14.0, width=6.0, speed=65.0, arms=2, side=1)
    c.deck(4.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.side_sweeper(length=14.0, width=6.0, speed=60.0, arms=2, phase=0.5, side=-1)
    c.deck(4.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    # 4. A platform over the pit.
    c.mover_crossing(length=9.0, size=4.0, period=6.5)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 5. The small room and the long pit at the far end.
    c.beam(length=10.0, width=1.8)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4), (18.0, -0.3)], size=1.7, until=19.8)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 6. North along the end: a big floor of tiles.
    c.deck(4.0, width=5.0)
    c.tiles(cols=3, rows=4, tile=1.8, period=3.2, down=0.28, seed=1)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 7. East: the room with the turning bar over a pit.
    c.deck(4.0, width=6.0)
    c.centre_spinner(size=11.0, speed=60.0, arms=2)
    c.deck(4.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    # 8. The rails: two platforms riding between the pit's edges.
    c.mover_crossing(length=10.0, size=4.0, period=7.0, phase=0.5)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # 9. The long way north. First the lasers over the floor.
    z0 = c.z
    c.deck(18.0, width=5.0)
    for i, at in enumerate((4.0, 8.5, 13.0)):
        c.laser((at, 0.0), across=5.0, along=0, reach=2.2, period=3.8 + 0.3 * i, duty=0.4,
                phase=0.3 * i, over=c.y, start=z0)
    c.checkpoint(5.0, back=1.0)
    # 10. Floors that open under you.
    c.deck(3.0, width=5.0)
    c.tiles(cols=3, rows=4, tile=1.8, period=3.2, down=0.28, seed=1)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 11. A room of stones with a bar through it.
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4), (18.0, -0.3), (21.6, 0.0)], size=1.7,
             until=23.4)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 12. Small rooms: a beam, then the ride on rails.
    c.beam(length=10.0, width=1.8)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.mover_crossing(length=11.0, size=4.0, period=7.5)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 13. The last room: the gate of bars, then the door.
    z0 = c.z
    c.deck(14.0, width=5.0)
    for i, at in enumerate((4.0, 8.0, 12.0)):
        c.laser((at, 0.0), across=5.0, along=0, reach=2.2, period=3.6 + 0.3 * i, duty=0.4,
                phase=0.4 * i, over=c.y, start=z0)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(4.0, width=5.0)
    c.finish()
    return c


def oaks_course():
    c = Course("wo_oaks_course", "Oaks Course",
               "A tall hard course in one life: a climb, moving bars, pillars under a spinning arm, a box ride, ladders, boxes that appear one by one, lasers, a push over the platforms, a tunnel of cars, a stair room, a pair of rolling balls and the last button.",
               THEMES["storm"], water=-30.0, seconds=600.0)
    c.doc["author"] = "ProfessorOak (port)"
    # The original lists twelve levels; this keeps the kinds of obstacle in their order and
    # drops the rest (its respawn gate, the button puzzles and the secrets). Levels 1 to 7 are
    # in its tall tower going down the map's west lane, level 8 is the long tunnel running east
    # (seventy metres of it, so here two halves), and 9 to 12 are in the small tower at the
    # east end. Plan view in the original is a long L, followed here by a left turn out of
    # the lane and a right turn at the far end.
    # Level 1: the climb.
    c.run_out(6)
    c.safe(8.0, width=6.0)
    c.checkpoint(6.0, back=1.2)
    c.climb(length=16.0, rise=4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # Level 2: moving bars to pass.
    c.deck(3.0, width=5.0)
    c.side_sweeper(length=14.0, width=5.0, speed=65.0, arms=2, side=1)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.pusher_alley(width=5.0, count=3, period=3.0, reach=3.0, step=4.5)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # Level 3: pillars, with a spinning arm over them.
    c.deck(4.0, width=6.0)
    c.centre_spinner(size=11.0, speed=55.0, arms=2)
    c.deck(4.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    # Level 4: boxes, then a ride on a moving box.
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4)], size=1.7, until=16.2)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.mover_crossing(length=10.0, size=4.0, period=6.5)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # Level 5: the ladders up.
    c.climb(length=14.0, rise=4.0, width=4.0)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # Level 6: boxes that appear one by one.
    c.deck(3.0, width=5.0)
    c.tiles(cols=3, rows=4, tile=1.8, period=3.2, down=0.28, seed=1)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # Level 7: lasers, a push over the platforms, then the big jump.
    z0 = c.z
    c.deck(15.0, width=5.0)
    for i, at in enumerate((4.0, 8.5, 13.0)):
        c.laser((at, 0.0), across=5.0, along=0, reach=2.2, period=3.8 + 0.3 * i, duty=0.4,
                phase=0.3 * i, over=c.y, start=z0)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.flat_belt(length=12.0, width=4.0, speed=3.0)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.gap(2.6)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # Level 8: the tunnel of cars, in two halves.
    c.deck(10.0, width=5.0)
    c.pusher_alley(width=5.0, count=4, period=3.0, reach=3.0, step=4.5)
    c.deck(6.0, width=5.0)
    c.checkpoint(6.0, back=1.0)
    c.rollers(count=2, speed=60.0)
    c.deck(4.0, width=5.0)
    c.checkpoint(6.0, back=1.0)
    c.pusher_alley(width=5.0, count=4, period=3.2, reach=3.0, step=4.5)
    c.deck(6.0, width=5.0)
    c.checkpoint(6.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # Level 9: the stairs of the tower room.
    c.deck(3.0, width=5.0)
    c.climb(length=17.0, rise=4.4, width=5.0)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # Level 11: the two big balls, as balls to hop across.
    c.balls(count=3, radius=1.5)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # Level 12: the last buttons are the door.
    c.deck(4.0, width=5.0)
    c.finish()
    return c


def dc_course():
    c = Course("wo_dc_course", "Destiny Course",
               "A long one-life course across a map of bare test textures: a spinning bar and a moving one, a pit of stones, drifting posts, low and high bars, rides over pits, a belt, a floor of tiles, a long bunny hop, three levels of spinning bars, three turning discs, a ride, a gauntlet of lasers and the last room of moving posts.",
               THEMES["storm"], water=-30.0, seconds=720.0)
    c.doc["author"] = "Xmortel (port)"
    # The rooms in the order of the original's corridors in plan view (0.02 m a unit): the
    # spawn room in the north-west, south, then east a long way (a pit, drifting posts, low
    # bars, two rides, a teleport up, a belt, tiles and a long hop), south down a tall room
    # (three levels of spinning bars, three discs, a ride and a push), the laser room and the
    # square room of moving posts in the south-east. The original is 260 m across; here the
    # long hall is kept, but its nine bars are four and the push is a belt.
    # 1. The spawn room: a spinning bar, then a bar that slides.
    c.run_out(6)
    c.safe(8.0, width=6.0)
    c.checkpoint(6.0, back=1.2)
    c.side_sweeper(length=14.0, width=6.0, speed=65.0, arms=2, side=1)
    c.deck(5.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.pusher_alley(width=5.0, count=2, period=3.0, reach=3.0, step=4.5)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # 2. The big pit room: stones over a floor that hurts.
    c.deck(4.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4), (18.0, -0.3)], size=1.7, until=19.8)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 3. The drifting posts.
    c.pusher_alley(width=5.0, count=3, period=3.2, reach=3.0, step=4.5)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 4. The corridor of low and high bars.
    z0 = c.z
    c.deck(16.0, width=5.0)
    for i, at in enumerate((4.0, 8.0, 12.0)):
        c.laser((at, 0.0), across=5.0, along=0, reach=2.2, period=3.6 + 0.3 * i, duty=0.4,
                phase=0.4 * i, over=c.y, start=z0)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 5. Two rides over pits.
    c.mover_crossing(length=10.0, size=4.0, period=6.5)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.mover_crossing(length=10.0, size=4.0, period=7.0, phase=0.5)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 6. Up through the teleport, and the belt that pushes.
    c.climb(length=14.0, rise=4.0, width=5.0)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.flat_belt(length=12.0, width=4.0, speed=3.0)
    c.deck(3.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    # 7. The floor of tiles, and the long bunny hop.
    c.deck(3.0, width=5.0)
    c.tiles(cols=3, rows=4, tile=1.8, period=3.2, down=0.28, seed=1)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4), (18.0, -0.3), (21.6, 0.0),
              (25.2, 0.4)], size=1.7, until=27.0)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 8. The tall room: three levels of spinning bars.
    for i in range(3):
        c.deck(4.0, width=6.0)
        c.centre_spinner(size=11.0, speed=55.0 + 5.0 * i, arms=2, phase=0.3 * i)
        c.deck(4.0, width=6.0)
        c.checkpoint(6.0, back=1.0)
    # 9. Three turning discs.
    for i in range(3):
        c.deck(3.0, width=6.0)
        c.turntable(radius=5.0, speed=30.0 + 5.0 * i)
        c.deck(3.0, width=6.0)
        c.checkpoint(6.0, back=1.0)
    # 10. A ride, then the planks that tip over the long room.
    c.mover_crossing(length=10.0, size=4.0, period=6.5)
    c.deck(4.0, width=4.0)
    c.checkpoint(4.0, back=1.0)
    c.seesaws(count=3, amplitude=12, period=4.4)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 11. The room of lasers.
    z0 = c.z
    c.deck(24.0, width=5.0)
    for i, at in enumerate((4.0, 8.0, 12.0, 16.0, 20.0)):
        c.laser((at, 0.0), across=5.0, along=0, reach=2.2, period=3.6 + 0.2 * i, duty=0.4,
                phase=0.4 * i, over=c.y, start=z0)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # 12. The last room: moving posts, then the end.
    c.deck(4.0, width=6.0)
    c.pendulums(width=5.0, count=3, period=3.2, swing=55.0)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(4.0, width=5.0)
    c.finish()
    return c


def waytobar_course():
    c = Course("wo_waytobar_course", "Waytobar Course",
               "Six one-life levels in a row, each its own long room: stones and low bars, a floor that gives way and a spinning bar, drifting posts and a lift, bars and a spinner over deep pits, tiles and a slow floor, and a long hall of pits to the end.",
               THEMES["storm"], water=-30.0, seconds=600.0)
    c.doc["author"] = "BeesCz (port)"
    # Six levels, each a long room of its own, side by side in plan view (0.02 m a unit): the
    # first runs east along the north, the next four are side-by-side halls run south, north,
    # south and north (a teleport joins them in the original; here a u-turn does), and the last
    # is the wide maze above them, run west. The ends are lengthened so the last hall passes the
    # first four far enough off.
    # Level 1: a floor with two stones in it, then eight bars across the hall (four here).
    c.run_out(6)
    c.safe(8.0, width=6.0)
    c.checkpoint(6.0, back=1.2)
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4)], size=1.7, until=12.6)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    z0 = c.z
    c.deck(16.0, width=5.0)
    for i, at in enumerate((4.0, 8.0, 12.0)):
        c.laser((at, 0.0), across=5.0, along=0, reach=2.2, period=3.6 + 0.3 * i, duty=0.4,
                phase=0.4 * i, over=c.y, start=z0)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # Level 2: a floor that gives way, a spinning bar.
    c.deck(4.0, width=5.0)
    c.tiles(cols=3, rows=4, tile=1.8, period=3.2, down=0.28, seed=1)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.centre_spinner(size=11.0, speed=60.0, arms=2)
    c.deck(4.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.deck(28.0, width=5.0)
    c.u_turn(side=1, spacing=18.0, radius=3.0)
    # Level 3: drifting posts, then the lift over the floor that hurts.
    c.deck(4.0, width=5.0)
    c.pusher_alley(width=5.0, count=4, period=3.2, reach=3.0, step=4.5)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.mover_crossing(length=10.0, size=4.0, period=6.5)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(21.0, width=5.0)
    c.u_turn(side=-1, spacing=18.0, radius=3.0)
    # Level 4: bars, then stones over deep pits with a spinning arm.
    c.deck(4.0, width=5.0)
    z0 = c.z
    c.deck(16.0, width=5.0)
    for i, at in enumerate((4.0, 8.0, 12.0)):
        c.laser((at, 0.0), across=5.0, along=0, reach=2.2, period=3.8 + 0.3 * i, duty=0.4,
                phase=0.3 * i, over=c.y, start=z0)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4)], size=1.7, until=16.2)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.centre_spinner(size=11.0, speed=55.0, arms=2, phase=0.3)
    c.deck(4.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.deck(4.0, width=5.0)
    c.u_turn(side=1, spacing=18.0, radius=3.0)
    # Level 5: plates that break, then a slow floor.
    c.deck(3.0, width=5.0)
    c.tiles(cols=3, rows=4, tile=1.8, period=3.2, down=0.28, seed=1)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4), (18.0, -0.3)], size=1.7, until=19.8)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(40.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # Level 6: the wide hall west, a long pit of stones, the belt that pushes, a second pit.
    c.deck(4.0, width=6.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4), (18.0, -0.3)], size=1.7, until=19.8)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.flat_belt(length=12.0, width=4.0, speed=3.0)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4)], size=1.7, until=16.2)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(4.0, width=5.0)
    c.finish()
    return c


def labo_course():
    c = Course("wo_labo_course", "Laboratory Course",
               "A laboratory has had its disaster and you run out through the traps in one life: lasers down a hall, three spinning bars, rams in a corridor, a lift, a long ride, a room of floors that give way, a laser room of stones, spinning bars over pits and a last cage of lasers to the exit.",
               THEMES["mint"], water=-30.0, seconds=600.0)
    c.doc["author"] = "Patator (port)"
    # The order is the original's own list of traps, followed in its level file (0.02 m a unit):
    # the spawn hall south, the laser hall, three spinning bars with a push, the rams and lift
    # columns, the obstacle rooms, a long ride on rails, the laser room, three spinning bars
    # over pits and the cage of lasers at the exit. The two bonus rooms are left out.
    c.run_out(6)
    c.safe(8.0, width=6.0)
    c.checkpoint(6.0, back=1.2)
    # 1. The laser hall: four bars sweeping the hall, one behind another.
    c.deck(18.0, width=5.0)
    z0 = c.z - 18.0
    for i, at in enumerate((3.5, 7.0, 10.5, 14.0)):
        c.laser((at, 0.0), across=5.0, along=0, reach=2.2, period=3.8 + 0.3 * i, duty=0.4,
                phase=0.3 * i, over=c.y, start=z0)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # 2. Three spinning bars in a row, with a push between them in the original.
    c.deck(4.0, width=6.0)
    c.side_sweeper(length=14.0, width=6.0, speed=75.0, arms=2, side=1)
    c.deck(5.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.side_sweeper(length=14.0, width=6.0, speed=70.0, arms=2, phase=0.5, side=-1)
    c.deck(5.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 3. The corridor of rams that close across it.
    c.deck(4.0, width=5.0)
    c.pusher_alley(width=5.0, count=4, period=3.0, reach=3.0, step=4.5)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 4. The lift columns over a deep pit: a ride across.
    c.mover_crossing(length=10.0, size=4.0, period=6.5)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(-90.0, radius=3.0)
    # 5. The obstacle rooms: swinging doors, then jumper pads and a floor that gives way.
    c.deck(4.0, width=5.0)
    c.pendulums(width=4.6, count=2, period=3.2, radius=1.2)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.trampolines(count=2)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.tiles(cols=3, rows=4, tile=1.8, period=3.2, down=0.28, seed=1)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # 6. The long ride on rails, a hall's length, with a plain floor either end.
    c.deck(4.0, width=5.0)
    c.mover_crossing(length=14.0, size=4.0, period=8.0)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    # 7. The laser room: stones over a pit with bars sweeping them.
    c.deck(3.0, width=5.0)
    z0 = c.z
    c.stones([(3.6, 0.0), (7.2, 0.5), (10.8, -0.4), (14.4, 0.4), (18.0, -0.3)], size=1.7, until=19.8)
    for i, at in enumerate((5.4, 12.6)):
        c.laser((at, 0.0), across=3.0, along=0, reach=2.2, period=3.8 + 0.4 * i, duty=0.4,
                phase=0.4 * i, over=c.y, start=z0)
    c.deck(3.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.turn(90.0, radius=3.0)
    # 8. Three spinning bars over pits (the original has them on a row of poles).
    c.deck(4.0, width=6.0)
    c.centre_spinner(size=11.0, speed=60.0, arms=2)
    c.deck(4.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    c.centre_spinner(size=11.0, speed=55.0, arms=2, phase=0.4)
    c.deck(4.0, width=6.0)
    c.checkpoint(6.0, back=1.0)
    # 9. A trail of rollers, then the cage of lasers at the exit.
    c.deck(3.0, width=5.0)
    c.rollers(count=3, speed=60.0)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(14.0, width=5.0)
    z0 = c.z - 14.0
    for i, at in enumerate((3.5, 7.0, 10.5)):
        c.laser((at, 0.0), across=5.0, along=0, reach=2.2, period=3.4 + 0.3 * i, duty=0.45,
                phase=0.35 * i, over=c.y, start=z0)
    c.deck(4.0, width=5.0)
    c.checkpoint(5.0, back=1.0)
    c.deck(4.0, width=5.0)
    c.finish()
    return c


def lily_pond():
    c = Course("wo_lily_pond", "Lily Pond",
               "Round the pond on a winding path: spinning pads to hop across, planks that tip you in, waterfalls, and at the fork the ferry or the pads.",
               THEMES["mint"], seconds=300.0)
    c.run_out(8)
    c.lily_pads(count=4, speed=50)
    c.safe(9)
    c.curve(60, length=12, steps=3)
    c.deck(4)
    c.seesaws(count=2, amplitude=12, period=4.4)
    c.deck(5)
    c.mover_crossing(length=9, period=6.5)
    c.safe(9)
    c.curve(-60, length=12, steps=3)
    c.deck(4)
    c.lily_pads(count=5, speed=50, swing=0.4)
    c.safe(9)
    c.waterfalls(count=3, period=3.4, duty=0.38)
    c.deck(4)
    c.trampolines(count=2)
    c.safe(9)
    c.curve(-90, length=16, steps=4)
    c.deck(4)

    def by_ferry(k):
        k.deck(3)
        k.detour(lambda d: d.mover_crossing(length=10, period=7.5),
                 lambda d: d.seesaws(count=1, amplitude=12, period=4.4), angle=35.0)
        k.deck(3)

    def by_pads(k):
        k.deck(3)
        k.lily_pads(count=6, speed=50, swing=0.4)
        k.deck(3)

    c.fork(by_ferry, by_pads)
    c.safe(9)
    c.seesaws(count=3, amplitude=14, period=4.0)
    c.safe(9)
    c.curve(90, length=16, steps=4)
    c.deck(4)
    c.rollers(count=3, speed=60.0)
    c.deck(4)
    c.side_sweeper(length=13, speed=65, arms=2)
    c.safe(9)
    c.lily_pads(count=4, speed=50, swing=0.4)
    c.deck(4)
    c.gap(2.2)
    c.finish()
    return c.build()


# --- The arenas --------------------------------------------------------------------

def arena(aid, name, blurb, theme, pieces, spawns, drops, gallery, kill=-8.0, toys=()):
    doc = {
        "format": 1, "kind": "arena", "id": aid, "name": name, "author": AUTHOR, "blurb": blurb,
        "theme": theme, "kill_height": kill, "pieces": pieces,
        "spawns": [{"at": v(*at), "size": v(*size)} for at, size in spawns],
        "drops": [{"at": v(*at), "size": v(*size)} for at, size in drops],
        "gallery": {"at": v(*gallery[0]), "size": v(*gallery[1])},
    }
    if toys:
        doc["toys"] = [{"toy": toy, "at": v(*at)} for toy, at in toys]
    return doc


# A finale's balls: a beach ball and a football on the floor, clear of the spawns and the drops,
# for the fighters to shoot about, kick into the water and throw with a barrel's blast. Never
# cover (the combat's trace does not see them) and never a step.
def finale_balls(a, b):
    return (("beach_ball", a), ("football", b))


def box(at, size, role="arena", yaw=0.0):
    return {"kind": "box", "at": v(*at), "size": v(*size), "role": role, "yaw": r(yaw)}


def arenas():
    out = []

    # A round floor (a ring of boxes would be a polygon; a big cylinder is exact) with a slow
    # arm in the middle that sweeps the props as well as the people.
    out.append(arena("wo_arena_ring", "The Ring",
        "A round floor, a slow arm in the middle, and nowhere to hide from it.", THEMES["dusk"],
        [{"kind": "cylinder", "at": v(0, -0.5, 0), "radius": 14.0, "height": 1.0, "role": "arena"},
         {"kind": "spinner", "at": v(0, 0, 0), "arm_length": 9.0, "arm_height": 0.6, "speed": 40.0,
          "arms": 2, "hub_radius": 0.9}],
        [((0, 0, -11), (4, 3)), ((0, 0, 11), (4, 3)), ((-11, 0, 0), (3, 4)), ((11, 0, 0), (3, 4)),
         ((8, 0, 8), (3, 3)), ((-8, 0, -8), (3, 3))],
        [((0, 0, 0), (14, 14))],
        ((0, 6, 20), (16, 5)),
        # Between the spawns, past the arm's reach.
        toys=finale_balls((8, 0, -8), (-8, 0, 8))))

    # Four islands joined by narrow bridges: the bridges are where a thrown crate counts.
    islands = []
    for sx, sz in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        islands.append(box((sx * 9, -0.5, sz * 9), (9, 1, 9)))
    islands += [box((0, -0.5, -9), (9, 1, 2.2)), box((0, -0.5, 9), (9, 1, 2.2)),
                box((-9, -0.5, 0), (2.2, 1, 9)), box((9, -0.5, 0), (2.2, 1, 9))]
    out.append(arena("wo_arena_islands", "Four Islands",
        "Four islands and four narrow bridges. Hold yours, or cross.", THEMES["lagoon"],
        islands,
        [((-9, 0, -9), (4, 4)), ((9, 0, 9), (4, 4)), ((9, 0, -9), (4, 4)), ((-9, 0, 9), (4, 4))],
        [((-9, 0, -9), (6, 6)), ((9, 0, 9), (6, 6)), ((9, 0, -9), (6, 6)), ((-9, 0, 9), (6, 6))],
        ((0, 7, 22), (16, 5)),
        # On two islands' inner corners, beside the bridges.
        toys=finale_balls((-5.5, 0, -5.5), (5.5, 0, 5.5))))

    # A stepped pyramid: high ground in the middle, reached by steps a jump climbs.
    tiers = [box((0, -0.5, 0), (28, 1, 28)), box((0, 0.4, 0), (16, 0.8, 16)),
             box((0, 1.2, 0), (8, 0.8, 8), role="safe")]
    out.append(arena("wo_arena_tiers", "The Steps",
        "A pyramid of three steps. The top is worth having, and everybody can see you on it.",
        THEMES["peach"], tiers,
        [((-11, 0, -11), (4, 4)), ((11, 0, 11), (4, 4)), ((11, 0, -11), (4, 4)),
         ((-11, 0, 11), (4, 4))],
        [((0, 1.6, 0), (6, 6)), ((-10, 0, 0), (4, 12)), ((10, 0, 0), (4, 12))],
        ((0, 7, 22), (16, 5)),
        # On the bottom step, north and south.
        toys=finale_balls((0, 0, -11), (0, 0, 11))))

    # A square with a hole in the middle and two movers that cross it.
    pit = [box((0, -0.5, -10), (26, 1, 6)), box((0, -0.5, 10), (26, 1, 6)),
           box((-10, -0.5, 0), (6, 1, 14)), box((10, -0.5, 0), (6, 1, 14)),
           {"kind": "mover", "from": v(-4.5, -0.4, 0), "to": v(4.5, -0.4, 0), "size": v(3.5, 0.6, 3.5),
            "period": 5.0},
           {"kind": "mover", "from": v(0, -0.4, -4.5), "to": v(0, -0.4, 4.5), "size": v(3.5, 0.6, 3.5),
            "period": 6.0, "phase": 0.25}]
    out.append(arena("wo_arena_pit", "The Pit",
        "A square round a hole, with two rides across it. Knock somebody in.", THEMES["storm"], pit,
        [((-10, 0, -10), (4, 3)), ((10, 0, 10), (4, 3)), ((10, 0, -10), (4, 3)),
         ((-10, 0, 10), (4, 3))],
        [((0, 0, -10), (18, 4)), ((0, 0, 10), (18, 4)), ((-10, 0, 0), (4, 10)), ((10, 0, 0), (4, 10))],
        ((0, 7, 21), (16, 5)),
        # On the side walks, to knock into the hole.
        toys=finale_balls((-12, 0, 5.5), (12, 0, -5.5))))

    # The whole floor turns.
    out.append(arena("wo_arena_turntable", "Merry-Go-Round",
        "The floor turns, and everything on it goes round with you, crates included.",
        THEMES["mint"],
        [{"kind": "turntable", "at": v(0, -0.3, 0), "radius": 13.0, "thickness": 0.6, "speed": 18.0},
         box((0, 0.5, 0), (2.4, 1.0, 2.4), role="pillar")],
        [((0, 0, -9), (4, 3)), ((0, 0, 9), (4, 3)), ((-9, 0, 0), (3, 4)), ((9, 0, 0), (3, 4))],
        [((0, 0, 0), (12, 12))],
        ((0, 6, 19), (16, 5))))
    # No balls on this one: the floor is moved by writing its transform, which carries a person
    # (mg-wipeout's carry) but not a rigid body, so a ball sat still while the floor turned under
    # it (measured: 0.08 m in half a turn).

    return out


def documents():
    courses = [first_splash(), spin_cycle(), big_balls(), punch_alley(), trapdoor_run(), log_roll(),
               the_sweeper(), uphill_belt(), hammer_gauntlet(), grand_tour(), lily_pond(), dans_course().build(),
               office_course().build(), pauls_course().build(),
               scary_course().build(), lego_course().build(), oaks_course().build(), dc_course().build(), waytobar_course().build(),
               labo_course().build()]
    return courses + arenas()


def main():
    check = "--check" in sys.argv
    os.makedirs(ROOT, exist_ok=True)
    stale = []

    for doc in documents():
        path = os.path.join(ROOT, doc["id"] + ".json")
        text = json.dumps(doc, indent=1, sort_keys=False) + "\n"

        if check:
            old = open(path).read() if os.path.exists(path) else ""
            if old != text:
                stale.append(path)
            continue

        with open(path, "w") as out:
            out.write(text)

    if check:
        if stale:
            print("out of date (run tools/build.py):")
            for path in stale:
                print("  " + os.path.relpath(path))
            return 1
        print("every document is what tools/build.py writes")
        return 0

    print("wrote %d documents to %s" % (len(documents()), os.path.relpath(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
