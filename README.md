The courses and arenas for [**mg-wipeout**](https://github.com/zees-games/mg-wipeout): obstacle courses over open water, and the arenas a final death is fought in. Eleven courses, each a minute to two for a good run, five of them in front of a full house, and five arenas.

Every course and arena is a **JSON document**, not a scene. A server reads the documents in its course directory and sends the one it is playing to every client as the round begins, so players need no course files at all and a new course is one file dropped into a directory.

## Using it
[dot-bootstrap](https://github.com/modcommunity/dot-bootstrap) clones this repository next to mg-wipeout and links it into the game as `courses/`, so `./game.sh` in mg-wipeout plays these courses with nothing else to do. On a server they are delivered as a pack of their own (`wipeout_maps`), which mg-wipeout's `./game.sh online` and `./game.sh server` build for you.

## The courses

| Course | What it is |
| --- | --- |
| `wo_first_splash` (First Splash) | The premiere, in front of a full house: a little of everything round the bay and up the hill, gently, and then not so gently |
| `wo_spin_cycle` (Spin Cycle) | Turntables, arms that turn on top of them, spinning pads, and a course that turns with them |
| `wo_big_balls` (Big Balls) | Seven sets of balls round the bay and up the hill, bigger and further apart, wrecking balls between them, and the stands |
| `wo_punch_alley` (Punch Alley) | Narrow walkways and rams that strike across them, and slime falls to wait out |
| `wo_trapdoor_run` (Trapdoor Run) | Floors that drop out from under you, rides across the gaps, pads that throw you on, and two forks: the long jumps or the pads straight across, or the long way round on the rides |
| `wo_log_roll` (Log Roll) | Rolling logs and tipping planks over open water. Keep moving or go backwards |
| `wo_the_sweeper` (The Sweeper) | Low arms to jump and high arms to duck, from both sides, round every corner, faster every time, with a crowd |
| `wo_uphill_belt` (Uphill Belt) | Up the hill in two switchbacks of belts, bouncers, falls and hammers, then round a spiral to a finish on the summit |
| `wo_hammer_gauntlet` (Hammer Gauntlet) | Narrow beams under swinging hammers, wrecking balls and rams, up to a high beam and down again, with a crowd |
| `wo_grand_tour` (Grand Tour) | The long one and the season's big night: round the bay and up the hill, a bit of everything, two forks to gamble on |
| `wo_lily_pond` (Lily Pond) | A winding path round the pond: spinning pads, tipping planks, waterfalls, and a fork between the ferry and the pads |
| `wo_dans_course` (Dan's Course) | One life, in outer space: stones over the dark with low bars sweeping them, a tower of bounce pads, a bridge beam, a hall with an east wing, a cross and a west wing of low bars, a winding maze path, a long bar sweeping a room, a shaft drop and a pit of cubes and trains. Ported from Dan's course; see Credits |
| `wo_office_course` (Office Course) | One life, in an office block: a choice of ways over a pit, a floor of tiles that drops out underfoot, doors that strike across a corridor, vending machines to hop, a low laser along a corridor, three bounce-pad ladders, a plate floor, a spinning vent, four low lasers, a climb and a long jump, and the winner's teleport. Ported from "mg office coursee"; see Credits |

| Arena | What it is |
| --- | --- |
| `wo_arena_ring` (The Ring) | A round floor with a slow arm in the middle |
| `wo_arena_islands` (Four Islands) | Four islands and four narrow bridges |
| `wo_arena_tiers` (The Steps) | A three-step pyramid; the top is worth having |
| `wo_arena_pit` (The Pit) | A square round a hole, with two rides across it |
| `wo_arena_turntable` (Merry-Go-Round) | The whole floor turns |

## How they are made

`tools/build.py` writes every document in `courses/` from a short description of each course as a run of **sections** (a gap, a sweeper, a set of balls, a mover crossing), each of which places its pieces, its checkpoint and the route a stand-in follows together. Moving one gap moves everything after it. Sections that bend the course (`turn`, `curve`, `kink`, `u_turn`), change its height (`climb`, and the belts, bouncers and steps that already did) and split it (`fork`, `detour`) carry everything after them round with them, so a course is a winding show rather than a corridor.

```bash
python3 tools/build.py            # rewrite courses/*.json
python3 tools/build.py --check    # exit 1 if a file differs from what the builder writes
```

The JSON is still what the game reads and is committed; CI runs `--check`, so a hand edit to a document the builder does not know about is caught instead of being lost on the next build. Hand-written documents that the builder does not produce are fine too: anything in `courses/` with a `.json` extension is loaded.

Every course is played to the finish by a stand-in in mg-wipeout's `examples/headless_courses.tscn`, with every hazard live. A course it cannot finish inside its own clock is a course with no window somewhere, and the suite says where it got to. mg-wipeout's `tools/race_times.tscn` races a field of eight at every difficulty and is what each course's length is set by.

The builder refuses a checkpoint inside any hazard's reach (a restart into a sweeper's arc), a course that runs into or over itself, and a hazard that reaches another part of the course; `event()` dresses a course for a big night from its route: stands down both sides in turn, light towers, flags at the start and screens at both ends.

## The format

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

## License

MIT. See [LICENSE](LICENSE).

## Credits

**Dan's Course** is the layout of "Dan's Course" by Dan (skybox by shini), https://gamebanana.com/mods/127888, released under CC BY-NC-ND 4.0. Only the sequence of rooms and their obstacles was taken; every piece is built here from our own art and the rooms are approximated, not copied. Changed on purpose: its two teleports (a decoy trap loop and the winner's) are left out or become the finish, the anti-gravity wind of its maze is left out, doors that open on a button or a shot are timed rams, ladders are bounce pads, trains are movers, and the exact way across the lower pit is approximated. Teleports are left out. If you made it and want it removed, say so and the course goes.

**Office Course** is the layout of "mg office coursee" by its author (the file is named `mg_office_coursee`), https://gamebanana.com/mods/127637, released under CC BY-NC-ND 4.0. Only the sequence of rooms and their obstacles was taken (its own trap list, one to twelve); every piece is built here from our own art and the rooms are approximated, not copied. Changed on purpose: sliding doors and the breaking floors are rams and tiles on a period, the invisible floor is a plain one, ladders are bounce pads, the choice of ways at the first pit is a stone path or a jump, the secret rooms and the disco (powers, lasers, tesla coil) are left out, and the winner's teleport becomes the finish. If you made it and want it removed, say so and the course goes.
