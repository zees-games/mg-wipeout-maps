The courses and arenas for [mg-wipeout](https://github.com/zees-games/mg-wipeout): obstacle courses over open water, and the arenas a final fight is played in. Eleven courses of our own (a minute or two for a good run, five of them in front of a full house), ten converted community courses, and five arenas.

A course or arena is a JSON document, not a scene. The server reads every `.json` file in its course directory and sends the current one to each client when the round begins, so players need no course files. To add one, drop a file in the directory. The format is in [docs/format.md](docs/format.md).

## Using it

[dot-bootstrap](https://github.com/gamespice-platform/bootstrap) clones this repository next to mg-wipeout and links it in as `courses/`. Run `./game.sh` in mg-wipeout and you play these courses. On a server they are delivered as one pack (`wipeout_maps`), which `./game.sh online` and `./game.sh server` build for you.

## Our courses

| Course | What is in it |
| --- | --- |
| `wo_first_splash` (First Splash) | The premiere, in front of a full house: a little of everything round the bay and up the hill |
| `wo_spin_cycle` (Spin Cycle) | Turntables, arms on top of them, spinning pads |
| `wo_big_balls` (Big Balls) | Seven sets of balls round the bay and up the hill, wrecking balls between them, stands |
| `wo_punch_alley` (Punch Alley) | Narrow walkways, rams that strike across them, slime falls |
| `wo_trapdoor_run` (Trapdoor Run) | Floors that drop out, rides across gaps, launch pads, two forks |
| `wo_log_roll` (Log Roll) | Rolling logs and tipping planks over open water |
| `wo_the_sweeper` (The Sweeper) | Low arms to jump, high arms to duck, from both sides, faster every time |
| `wo_uphill_belt` (Uphill Belt) | Two switchbacks of belts, bouncers, falls and hammers, then a spiral to the summit |
| `wo_hammer_gauntlet` (Hammer Gauntlet) | Narrow beams under hammers, wrecking balls and rams |
| `wo_grand_tour` (Grand Tour) | The long one, the season's big night, two forks to gamble on |
| `wo_lily_pond` (Lily Pond) | A winding path round a pond: spinning pads, tipping planks, waterfalls, a ferry fork |

## Arenas

| Arena | What is in it |
| --- | --- |
| `wo_arena_ring` (The Ring) | A round floor with a slow arm in the middle |
| `wo_arena_islands` (Four Islands) | Four islands and four narrow bridges |
| `wo_arena_tiers` (The Steps) | A three-step pyramid; the top is worth having |
| `wo_arena_pit` (The Pit) | A square round a hole, with two rides across it |
| `wo_arena_turntable` (Merry-Go-Round) | The whole floor turns |

## Converted community courses

These are one-life courses imported whole from Source 1 maps through dot-map's BSP importer (`tools/import_world.py`, specs in `tools/imports/`). The geometry, textures and props are the author's own; only the start, finish and one-life rule are added, and the author's movers, doors, lasers, teleports and hurt volumes run as the original's entities say. Dan's Course and Office Course use only their first stage, with our own pieces in place of some traps.

| Course | Author | Source | Licence |
| --- | --- | --- | --- |
| `wo_dans_course` (Dan's Course) | Dan (skybox by shini) | [GameBanana](https://gamebanana.com/mods/127888) | CC BY-NC-ND 4.0 |
| `wo_dc_course` (Destiny Course) | Xmortel (project by HAARDCORE) | [GameBanana](https://gamebanana.com/mods/127896) | CC BY-NC-ND 4.0 |
| `wo_labo_course` (Laboratory Course) | Patator (with Artek and Xmortel, for the Furaxx team) | [GameBanana](https://gamebanana.com/mods/128233) | CC BY-NC-ND 4.0 |
| `wo_lego_course` (Lego Course) | The_Prodigy | [GameBanana](https://gamebanana.com/mods/128253) | CC BY-NC-ND 4.0 |
| `wo_oaks_course` (Oaks Course) | ProfessorOak | [GameBanana](https://gamebanana.com/mods/128401) | CC BY-NC-ND 4.0 |
| `wo_office_course` (Office Course) | Lionheartnl | [GameBanana](https://gamebanana.com/mods/127637) | CC BY-NC-ND 4.0 |
| `wo_pauls_course` (Pauls Mine Course) | Paul_Deagle ([SG]Paul) | [GameBanana](https://gamebanana.com/mods/128438) | CC BY-NC-ND 4.0 |
| `wo_scary_course` (Scary Course) | BeesCz and eamy-dnb | [GameBanana](https://gamebanana.com/mods/128598) | CC BY-NC-ND 4.0 |
| `wo_sweet_course` (Sweet Course) | Nexore | [GameBanana](https://gamebanana.com/mods/658326) | CC BY-NC-ND 4.0 |
| `wo_waytobar_course` (Waytobar Course) | BeesCz | [GameBanana](https://gamebanana.com/mods/128852) | CC BY-NC-ND 4.0 |

Notes: Pauls Mine Course also credits the Nadetrail Deluxe Prefab (the1nonlyevilelmo), a Minecraft texture pack (Cdsand1) and a Nuke prefab (teh_grave). Dan's Course credits its skybox to shini. Sweet Course is a rework of the author's first map, <https://gamebanana.com/mods/128763>. Waytobar's page points to a newer version of the map.

If you made one of these maps and want it removed, open an issue at <https://github.com/zees-games/mg-wipeout-maps/issues> and it goes. See [licence.json](licence.json).

## Building the courses

`tools/build.py` writes the own courses and arenas from a short description per course: a run of sections (a gap, a sweeper, a set of balls, a mover crossing), each of which places its pieces, checkpoint and bot route together. Sections can turn, curve, climb and fork. The builder refuses a checkpoint inside a hazard's reach, a course that crosses itself, and a hazard that reaches another part of the course.

```bash
python3 tools/build.py            # rewrite courses/*.json
python3 tools/build.py --check    # exit 1 if a file differs from the builder's output
```

The JSON is committed and CI runs `--check`. Hand-written and imported documents are fine too: any `.json` file in `courses/` loads.

mg-wipeout's `examples/headless_courses.tscn` plays every course to the finish with a stand-in and every hazard live. A course it cannot finish inside its clock has a missing window somewhere, and the test says where it got to. mg-wipeout's `tools/race_times.tscn` races a field of eight at each difficulty and is what sets each course's length.

## Quality and ongoing improvement

The models, textures, animations, sounds and maps in this pack are improved automatically and recursively by AI agents. [Nightly](https://github.com/gamemann/nightly) keeps a board of improvement items. Agents pick up an item, make the change, render fresh frames and check them with a visual judge. Judge findings become new items, and the loop repeats until the result is production quality. Improvements ship as new pack versions, and the screenshots in this README are re-shot each time. Some assets are still low quality today.

## Licence

MIT, see [LICENSE](LICENSE). The converted courses keep the licences listed above.
