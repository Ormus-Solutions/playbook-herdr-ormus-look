# Changelog

Newest first.

## 0.1.1

- `undo` reverses only what `install` changed in `keys.json` and `programs.json`,
  recorded in the manifest, and never restores a whole file from a backup, so later
  edits survive a re-install and an undo.
- `install` and `check` read and type-check both settings files before writing
  anything, and write the manifest first, so a failure never blocks `undo`.
- Without a `keys.json`, or with `--no-keys`, `install` prints the bindings to add by hand.
- The mods load their icons from the copies in `mods/ormus-chrome/`.
- Licenses: Lucide (ISC) and Feather (MIT) texts, Herdr attribution headers, the Inter
  notice as the font carries it.
- `check.sh` also decodes escapes and runs the deny-list on the result.
- `undo` refuses a manifest path that is not one of the look's own files.

## 0.1.0

- First release: the Ormus look for the Herdr desktop app (herdr-app 0.1.15) as a
  playbook: the layout, seven themes, the header mod, Needs you / Overview /
  Flock, Search all terminals, the card board, a name and a Spotlight button
  per pane, and a logo or accent tile per space.
- `src/ormus_look.py`: `check`, `install`, `undo`, `preview` and `--demo`, with the
  Herdr mods patched at install time from the person's own copies (anchored
  edits that stop when Herdr moves the code), and an undo that keeps later
  changes.
- Personal settings were left out of this release; the example spaces are made up.
