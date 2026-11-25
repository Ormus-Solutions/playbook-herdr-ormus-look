# The Ormus look for Herdr: the playbook

This file is written for a coding agent (Claude Code, Codex, Grok) and is
readable by a person. Do the steps in order. Each step is one action, a
"Verify:" command and the result to expect. Stop at the first result that
does not match and report what you saw.

Agents: steps 1 to 4 change nothing outside this repo and the config folder
`~/.config/herdr-ormus-look`. Steps 5 to 7 change the person's Herdr home and
window: ask before each of them, and never start, stop or signal the Herdr
app yourself.

## Goal

The Herdr desktop app shows the Ormus look: the layout, seven themes, the
header, Needs you / Overview / Flock, Search all terminals, a name and a
Spotlight button per pane, and a logo or accent tile per space that the
person lists. Every other Herdr file stays as it was. One command undoes it.

## Before you start

The Herdr home is the folder the desktop app keeps its files in:
`$HERDR_APP_HOME` when that is set, else `~/.config/herdr-app`. The commands
below spell it out in full, because an agent's shell may not keep variables
from one command to the next. On macOS the folder may be elsewhere: ask the
person, and pass it with `--home`.

| Need | Check | Expected | If it fails |
|---|---|---|---|
| Python 3.11 or newer | `python3 -c 'import sys; print(sys.version_info >= (3, 11))'` | `True` | install a newer Python from python.org or your package manager |
| git | `git --version` | a version line | install git |
| The Herdr desktop app's command line | `command -v herdr-app` | a path | install the desktop app with the install script from herdr.dev. The terminal app `herdr` has no mods, so this look cannot work with it |
| A Herdr home with Herdr's own mods in it | `test -f ~/.config/herdr-app/mods/pane/main.js && echo ok` | `ok` | start the desktop app once (it writes its mods on every start), or pass `--home` |
| herdr-core | `command -v hc` | a path | it comes with the app; without it Needs you and Search cannot read terminals |
| node (optional) | `node --version` | a version line | nothing to do: four tests are skipped without it |

## Steps

### 1. Run the demo on the synthetic data

This installs into a temporary copy of a made-up Herdr home
(`examples/herdr-home`), undoes it, and checks the copy is back as it was.
Nothing on your machine changes.

```bash
bash examples/run.sh
```

Verify: `bash examples/run.sh | diff - examples/expected-output.txt && echo same`
Expected: `same`

### 2. Make your config folder

The config is a `spaces.json` with a `logos/` folder next to it. Start from
the example, so the next step has something to check.

```bash
mkdir -p ~/.config/herdr-ormus-look/logos
cp -n examples/spaces.json ~/.config/herdr-ormus-look/spaces.json
cp -n examples/logos/*.svg ~/.config/herdr-ormus-look/logos/
```

Verify: `python3 src/ormus_look.py preview --config ~/.config/herdr-ormus-look/spaces.json | head -1`
Expected: a line that starts with `Space tiles from` and names your config file

### 3. Put the person's spaces in the config

Ask the person which spaces get which logo, accent or letter, and where the
logo files are. Get the space names with `herdr-app ls` and copy them exactly.
An entry is `{ "logo": "file.svg" }` (add `"bg": "#1d2b4f"` for a logo that
needs a color behind it and `"pad": 3` for its margin in px), or
`{ "accent": "teal", "letter": "D" }`. Accents: `rose`, `teal`, `leaf`,
`ember`, `sky`, `iris`. Put the logo files in
`~/.config/herdr-ormus-look/logos/`. Remove the made-up example spaces.

Verify: `python3 src/ormus_look.py preview --config ~/.config/herdr-ormus-look/spaces.json | tail -3`
Expected: one line per space the person listed, each with the tile it gets, then the `any other space` line

### 4. Check the patch fits, writing nothing

This reads Herdr's `spaces`, `picker` and `pane` mods from the home and builds
everything in memory. If Herdr moved the code an edit looks for, it stops here
and says which anchor (see "When Herdr moves the code").

```bash
python3 src/ormus_look.py check --config ~/.config/herdr-ormus-look/spaces.json --home ~/.config/herdr-app
```

Verify: the command above
Expected: `check: the patch fits Herdr's mods in ...; install would write N files`

### 5. Install

Ask first. This writes `layouts/ormus.*`, `themes/ormus-*.json` and
`mods/ormus-*/` in the Herdr home, sets Claude's icon in `programs.json`, and
(unless `--no-keys`) rebinds the picker keys in `keys.json` and adds the
Ormus keys where the person has not bound them. Each of the two files keeps a
backup, `<file>.bak-pre-ormus`. The command prints each key it left out.

```bash
python3 src/ormus_look.py install --config ~/.config/herdr-ormus-look/spaces.json --home ~/.config/herdr-app
```

