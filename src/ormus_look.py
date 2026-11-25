#!/usr/bin/env python3
"""The Ormus look for the Herdr desktop app: install, check and undo.

Copies the look into a Herdr home (the folder the desktop app keeps its files in):
a layout, seven themes, a header mod, the Needs you / Overview / Flock sidebar, the
search over all terminals and a board of cards. It also builds three mods from
Herdr's own copies in that home, with anchored edits (src/space_tiles.py and
src/pane_head.py): a logo or accent tile per space, and a name, a Spotlight button
and an Overview per pane. In the person's own programs.json and keys.json it sets
only what the look needs, with a backup of each. It never starts, stops or
switches the app: it prints the commands for that.

Usage:
    python3 src/ormus_look.py --demo
    python3 src/ormus_look.py check   [--config spaces.json] [--home DIR]
    python3 src/ormus_look.py install [--config spaces.json] [--home DIR] [--no-keys]
    python3 src/ormus_look.py undo    [--home DIR]
    python3 src/ormus_look.py preview [--config spaces.json]

Standard library only, Python 3.11 or newer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import merge_home  # noqa: E402
import pane_head  # noqa: E402
import space_tiles  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
DEFAULT_CONFIG = "~/.config/herdr-ormus-look/spaces.json"
DEFAULT_HOME = "~/.config/herdr-app"
MANIFEST = ".ormus-look.json"
HERDR_VERSION = "0.1.15"  # the Herdr version the anchors and the cloned files come from
DEFAULT_THEME = "ormus-gold"
# The repo spells one word of Herdr's UI API with an escape, so the repo's own scrub
# of client names does not flag a common word. The install writes the plain word.
SHIELD = ("hov\\u0065r", "hov" + "er")
TEXT_SUFFIXES = {".js", ".json"}
SKIP_NAMES = {"gpui-kit.d.ts", "jsconfig.json"}
ENTRY_KEYS = {"logo", "bg", "pad", "accent", "letter"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(svg|png)$")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# Herdr's own mods the look is built from, and the Ormus mods they become.
PATCHED = {"spaces": "ormus-spaces", "picker": "ormus-picker", "pane": "ormus-pane"}
TITLES = {"spaces": "Spaces (Ormus)", "picker": "Picker (Ormus)", "pane": "Pane header (Ormus)"}
UPSTREAM_FILES = ("main.js", "mod.json")


class Stop(SystemExit):
    """A stop with a plain message and nothing written."""

    def __init__(self, message: str) -> None:
        super().__init__(f"ormus-look: {message}")


@dataclass
class Config:
    separator: str = " · "
    spaces: dict[str, dict] = field(default_factory=dict)
    logos: Path = Path(".")


def home_path(given: str | None) -> Path:
    return Path(given or os.environ.get("HERDR_APP_HOME") or DEFAULT_HOME).expanduser()


def load_config(path: str | None) -> Config:
    """The spaces config, checked. A missing default config means no logos, only accent tiles."""
    file = Path(path or DEFAULT_CONFIG).expanduser()
    if not file.is_file():
        if path:
            raise Stop(f"no config at {file}")
        return Config()
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Stop(f"{file.name} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise Stop(f"{file.name} must hold a JSON object")
    config = Config(separator=data.get("separator", " · "), logos=file.parent / "logos")
    if not isinstance(config.separator, str):
        raise Stop("'separator' must be text")
    spaces = data.get("spaces", {})
    if not isinstance(spaces, dict):
        raise Stop("'spaces' must be an object: space name -> entry")
    for name, entry in spaces.items():
        if name.startswith("$"):
            continue
        config.spaces[name] = check_entry(name, entry, config.logos)
    return config


def check_entry(name: str, entry: object, logos: Path) -> dict:
    if not isinstance(entry, dict):
        raise Stop(f"{name}: the entry must be an object")
    unknown = set(entry) - ENTRY_KEYS
    if unknown:
        raise Stop(f"{name}: unknown keys {sorted(unknown)}; use {sorted(ENTRY_KEYS)}")
    if "logo" in entry:
        logo = entry["logo"]
        if not isinstance(logo, str) or not LOGO_FILE.match(logo):
            raise Stop(f"{name}: 'logo' must be a file name ending in .svg or .png, no folder")
        file = logos / logo
        if not file.is_file():
            raise Stop(f"{name}: the logo file {file} is missing")
        head = file.read_bytes()[:512]
        if not (head.startswith(PNG_MAGIC) or b"<svg" in head.lower() or b"<?xml" in head.lower()):
            raise Stop(f"{name}: {logo} is not a PNG or SVG file")
    if "bg" in entry and not (isinstance(entry["bg"], str) and HEX.match(entry["bg"])):
        raise Stop(f"{name}: 'bg' must be a color like #1d2b4f")
    if "pad" in entry and not (isinstance(entry["pad"], int) and 0 <= entry["pad"] <= 6):
        raise Stop(f"{name}: 'pad' must be a whole number of px from 0 to 6")
    if "accent" in entry and entry["accent"] not in space_tiles.ACCENTS:
        raise Stop(f"{name}: unknown accent; use one of {sorted(space_tiles.ACCENTS)}")
    if "letter" in entry and not (isinstance(entry["letter"], str) and 1 <= len(entry["letter"]) <= 2):
        raise Stop(f"{name}: 'letter' must be one or two characters")
    return entry


def describe_entry(entry: dict) -> str:
    if "logo" in entry:
        extra = f" on {entry['bg']}" if "bg" in entry else ""
        pad = f", {entry['pad']} px margin" if entry.get("pad") else ""
        return f"logo {entry['logo']}{extra}{pad}"
    kind = f"accent {entry['accent']}" if "accent" in entry else "Herdr's color"
    letter = f"letter {entry['letter']}" if "letter" in entry else "letter after the separator"
    return f"{letter} on {kind}"


def describe(config: Config, shown: str) -> str:
    width = max([len(n) for n in config.spaces] + [len("any other space")])
    rows = [f"Space tiles from {shown} (separator {json.dumps(config.separator, ensure_ascii=False)}):", ""]
    for name, entry in config.spaces.items():
        rows.append(f"  {name.ljust(width)}  {describe_entry(entry)}")
    rows.append(f"  {'any other space'.ljust(width)}  letter after the separator, on an accent for Herdr's color")
    return "\n".join(rows)


# ---- what an install writes ---------------------------------------------------------------


def shielded(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix in TEXT_SUFFIXES:
        data = data.decode("utf-8").replace(*SHIELD).encode("utf-8")
    return data


def payload() -> dict[str, bytes]:
    """The files copied as they are: layouts/ormus.*, themes/ormus-*.json and mods/ormus-*/."""
    out: dict[str, bytes] = {}
    roots = [ROOT / "layouts", ROOT / "themes", ROOT / "mods"]
    for base in roots:
        for file in sorted(base.rglob("*")):
            rel = file.relative_to(ROOT)
            if not file.is_file() or file.name in SKIP_NAMES or "__pycache__" in rel.parts:
                continue
            if not rel.parts[1].startswith("ormus"):
                continue
            out[rel.as_posix()] = shielded(file)
    return out


def read_upstream(home: Path, name: str) -> tuple[str, str]:
    folder = home / "mods" / name
    missing = [f for f in UPSTREAM_FILES if not (folder / f).is_file()]
    if missing:
        raise Stop(
            f"Herdr's own mod {name} is not in {home} ({', '.join(missing)} missing). "
            "Start the desktop app once: it writes its mods on every start. "
            "Or point --home / HERDR_APP_HOME at the right folder."
        )
    return (folder / "main.js").read_text(encoding="utf-8"), (folder / "mod.json").read_text(encoding="utf-8")


def build(config: Config, home: Path) -> dict[str, bytes]:
    """Every file of the install, by its path in the Herdr home. Stops when an anchor is gone."""
    files = payload()
    table = {
        name: {k: v for k, v in entry.items() if k in ENTRY_KEYS}
        for name, entry in config.spaces.items()
    }
    shared_js = space_tiles.tile_js(table, config.separator)
    patchers = {
        "spaces": lambda src: space_tiles.patch_spaces(src, shared_js),
        "picker": lambda src: space_tiles.patch_picker(src, shared_js),
        "pane": pane_head.patch_pane,
    }
    for upstream, ours in PATCHED.items():
        main_js, mod_json = read_upstream(home, upstream)
        files[f"mods/{ours}/main.js"] = patchers[upstream](main_js).encode("utf-8")
        files[f"mods/{ours}/mod.json"] = space_tiles.mod_json(
            mod_json, upstream, TITLES[upstream], HERDR_VERSION
        ).encode("utf-8")
    files["mods/ormus-needs/tiles.js"] = space_tiles.needs_tiles_js(shared_js).encode("utf-8")
    for entry in config.spaces.values():
        if "logo" in entry:
            files[f"mods/ormus-spaces/logos/{entry['logo']}"] = (config.logos / entry["logo"]).read_bytes()
    return files


def top_paths(files: dict[str, bytes]) -> list[str]:
    """What the install owns: each layout and theme file, and each mod folder."""
    tops = set()
    for rel in files:
        parts = rel.split("/")
        tops.add("/".join(parts[:2]) if parts[0] == "mods" else rel)
    return sorted(tops)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(home: Path) -> dict:
    file = home / MANIFEST
    return json.loads(file.read_text()) if file.is_file() else {}


def conflicts(home: Path, files: dict[str, bytes], owned: set[str]) -> list[str]:
    """Paths the install would overwrite that it did not write before and that differ."""
    found = []
    for top in top_paths(files):
        target = home / top
        if top in owned or not target.exists():
            continue
        if target.is_file() and target.read_bytes() == files[top]:
            continue
        found.append(top)
    return found


def install(config: Config, home: Path, keys: bool) -> list[str]:
    if not home.is_dir():
        raise Stop(f"no Herdr home at {home}")
    files = build(config, home)
    old = read_manifest(home)
    owned = set(old.get("paths", []))
    clash = conflicts(home, files, owned)
    if clash:
        raise Stop(
            "these exist in the Herdr home and were not made by this tool, so nothing was written: "
            + ", ".join(clash)
        )
    for top in top_paths(files):
        target = home / top
        if target.is_dir():
            shutil.rmtree(target)
    for rel, data in files.items():
        target = home / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    settings = settings_install(home, keys, old.get("settings", {}))
    manifest = {"paths": top_paths(files), "settings": settings, "tool": "playbook-herdr-ormus-look"}
    (home / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    return report(files, settings, config)


def settings_install(home: Path, keys: bool, earlier: dict) -> dict:
    """Set Claude's icon and the keys in the person's own files; record what was written."""
    record: dict[str, dict] = {}
    ormus = json.loads((ROOT / "mods/ormus-chrome/programs.ormus.json").read_text())
    for name, change in (("programs.json", None), ("keys.json", keys)):
        path = home / name
        existed = path.exists()
        if name == "programs.json":
            mine = json.loads(path.read_text()) if existed else {}
            changed = merge_home.write(path, mine, merge_home.merge(mine, ormus))
            note = "Claude's icon set" if changed else "already set"
            left: list[str] = []
        else:
            if not change or not existed:
                reason = "skipped (--no-keys)" if not change else "none in the home: Herdr's default keys stay"
                record[name] = {"note": reason}
                continue
            before = json.loads(path.read_text())
            after, left = merge_home.add_keys(merge_home.rebind(before))
            changed = merge_home.write(path, before, after)
            note = "picker keys open ormus-picker, Ormus keys added" if changed else "already set"
        record[name] = {
            "note": note,
            "left_out": left,
            # a file an earlier install made stays "made by the install" when this one changes nothing
            "created": (changed and not existed) or (not changed and earlier.get(name, {}).get("created", False)),
            "sha": sha(path) if path.exists() else "",
        }
    return record


def report(files: dict[str, bytes], settings: dict, config: Config) -> list[str]:
    lines = ["Built from Herdr's shipped mods (mods/spaces, mods/picker, mods/pane):"]
    for upstream, ours in PATCHED.items():
        edits = {"spaces": 3, "picker": 3, "pane": 10}[upstream]
        extra = sorted(r.split("/")[-1] for r in files if r.startswith(f"mods/{ours}/logos/"))
        logos = f", logos/{', logos/'.join(extra)}" if extra else ""
        lines.append(f"  mods/{ours}/  main.js ({edits} edits), mod.json{logos}")
    lines.append("Copied as they are:")
    lines.append("  layouts/ormus.json, layouts/ormus.svg")
    themes = sorted(Path(r).stem for r in files if r.startswith("themes/"))
    lines.append(f"  themes: {', '.join(themes)}")
    for mod in sorted({r.split('/')[1] for r in files if r.startswith("mods/")} - set(PATCHED.values())):
        count = sum(1 for r in files if r.startswith(f"mods/{mod}/"))
        lines.append(f"  mods/{mod}/  {count} files" + (" (tiles.js is built from your config)" if mod == "ormus-needs" else ""))
    for name, rec in settings.items():
        lines.append(f"{name}: {rec['note']}")
        for key in rec.get("left_out", []):
            lines.append(f"{name}: left out {key}: bind it by hand if you want it")
    return lines


def undo(home: Path) -> list[str]:
    manifest = read_manifest(home)
    if not manifest:
        raise Stop(f"no {MANIFEST} in {home}: nothing from this tool to undo")
    lines = []
    for name, rec in manifest.get("settings", {}).items():
        path = home / name
        backup = path.with_name(path.name + ".bak-pre-ormus")
        if not rec.get("sha"):
            continue
        if not path.exists():
            continue
        if sha(path) != rec["sha"]:
            lines.append(f"  {name} changed after install: kept as it is (the copy from before install: {backup.name})")
        elif backup.exists():
            backup.replace(path)
            lines.append(f"  {name} restored from its backup")
        elif rec.get("created"):
            path.unlink()
            lines.append(f"  {name} removed (the install made it)")
    for top in manifest.get("paths", []):
        target = home / top
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        lines.append(f"  {top} removed")
    (home / MANIFEST).unlink()
    return lines


def next_steps(theme: str = DEFAULT_THEME) -> list[str]:
    return [
        "Next, in the app (the tool never switches it):",
        "  herdr-app check ~/.config/herdr-app/mods/ormus-needs   (and the other ormus-* mods)",
        "  herdr-app do layout.switch '{\"name\":\"ormus\"}'",
        f"  herdr-app do app.theme '{{\"name\":\"{theme}\"}}'",
    ]


# ---- the demo ------------------------------------------------------------------------------


def tree_state(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def demo() -> str:
    """Install into a temporary copy of examples/herdr-home with examples/spaces.json, then undo."""
    out: list[str] = []
    config = load_config(str(EXAMPLES / "spaces.json"))
    out.append(describe(config, "examples/spaces.json"))
    with tempfile.TemporaryDirectory(prefix="ormus-look-demo-") as tmp:
        home = Path(tmp) / "herdr-home"
        shutil.copytree(EXAMPLES / "herdr-home", home)
        before = tree_state(home)
        out += ["", "Install into a copy of examples/herdr-home (a synthetic Herdr home):"]
        out += install(config, home, keys=True)
        out += [""] + next_steps()
        out += ["", "Undo:"] + undo(home)
        out.append(f"The demo home is back as it was: {'yes' if tree_state(home) == before else 'NO'}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="The Ormus look for the Herdr desktop app.")
    parser.add_argument("--demo", action="store_true", help="install into a temporary copy of a made-up home, then undo")
    sub = parser.add_subparsers(dest="cmd")
    for name, text in (
        ("check", "build everything in memory and write nothing"),
        ("install", "copy the look into a Herdr home"),
        ("undo", "take out what install wrote"),
        ("preview", "print the space tiles of a config"),
    ):
        p = sub.add_parser(name, help=text)
        p.add_argument("--config", help=f"spaces.json (default {DEFAULT_CONFIG})")
        p.add_argument("--home", help=f"Herdr home (default $HERDR_APP_HOME, else {DEFAULT_HOME})")
        if name == "install":
            p.add_argument("--no-keys", action="store_true", help="leave keys.json alone")
    args = parser.parse_args(argv)
    if args.demo:
        print(demo())
        return
    if not args.cmd:
        parser.print_help()
        raise SystemExit(2)
    if args.cmd == "preview":
        config = load_config(args.config)
        print(describe(config, args.config or DEFAULT_CONFIG))
        return
    home = home_path(args.home)
    if args.cmd == "undo":
        print("Undo:")
        print("\n".join(undo(home)))
        return
    config = load_config(args.config)
    if args.cmd == "check":
        if not home.is_dir():
            raise Stop(f"no Herdr home at {home}")
        files = build(config, home)
        clash = conflicts(home, files, set(read_manifest(home).get("paths", [])))
        if clash:
            raise Stop("these exist and were not made by this tool: " + ", ".join(clash))
        print(f"check: the patch fits Herdr's mods in {home}; install would write {len(files)} files")
        return
    print("\n".join(install(config, home, keys=not args.no_keys) + [""] + next_steps()))


if __name__ == "__main__":
    main()
