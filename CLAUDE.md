# mg-wipeout-maps

The courses and arenas mg-wipeout plays, as JSON documents. Read `../../CLAUDE.md` and `../mg-wipeout/CLAUDE.md` first: the format is defined and validated by `mg-wipeout/game/wo_course_doc.gd`, built by `wo_course.gd`, and this README is the mapper's copy of it.

**`courses/` is what the game reads**, through a dot-bootstrap link (`mg-wipeout/.gitignore` names it: `# bootstrap-link: mg-wipeout-maps/courses`). The game reads every `.json` there plus one practice course and arena built into it; a refused document is a WARN with the reason, never a server that will not start.

**`tools/build.py` writes every document, and the JSON is committed.** Edit the builder, run it, commit both. `--check` (CI) fails when a committed file differs from what the builder writes, so a hand edit to a built course is caught rather than silently lost; a hand-written course the builder does not produce is fine. Sections place pieces, checkpoints and route points together on a cursor running down −Z of the current **frame** — that is the reason for the builder: moving one gap moves everything after it. `turn`, `curve`, `kink`, `u_turn` and `detour` start a new frame (an origin and a heading) and `build()` carries everything into the world, so a course can wind, switch back and spiral; a course that never turns stays in frame 0 and writes the same bytes as before turns existed. `fork(safe, risky)` lays two branches side by side on lanes and joins them; the document then says `"format": 2`.

## What makes a course finishable, measured

Sized against mg-wipeout's defaults: a 7 m/s run, a 1.25 m jump at 20 m/s², which clears about 4.9 m of flat gap. Gaps here are 3.4 m at the most and steps 0.8 m. **Every number below came from a stand-in failing in `mg-wipeout/tools/trace_course` or `tools/race_times`**, and the builder's own comments say which:

