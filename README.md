# The Ormus look for Herdr

A midnight-and-gold look for the Herdr desktop app, plus the parts that make many agents easy to run: a "Needs you" list, a bird's-eye Overview, a Flock sidebar, search across every terminal, a name per pane and a logo per space.

## What it is

Herdr's desktop app (`herdr-app`) draws its window from a layout, a theme and small JavaScript mods, all plain files in one folder (its home). This playbook is a set of those files, and an installer that puts them there. The pattern is the same as in its sibling `playbook-herdr-space-logos`: an anchored patch on a copy. Herdr rewrites its own mods on every start, so the installer never edits them. It reads your copies of Herdr's `spaces`, `picker` and `pane` mods, makes a few exact edits, and writes the result as new `ormus-*` mods next to them. Each edit looks for one exact piece of Herdr's code, its anchor. When a Herdr update moves that code, the installer stops and says so, instead of writing a broken mod. That is why it is safe to run again after every update, and why one command undoes it.

What you get:

- **Layout and themes.** Sidebars in midnight `#14213d`, terminals on code-dark cards with 14 px corners, ink text, and gold kept for the one thing to integrate. Seven themes: `ormus-gold` (the default), `ormus-silver`, `ormus-quicksilver`, `ormus-jade`, `ormus-rust`, `ormus-violet`, `ormus-graphite`. Each keeps the same terminal hues and changes the neutrals and the "done" color.
- **Header.** The Ormus mark, "Ormus" in Cormorant Garamond and a dim `/ HERDR` label, in a clone of Herdr's chrome mod. Claude agents show the mark in place of the orange Claude Code icon.
- **Agent states.** Blocked (needs you) is red, working is blue, idle is dim, done (finished, not yet seen) is gold.
- **Needs you, Overview and Flock** (`mods/ormus-needs`). Two rows under the header. Needs you counts the agents that wait for you and the ones that finished while you did not look; its dialog (`ctrl-shift-i`) shows the picked agent's real screen, and when that screen is a Claude Code menu its numbered choices are buttons. Overview (`ctrl-shift-g`) shows every tab of every space as a card, by status or by space. Flock (`ctrl-shift-j`) is a second sidebar: each space with one mark per tab that has an agent.
- **Search all terminals** (`ctrl-shift-s`, `mods/ormus-search`). One query over the screen and history of every terminal in every space. Herdr's own find bar searches only the focused one.
- **A name per pane.** Label a terminal `ormus.title` and its header shows that name.
- **A Spotlight button per pane.** Label a terminal `ormus.spotlight` with a command (a JSON list) and its header gets a button, and a double-click, that runs it. The first pane of a tab with four or more terminals gets an Overview button that opens every terminal of the tab in one grid.
- **A logo or accent tile per space.** A logo by exact space name, or a tile in a brand accent with the letter after the separator (`acme · WEB` shows W, not the A of every acme space). The sidebar, the Flock sidebar and the Go to picker all draw them.
- **A card board** (`mods/ormus-cards`). One card per agent for a pane of a tab (props `source` and `spot`: commands that print the cards as JSON and move an agent into the big pane). Optional: only a layout that uses it needs it.

## What it saved me

I run many agents in many spaces at once. The look answers three questions without opening tabs one by one: which agent waits for me, where did that text appear, and which space is which. I have not timed it, so I give no number. What I can say is what I stopped doing: opening each tab to find the agent that asked a question, and reading eight sidebar tiles that all show the same letter.

## Who it is for

People who run several agents in the Herdr desktop app and want to see their state at a glance, and people who like this midnight and gold look. Skip it if you use only the terminal app `herdr` (no mods, so nothing here applies), or if you run one or two agents: the default look is enough. The layout and the header carry the Ormus brand; to make it yours, change the colors in `themes/` and the mark in `mods/ormus-chrome/ormus-mark.svg`.

## Requirements

