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
- `check.sh` also runs `scripts/decoded_scrub.py`: it decodes every known escape form, repeated up to
  50 levels, and matches the deny-list on the result (it does not cover string concatenation,
  lookalike letters, zero-width characters or base64-style encodings).
- Settings and manifest files with a non-finite number (`Infinity`, `NaN`, `1e400`) are refused
  with a message, and the full 8-byte PNG signature is required for a PNG logo.
- Symlinked `mods/`, `layouts/` and `themes/` folders and symlinked settings files work (writes go
  through the link and keep the file mode); a link that points outside the home is refused.
- A damaged or wrong-shape `.ormus-look.json` stops `install` and `undo` with a plain message that
  names the file; the manifest is written in one step.
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