- **Balls 3.6 m apart by default (4.0 m for a hard set), logs 3.4 m, pads 3.6 m with a 1.8 m radius** (top to top): under a full jump, because a jump is cut short in the air and never stretched, and a landing on a ball or a turning log costs speed. Pads turn at 50°/s at the most.
- **A checkpoint is plain deck, near its start** (`safe(9)`: seven metres of run-up), never in a hazard's reach: `build()` refuses one that is, because a restart at the end of a sweeper's arc was knocked in again as it stood up.
- **A run of tops is lined up** (`lead_in`, a point on the line 3.5 m before the edge), and **a stand point is never behind the last point** (`stand`): one half a metre behind was reached at once, and a stand-in ran onto a grid of tiles two rows too far.
- **A centre spinner ends in four metres of plain deck**: its arms reach to 0.3 m from the edge, and the jump after it was taken sideways.
- **Hammers 4.2 m apart, rams 4.5 m**, with the wait point halfway / 2.4 m short: closer, and somebody waiting for the next one is in reach of the one behind.
- **Side sweepers reach just short of the far edge**, and the deck is longer than their sweep, so there is ground to watch from; **centre spinners are walked round 2.9 m in from the edge**, back to the middle 3.4 m before the far edge, so the next jump is taken straight.
- **Pendulums `yaw` 0**, which swings them across the course. `yaw` 90 swings them along it, where they hit a person waiting for them.
- **A belt on a ramp has the ramp's `pitch`.** Flat at the ramp's middle height it is a wall.
- **Every route starts at the middle of the pad's front**: the pad is wider than the run-out after it.
- **The builder refuses a course that runs into itself** (`_check_shape`): two parts of the route under 7 m apart across (at any height under 12) that are 30 m apart along it, or a hazard reaching a part of the route it was not placed on. Switchback legs are 18 m apart (`u_turn(spacing=18)`): a side sweeper's arm reaches 10 m from its line.
- **A spinner on a turntable turns against it** (at least 60°/s apart, refused otherwise): arms turning with the disc sat on a rider and pushed them round, too slowly to hop.
- **The jump onto a turntable with a spinner is on the line round its hub** (1.6 m off the middle): taken down the middle, a stand-in steered sideways in the air at the point beside it and ran off the disc's side.
- **A fork's lanes get a point at their start on the wide deck and 3 m of lane** before the branch's sections, and a `detour` runs 4.5 m after each kink before anything: a diagonal from the middle crossed water, and a jump straight after a kink was taken from a standstill.
- **After a `climb` down, `safe(9)` before tiles or tops**: a runner coming down a ramp could not stop for the first row of tiles or line up for the first ball.
- **Every column of a grid of tiles is clear at least half a second on end** to set off for (`tile_column_windows`, a port of mg-wipeout's `WoCourse.tile_crossing_clear`; `build()` refuses a grid otherwise): a seed can lay a column whose rows come back just as the row before drops, and a field then crossed in one column. Change the seed, not the margin; keep the port's constants in step with the game's.
- **The risky branch of a fork is one that skill wins** (jumps, pads, logs), never tiles: a field crowds onto trapdoors and goes down with them together whatever its preset, and the stand-ins that take the risk most (the hardest) came last.

- **Toys are loose only** (dot-props' balls, pins, barrels, tyres): two beach balls in the start pen's back corners on every course (`START_PEN_TOYS`) and a beach ball and a football on an arena's floor (`finale_balls`), clear of spawns and drops. Never on the course and never a pad or a trampoline, which would be a way past an obstacle; mg-wipeout leaves any other kind out. Not on the turning floor, which carries a person but not a ball. `headless_courses` checks each stands clear and still.

`mg-wipeout/examples/headless_courses.tscn` runs every course with a stand-in that never makes a mistake, every hazard live; a course that newly fails there is a course to fix, or a bot that has found a real hole in its timing. **A course is 55 to 120 seconds for that stand-in** (each way through a fork), and its `course_seconds` (300 to 360) about three runs of a medium field; `mg-wipeout/tools/race_times.tscn` measures a field at every difficulty, and mg-wipeout's [docs/stand-ins.md](../mg-wipeout/docs/stand-ins.md#measured) has the numbers.

## What a level is here, for the nightly quota

A level is **a course or an arena that plays differently from every other**, or a section that changes how one plays. In order of preference, as everywhere in this family:

1. **An existing course rebuilt so it plays the way its blurb says.** Both of the original gaps are closed: The Sweeper has a high arm to duck (`high_sweeper`), and a tile shows red for `TILE_WARN_SECONDS` before it drops.
2. **A new section kind in the builder**, made of existing piece kinds, used in at least one course.
3. **A new course or arena** — only with a blurb that says what makes it different, a stand-in finishing it in `headless_courses`, and a render (`mg-wipeout/tools/shot.sh --view=course --wo-course-ids=<id>`).

A new piece KIND is a game change (`wo_course_doc.gd` and `wo_course.gd`), and a level after that.

## `cfg/`: a course that wants its own rules

`cfg/<course id>.cfg` sets `wo_` cvars while that course is the one being played (mg-wipeout applies it when the course loads and puts back what it changed on the next); see `cfg/README.md`. The classic one-life obstacle courses want `wo_instant_death 1`. The builder neither reads nor writes it, and `build.py --check` ignores it.

## Publishing

**This repository is a pack of its own, mounted on the server alone.** mg-wipeout's `game.yml` names it under `server_dependencies`; a server mounts it at `res://dot_cloud/<owner>/mg-wipeout-maps/<version>/` and the game adds that mount's `courses/` to its catalogue (`WoModule._add_delivered_courses`). It is never in a client's `content.sync`: a client is sent the one document being played. `.github/workflows/release.yml` runs `build.py --check` and then dot-ci's release with `pack: true` (and `server-compat: false`, because there is no code in it to check). In dot-server-deploy it is `content/wipeout_maps/` (`tmc/wipeout_maps`), and `examples/wipeout_client.tscn` is the proof that it arrives: it fails seven checks with the dependency removed.

`project.godot` exists only so dot-ci's release can import this repository and attach the `-pack.zip`; it carries the editor's own header and no comments, because the editor rewrites the file on its first save and a checkout would show it modified.

**A new course reaches servers by a release here and nothing else** — no game release, no shell. A server picks it up at its next install, because `install-games` pins `@latest` when it installs.

**A course with a fork (`"format": 2`) needs mg-wipeout with format 2** (this pass, 2026-10-12): an older game refuses the document with "format is 2" and plays the rest, so release the game before this pack. Turns, curves and climbs need nothing new. **A course with a `fall` needs mg-wipeout from 2026-10-12 on**: an older game refuses it (a piece kind it does not know) and plays the rest. Release the game before this pack. `dressing` and the `bounce` route flag are ignored by an older game, not refused. `toys` is ignored by an older game, not refused. A new tile `seed` needs nothing new from the game; it changes the course's digest, which server and client agree on because the client is sent the document.

**`lily_pads` and Lily Pond (2026-10-08).** A new section of existing pieces: small turntables (`role` hazard) over the water, centre to centre at the balls' 4.0 m, alternate pads turning the other way, nearly in line (0.4 m either side). The first draft zig-zagged 2.2 m across and a stand-in fell 56 times on the first pad, because a jump is barely steered in the air: it landed past the centre and wide, and the bot then hopped back toward the centre it had overshot. So the pads are almost on the line, and their route points carry a new `onward` flag (mg-wipeout reads it): a stand-in that lands past such a point jumps, and runs up, toward the NEXT point instead of back at this one. **Lily Pond** (`wo_lily_pond`, the mint theme): four pads, two seesaws, a ferry, a second set of five pads at 60 degrees a second, a gap and the finish. Since 2026-10-12 the pads are 1.8 m across, 3.6 m apart and turn at 50°/s at most, and Lily Pond is a long course; render it with `--view=course --wo-course-ids=wo_lily_pond`.