| Tool | Version | Check |
|---|---|---|
| Python | 3.11 or newer | `python3 --version` |
| git | any recent version | `git --version` |
| [Herdr](https://herdr.dev) desktop app | 0.1.15 (its mods are where the anchors come from); a newer one works while `check` says the patch fits | `command -v herdr-app` |
| A Herdr home with Herdr's own mods | written by the desktop app on every start | `ls ~/.config/herdr-app/mods/spaces/main.js` |
| herdr-core `hc` | the one that comes with the app; Needs you and Search read terminals with `hc read` | `command -v hc` |
| JetBrains Mono (font) | any; the layout names it for terminals, and it is not included | Linux: `fc-list \| grep -i "JetBrains Mono"` |
| node (optional) | any recent version, for three of the tests | `node --version` |

Inter and Cormorant Garamond are included (SIL Open Font License 1.1, notices next to the files).

### Which systems it works on

- **Linux: this is what is verified.** On Linux the installer, the 30 tests and the demo pass (measured on Linux x86_64). I also built the three patched mods from Herdr 0.1.15's own `spaces`, `picker` and `pane` mods and every installed mod parses as JavaScript (measured with `node --check`). I could not start `herdr-app` on the machine where this was packaged, so `herdr-app check` and the window itself were not run there; PLAYBOOK.md has you run `herdr-app check` on each mod before you switch.
- **macOS: expected to work, untested.** The chrome mod has a macOS branch (traffic lights) and the installer is plain Python with no system calls. I do not know where the desktop app keeps its home on macOS, so I did not hard-code a guess: pass `--home` or set `HERDR_APP_HOME`. The keys are `ctrl-shift-...`; Herdr uses `cmd-p` for its own picker on macOS.
- **Windows: not tested, not claimed.**
- The terminal app `herdr` has no mods: it cannot show any of this.

## Quick start

### Hand it to your agent

```bash
git clone https://github.com/Ormus-Solutions/playbook-herdr-ormus-look
cd playbook-herdr-ormus-look
```

Clone this repo, open your coding agent (Claude Code, Codex, Grok) inside the clone, and paste this:

```text
Read PLAYBOOK.md in this repo and follow it step by step. After each step,
run its "Verify:" command and compare the result with "Expected:". If they
differ, stop and tell me what you saw. Ask me which spaces get which logo,
and where my logo files are. Ask me before any step that changes something
outside this repo and its config folder ~/.config/herdr-ormus-look (my Herdr
home, my Herdr window). When you finish, run the "Done when" checks and show
me their output.
```

### Do it by hand

1. See it work on made-up data: `bash examples/run.sh`.
2. Make your config: `mkdir -p ~/.config/herdr-ormus-look/logos`, then copy `examples/spaces.json` there and the logos you want into `logos/`. Change the space names to yours (`herdr-app ls` lists them).
3. Check it, writing nothing: `python3 src/ormus_look.py check --config ~/.config/herdr-ormus-look/spaces.json`.
4. Install: `python3 src/ormus_look.py install --config ~/.config/herdr-ormus-look/spaces.json`. Add `--no-keys` to leave `keys.json` alone.
5. Check each mod: `herdr-app check ~/.config/herdr-app/mods/ormus-needs` (and `ormus-chrome`, `ormus-spaces`, `ormus-picker`, `ormus-pane`, `ormus-search`, `ormus-cards`).
6. Switch: `herdr-app do layout.switch '{"name":"ormus"}'`, then pick a theme: `herdr-app do app.theme '{"name":"ormus-gold"}'`.

To undo: `herdr-app do layout.switch '{"name":"main"}'`, then `python3 src/ormus_look.py undo`.

## Preview

The output of `bash examples/run.sh`, which installs into a temporary copy of a made-up Herdr home and undoes it:

```text
Space tiles from examples/spaces.json (separator " · "):

  acme · WEB       logo acme.svg
  acme · API       logo acme.svg
  demo-api         logo peak.svg on #1d2b4f, 3 px margin
  lab · DASHBOARD  logo orbit.svg
  ormus            logo ormus-mark.svg on #e0b258, 3 px margin
  docs             letter D on accent teal
  web · STAGING    letter after the separator on accent ember
  any other space  letter after the separator, on an accent for Herdr's color

Install into a copy of examples/herdr-home (a synthetic Herdr home):
Built from Herdr's shipped mods (mods/spaces, mods/picker, mods/pane):
  mods/ormus-spaces/  main.js (3 edits), mod.json, logos/acme.svg, logos/orbit.svg, logos/ormus-mark.svg, logos/peak.svg
  mods/ormus-picker/  main.js (3 edits), mod.json
  mods/ormus-pane/  main.js (10 edits), mod.json
Copied as they are:
  layouts/ormus.json, layouts/ormus.svg
  themes: ormus-gold, ormus-graphite, ormus-jade, ormus-quicksilver, ormus-rust, ormus-silver, ormus-violet
  mods/ormus-cards/  2 files
  mods/ormus-chrome/  39 files
  mods/ormus-needs/  3 files (tiles.js is built from your config)
  mods/ormus-search/  2 files
programs.json: Claude's icon set
keys.json: picker keys open ormus-picker, Ormus keys added

Next, in the app (the tool never switches it):
  herdr-app check ~/.config/herdr-app/mods/ormus-needs   (and the other ormus-* mods)
  herdr-app do layout.switch '{"name":"ormus"}'
  herdr-app do app.theme '{"name":"ormus-gold"}'

Undo:
  programs.json removed (the install made it, nothing else is in it)
  keys.json: the keys install changed or added were put back; your other keys stay
  layouts/ormus.json removed
  layouts/ormus.svg removed
  mods/ormus-cards removed
  mods/ormus-chrome removed
  mods/ormus-needs removed
  mods/ormus-pane removed
  mods/ormus-picker removed
  mods/ormus-search removed
  mods/ormus-spaces removed
  themes/ormus-gold.json removed
  themes/ormus-graphite.json removed
  themes/ormus-jade.json removed
  themes/ormus-quicksilver.json removed
  themes/ormus-rust.json removed
  themes/ormus-silver.json removed
  themes/ormus-violet.json removed
The demo home is back as it was: yes
```

## Watch out

- Logos go by the exact space name. Rename a space and it loses its logo until `spaces.json` has the new name and you run `install` again.
- The patched mods are copies and do not follow Herdr updates. Run `install` again after an update. If Herdr moved the code an edit looks for, `install` stops and writes nothing; PLAYBOOK.md says how to move the anchor.
- `install` edits `keys.json` (and sets Claude's icon in `programs.json`): Herdr's picker keys open the Ormus picker, and four Ormus keys are added where you have not bound them (it prints each one it left out). From then on Herdr treats the file as yours and stops adding its new default keys on upgrades. With `--no-keys`, or when you have no `keys.json`, nothing is bound and `install` prints the lines to add by hand (the table below).
- `undo` reverses only what `install` recorded: the keys it rebound or added and the program fields it set, each only while it still reads as install left it. Everything else you wrote in those two files stays, also what you added between two installs. A copy of each file from before the first install stays as `<file>.bak-pre-ormus` (removed again if the file reads the same as the copy after undo); `undo` never restores a whole file from it.
- Installing again replaces the seven `ormus-*` mod folders, the layout and the themes with fresh copies: keep your own edits to them elsewhere. It stops, writing nothing, when one of those names exists and this tool did not make it.
- Some words in the repo's JavaScript and theme files are spelled with a `\u` escape (a backslash, `u` and four hex digits). It is the same word to Herdr, and the installer writes it plainly. `check.sh` decodes such escapes and runs its checks on the result.
- Needs you types into an agent only when you press a button, and only after it read the screen again and found the same question. Read `mods/ormus-needs/main.js` before you trust any tool that types for you.

## Keys

`install` binds these where you have not bound the key. Add them by hand to `keys.json` when you use `--no-keys` or have no `keys.json`:

| Section | Key | Action |
|---|---|---|
| `global` | `ctrl-shift-s` | `mod.open:ormus-search` (Search all terminals) |
| `layout:ormus` | `ctrl-shift-i` | `ormus-needs.needs` (Needs you) |
| `layout:ormus` | `ctrl-shift-g` | `ormus-needs.overview` (Overview) |
| `layout:ormus` | `ctrl-shift-j` | `ormus-needs.sidebar` (Lists or Flock) |

Also replace `mod.open:picker` with `mod.open:ormus-picker` on any key that opens Herdr's picker, so the Go to picker shows your tiles.

## Files

| Path | What it is |
|---|---|
| `PLAYBOOK.md` | the steps, for an agent or a person |
| `src/ormus_look.py` | the installer: `check`, `install`, `undo`, `preview`, `--demo` |
| `src/space_tiles.py`, `src/pane_head.py` | the anchored edits of Herdr's `spaces`, `picker` and `pane` mods |
| `src/merge_home.py` | sets Claude's icon in `programs.json` and the keys in `keys.json`, keeping everything else |
| `layouts/ormus.json`, `layouts/ormus.svg` | the layout (a clone of Herdr's `main`) and its picture |
| `themes/ormus-*.json` | the seven themes |
| `mods/ormus-chrome/` | the header and footer, the icons, the fonts, `programs.ormus.json` |
| `mods/ormus-needs/`, `mods/ormus-search/`, `mods/ormus-cards/` | Needs you / Overview / Flock, Search all terminals, the card board |
| `examples/spaces.json` | a synthetic config: seven made-up spaces and the Ormus mark |
| `examples/logos/` | three plain generated shapes and the Ormus mark |
| `examples/herdr-home/` | a made-up Herdr home with stand-ins for Herdr's three mods and a keys file |
| `examples/expected-output.txt` | what `bash examples/run.sh` must print |
| `tests/` | offline tests that pin the behaviour on the synthetic data |
| `check.sh` | the one gate: tests, placeholders, scrub. The scrub's client-name check reads your own deny-list (`$PLAYBOOK_DENYLIST`, default `~/.config/playbooks/denylist.txt`); without one it says "deny-list: 0 entries" and skips that check |
| `scripts/scrub.sh` | the scrub check, copied unchanged from playbook-packaging |
| `scripts/decoded_scrub.py` | the scrub on decoded text, run by `check.sh` |
| `NOTICE`, `LICENSE-APACHE-2.0.txt`, `LICENSE-LUCIDE.txt` | what is derived from Herdr, what was changed, Herdr's license, and the icon licenses |
| `CHANGELOG.md` | what changed, newest first |

## Credits

Made by Ormus (Ormus Solutions). The look is the Ormus brand: the midnight and gold colors, Inter, Cormorant Garamond, JetBrains Mono and the Ormus mark are public at brand.ormus.solutions. MIT license for this repo's own code (`LICENSE`). The MIT license does not cover the Ormus mark and wordmark as another brand: you may use them in this look, but not as your own brand.

It builds on [Herdr](https://herdr.dev), which is open source under the Apache License 2.0. `layouts/ormus.json` and `mods/ormus-chrome/main.js` are clones of Herdr 0.1.15's `main` layout and `workspace-chrome` mod with changes, and the patched mods are built from the few lines of Herdr's code copied here as anchors. `NOTICE` lists each derived file and what was changed, as the Apache License asks. Needs you and Overview borrow ideas from [Flockbook](https://github.com/minchenlee/flockbook) (MIT); the code is new. The icons are [Lucide](https://lucide.dev) (ISC, with parts from Feather, MIT; texts in `LICENSE-LUCIDE.txt`). Inter and Cormorant Garamond are under the SIL Open Font License 1.1.

Packaged with
[playbook-packaging](https://github.com/Ormus-Solutions/playbook-packaging),
the playbook that sets how these playbook repos are packaged. MIT license.
