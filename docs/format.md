# Course and arena format

The JSON format a server reads from its course directory. See the [README](../README.md) for the packs.

Every length is metres, every angle degrees, every time seconds. A course may run any way; yaw 0 faces **−Z**, and every piece, checkpoint and the finish take a `yaw`. A position is the **centre** of what it places, except where a field says otherwise. Colours are `[r, g, b]` in 0–1.

```json
{
  "format": 1,
  "kind": "course",
  "id": "wo_my_course",
  "name": "My Course",
  "author": "you",
  "blurb": "One line the server shows at the top of the round.",
  "theme": {"sky": [0.4, 0.66, 0.92], "horizon": [0.8, 0.88, 0.95], "water": [0.12, 0.45, 0.62]},
  "water_height": -6,
  "course_seconds": 240,
  "start": {"at": [0, 0, 0], "size": [10, 8], "yaw": 0},
  "pieces": [ ... ],
  "checkpoints": [{"at": [0, 0, -30], "size": [6, 4, 2.4]}],
  "finish": {"at": [0, 0, -80], "size": [10, 4, 2], "lounge": [0, 0, -84]},
  "route": [ ... ]
}
```

- `start.at` is the **top** of the start pad; the game builds the pad, its side walls and the gate the countdown holds closed across its −Z edge.
- `checkpoints` and `finish` are volumes whose `at` is their **bottom** centre: a runner is through when they stand inside one. Falling in puts a runner back at the last checkpoint they crossed. `lounge` is where finishers wait.
- `water_height` is where falling in starts. `course_seconds` is optional and is capped by the server's `wo_course_seconds`.
- Ids are lowercase `a-z`, `0-9` and `_`. A document a server cannot read is refused with the reason, and every other course still plays: `wo_courses` on the server lists refusals.

### Pieces

Every piece has a `kind`, and may have `yaw` and a `role` (`deck`, `pillar`, `cannon`, `arena`, `hazard`, `safe`), which decides its texture.

**Still**

| kind | fields | |
| --- | --- | --- |
| `box` | `at`, `size` | ground |
| `ramp` | `at`, `size`, `pitch` | a box tilted about its X axis; positive raises its −Z end |
| `ball` | `at`, `radius` | stand only near the top (about 35°) |
| `cylinder` | `at`, `radius`, `height` | upright |

**Carriers:** solid, and whoever stands on one moves with it

| kind | fields | |
| --- | --- | --- |
| `mover` | `from`, `to`, `size`, `period`, `phase` | slides between two centres, eased at both ends |
| `turntable` | `at`, `radius`, `speed`, `thickness`, `phase` | turns at `speed` degrees a second |
| `roller` | `at`, `length`, `radius`, `speed` | a log along its X axis, rolling at `speed` degrees a second |
| `seesaw` | `at`, `size`, `amplitude`, `period`, `phase` | tips about its X axis |
| `conveyor` | `at`, `size`, `speed`, `pitch` | a belt moving whoever is on it along its −Z at `speed` m/s (negative runs back toward the start); `pitch` lays it on a slope |
| `tiles` | `at`, `cols`, `rows`, `tile`, `gap`, `thickness`, `period`, `down`, `seed` | a grid; each tile drops out for `down` of every `period`, each at its own point in the cycle |
| `bouncer` | `at`, `size`, `power` | throws whoever lands on it up at `power` m/s |
| `teleport` | `at`, `size`, `to`, `heading` | a still pad: whoever stands on it is put at `to` (their feet) facing `heading` degrees, and a stand-in carries on from the route point nearest there. The builder's `teleport(dx, dz, dy, angle)` starts the next section at the destination. Needs mg-wipeout from 2026-10-20 on: an older game refuses the document (a piece kind it does not know) and plays the rest |

**Hazards:** not solid; whatever they touch is thrown

| kind | fields | |
| --- | --- | --- |
| `spinner` | `at` (the base of its post), `arm_length`, `speed`, `arms`, `arm_height`, `arm_thickness`, `hub_radius`, `hub_height`, `phase` | arms round a solid post; jump a low one, duck a high one |
| `pendulum` | `pivot`, `length`, `radius`, `swing`, `period`, `phase` | a ball on a rod, swinging `swing` degrees either side along its X axis (yaw 0 swings across a course) |
| `pusher` | `at`, `size`, `reach`, `period`, `duty`, `phase` | a ram that strikes `reach` metres along its −Z, holds for `duty` of its period, and goes home |
| `fall` | `at` (on the deck), `size` (width, height, thickness), `period`, `duty`, `phase`, `push`, `tint` | a curtain of water (or slime, by `tint`) pouring for `duty` of its period after 0.7 s of drips; it throws whoever is under it `push` m/s off along its own +X. Needs mg-wipeout with `fall` (2026-10-12 on) |

`phase` is a fraction of a period (0–1) for anything with a period, and degrees for anything that turns. Everything that moves is a function of time and nothing else, which is what lets every machine agree about where it is without being told.

### The route

The points a stand-in runs through, in order. Each is `{"at": [x, y, z]}` with any of:

- `jump`: jump here (once on the ground); a jump point that is a top to land on is braked toward in the air;
- `wait`: wait here until the way to the next point is clear of every hazard for the time it takes to run it;
- `board`: this is something to land on: wait until it will be there, then run and jump at the edge;
- `ride`: this point is ON something that moves: standing on any carrier reaches it;
- `bounce`: this point is on a bouncer: passing over it in the air reaches it;
- `onward`: a jump point the stand-in may land past; the jump from it aims at the next point;
- `walk`, `reach` (metres, default 1.2);
- `branch` and `risky`: a fork (format 2). The points of each way through carry its number (1, 2…); points without one are the way everybody goes. A fork's points are laid out after the point it starts at, one branch's then the next's, and a stand-in takes the branch marked `risky` (the faster, harder way) by its `wo_bot_risk` and skips the other's points. A course with a fork says `"format": 2`, which an mg-wipeout from before 2026-10-12 refuses (and plays the rest).

### Dressing

Optional, and only ever drawn: a course with none plays the same. Each entry is `{"kind", "at", "size", "yaw", "seed", "text", "tint"}`; a kind the client does not know is skipped.

| kind | |
| --- | --- |
| `stands` | a grandstand full of people; `at` is the middle of its front edge at the first row's height, `size` is length, height, depth, and it faces its own −Z; `text` along the back |
| `banner` | a board on two poles with `text` on both faces |
| `lights` | a light tower, `size.y` tall, its lamps facing −Z |
| `screen` | a big screen facing −Z; it shows `text`, and in a race the leaders |
| `flags` | a row of flags on poles along `size.x` |

### Arenas

```json
{
  "format": 1, "kind": "arena", "id": "wo_arena_mine", "name": "Mine", "author": "you",
  "kill_height": -8,
  "pieces": [ ... ],
  "spawns": [{"at": [-9, 0, -9], "size": [4, 4]}, ... ],
  "drops": [{"at": [0, 0, 0], "size": [12, 12]}],
  "gallery": {"at": [0, 6, 20], "size": [14, 5]}
}
```

`spawns` are the areas a side can be put down in (at least two; give it four or more so the draw of who goes where varies), `drops` where props and weapons land, and `gallery` a walled box where everybody who did not finish watches from. An arena can use any piece a course can.

