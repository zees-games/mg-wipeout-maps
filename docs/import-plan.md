# Importing the other courses

The Office Course (`wo_office_course`) is the pilot, `wo_dans_course` the second: `tools/import_world.py tools/imports/<id>.json` reads a map through dot-map's BSP mesh tool and writes `worlds/<id>.{json,bin}` plus `courses/<id>.json` with a `world` piece, `kill` volumes and the scripted pieces mapped from the source map's movers. The 18 other hand-built courses (everything in `tools/build.py`, 2 of 19 imported) each need the same steps.

## Per course

1. Find the source `.bsp` (the credit and page are already in the README) and write `tools/imports/<id>.json`: name, credit, `start`, `finish`, `checkpoints`, `water_height`, `course_seconds`, and `hidden` (toggled brush doors that are closed in the file) and `attached` (brush models that ride a mover) model numbers.
2. Run the importer and read its list of movers, volumes and teleports it could not map.
3. Lay the route with a bot: a navigation search over the hull floors (a 0.5 m grid, jumps up to about 5 m on the level) gives the points; add `jump`, `onward` and `wait` flags at gaps and ram bands; run `tools/trace_course.tscn` until it finishes.
4. Render a tour and a free-camera look (`tools/shot.sh --view=tour`, `--view=look`), then `./game.sh soak <id> 1`.
5. Remove the course from `tools/build.py` and run `python3 tools/build.py --check`.

## What has no equivalent yet

Pit crossings by water or a hurt plane, ladders (the importer makes bounce pads), climbs, teleports, steam and fan volumes, push volumes, buttons and the secret and disco teleports. A course that depends on one of these is imported as the stages that do not, the rest left as scenery, as the Office Course is. Each needs a new piece kind in mg-wipeout (`game/wo_course_doc.gd`, `game/wo_course.gd`).

## Open items

- Online clients still get the whole maps pack (`maps_delivery: client`), about 20 MB with all 19 imported. mg-wipeout now asks for a course's mesh by group when a stage names a mesh no mounted pack holds (`WoWorld.fetch`), but nothing publishes groups yet: nightly item `wipeout-mesh-groups` (a `groups.json` read by `DotCloudPublisher`, passed through by the site, written here one group per course). dot-server-deploy's `wipeout_client` example still expects `server` delivery.
- The pilot's bot falls about 25 times at the two island jumps before it lands them; the takeoffs want tuning.
- Dan's Course needed no vent bounds or rock-wall rows in dot-map. Its second stage (the hall of stones with two sweeping walls of light) is not finished by the stand-in yet: the zig-zag jumps between stones need run-up tuning in `tools/imports/wo_dans_course.json`, and it stays scenery until then.

## Effort

Per course, one builder session: simple linear courses (spin cycle, big balls, punch alley and similar) half a day each; the large themed maps (Pauls, Oaks, Labo, Sweet, Scary) a day each because of the route and the unmapped mechanisms. Only community maps have a source `.bsp` (under `~/mapsrc/wipeout/`); the eleven courses of our own (first splash to lily pond) have none and stay as built, so the 18 is an upper bound to be counted when the sources are matched to the courses.
