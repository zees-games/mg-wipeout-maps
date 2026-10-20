# cfg/

A course's own settings: `cfg/<course id>.cfg` is applied by mg-wipeout (the server) when that course is laid out, and put back when the next course is. One `wo_` cvar and its value per line, `//` or `#` for comments; any other cvar is skipped with a WARN, because a courses pack may be anyone's.

A course built for one life (a fall is the end of the round for you, no checkpoint restart, until the round is over) says so with:

```
wo_instant_death 1
```

An operator's own change to a cvar mid-round outranks the file when it is put back. `wo_dans_course.cfg` is the one file here: the other courses all play with checkpoints. A course converted from a classic one-life obstacle-course map gets its own.