Verify: `test -f ~/.config/herdr-app/.ormus-look.json && ls ~/.config/herdr-app/mods | grep -c '^ormus-'`
Expected: `7`

### 6. Let Herdr check each mod

Ask first. This only reads.

```bash
for m in ormus-chrome ormus-spaces ormus-picker ormus-pane ormus-needs ormus-search ormus-cards; do herdr-app check ~/.config/herdr-app/mods/$m; done
```

Verify: the loop above
Expected: no error from any of the seven. If one fails, stop and report its message: do not switch the layout

### 7. Switch the window to the look

Ask first. This changes the open window, and the person can go back with
`ctrl-shift-l` or the undo command below.

```bash
herdr-app do layout.switch '{"name":"ormus"}'
herdr-app do app.theme '{"name":"ormus-gold"}'
```

Verify: `herdr-app status`
Expected: the app answers (it does not need to name the layout); then ask the person whether the sidebar shows the Ormus header, Needs you and Overview, and the tiles they set

## Adapt it

| Setting | Where | Example |
|---|---|---|
| Space logos, accents, letters | `~/.config/herdr-ormus-look/spaces.json`, key `spaces`; run `install` again | `"docs": { "accent": "teal", "letter": "D" }` |
| The separator in space names | the same file, key `separator` | `" · "` (a space named `acme · WEB` shows W) |
| Another theme | `herdr-app do app.theme` | `{"name":"ormus-violet"}` |
| The colors | `themes/ormus-gold.json`; copy the file and rename it for a new theme | `"chrome": "#14213d"` |
| The header mark | `mods/ormus-chrome/ormus-mark.svg` (one color, drawn in the text color) | your own SVG with the same name |
| Name a pane | `hc label <terminal> ormus.title="Fix login test"` (an empty value clears it) | in the pane's terminal |
| A Spotlight button on a pane | `hc label <terminal> 'ormus.spotlight=["python3", "/path/to/focus.py", "t1"]'` | a command as a JSON list; it runs on the pane's machine |
| Where the config is | `--config PATH` | `--config ./my-spaces.json` |
| The Herdr home | `--home DIR` or `HERDR_APP_HOME` | `--home ~/.config/herdr-app` |

## When Herdr moves the code

`install` and `check` stop with `the Herdr anchor for X is gone or not unique`
and write nothing. The anchors are the exact lines in `src/space_tiles.py`
(`GPUI_IMPORT`, `UPSTREAM_MARK`, `SPACES_TILE`, `PICKER_TILE`) and in
`patch_pane()` of `src/pane_head.py`. To move one: open your copy of the mod
named in the message (`~/.config/herdr-app/mods/spaces/main.js`, `picker` or
`pane`), find the line that now does the same thing, copy it into the
anchor, run `python3 -m unittest discover -s tests`, and run `check` again.
The stand-ins in `examples/herdr-home/mods/` must carry the new line too, or
a test says so.

## Done when

- `./check.sh` prints `check: ok`.
- `python3 src/ormus_look.py check ...` prints `check: the patch fits ...`.
- `herdr-app check` passes for each of the seven `ormus-*` mods.
- The person sees the Ormus header, the Needs you and Overview rows, and the
  tiles they set, in the sidebar and in the Go to picker (`ctrl-shift-k` on
  Linux and Windows, `cmd-p` on macOS).

## Undo

1. Switch the window back: `herdr-app do layout.switch '{"name":"main"}'`.
2. `python3 src/ormus_look.py undo --home ~/.config/herdr-app` removes
   everything `install` wrote: the layout, the themes, the seven mod folders
   and the manifest `.ormus-look.json`. It restores `programs.json` and
   `keys.json` from their `.bak-pre-ormus` copies when they are as install
   left them. When you changed one after install, it keeps your file and says
   so; the copy from before install stays next to it.
3. Delete `~/.config/herdr-ormus-look` if you no longer want your config.

## Safety

- Reads: Herdr's own `spaces`, `picker` and `pane` mods in the Herdr home, the
  existing `programs.json` and `keys.json`, and the config folder.
- Writes: only `layouts/ormus.*`, `themes/ormus-*.json` and `mods/ormus-*/` in
  the Herdr home, `programs.json` (Claude's icon and tint only), `keys.json`
  (the picker keys and four Ormus keys, with a backup of each), and the
  manifest `.ormus-look.json`. It stops, writing nothing, when one of those
  names already exists and was not made by this tool.
- Never: edits Herdr's own mods, starts, stops or switches the app (it prints
  the commands), sends anything over the network, or reads files outside the
  Herdr home and the config folder. The Needs you dialog types into an agent
  only on the person's own button press, after it read the screen again.
