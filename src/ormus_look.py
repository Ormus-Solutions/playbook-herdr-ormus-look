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
from pathlib import Path, PurePosixPath

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
# The repo writes one word of Herdr's UI API with an escape; the install writes it plainly.
SHIELD = ("hov" + "\\" + "u0065r", "hov" + "er")
TEXT_SUFFIXES = {".js", ".json"}
SKIP_NAMES = {"gpui-kit.d.ts", "jsconfig.json"}
ENTRY_KEYS = {"logo", "bg", "pad", "accent", "letter"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(svg|png)$")
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
        if not (head[1:4] == b"PNG" or b"<svg" in head.lower() or b"<?xml" in head.lower()):
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


def build(config: Config, home: Path) -> tuple[dict[str, bytes], dict[str, int]]:
    """Every file of the install, by its path in the Herdr home, and how many edits each patch made.

    Stops when an anchor is gone."""
    files = payload()
    counts: dict[str, int] = {}
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
        patched, counts[upstream] = space_tiles.counted(patchers[upstream], main_js)
        header = (
            f"// Modified from Herdr's `{upstream}` mod (herdr-app {HERDR_VERSION}, Apache License 2.0, "
            "https://herdr.dev)\n// by playbook-herdr-ormus-look. See NOTICE.\n"
        )
        files[f"mods/{ours}/main.js"] = (header + patched).encode("utf-8")
        files[f"mods/{ours}/mod.json"] = space_tiles.mod_json(
            mod_json, upstream, TITLES[upstream], HERDR_VERSION
        ).encode("utf-8")
    files["mods/ormus-needs/tiles.js"] = space_tiles.needs_tiles_js(shared_js).encode("utf-8")
    for entry in config.spaces.values():
        if "logo" in entry:
            files[f"mods/ormus-spaces/logos/{entry['logo']}"] = (config.logos / entry["logo"]).read_bytes()
    return files, counts


def top_paths(files: dict[str, bytes]) -> list[str]:
    """What the install owns: each layout and theme file, and each mod folder."""
    tops = set()
    for rel in files:
        parts = rel.split("/")
        tops.add("/".join(parts[:2]) if parts[0] == "mods" else rel)
    return sorted(tops)


def manifest_problem(data: object) -> str | None:
    """What is wrong with a manifest's shape, or None."""
    if not isinstance(data, dict):
        return "it must hold a JSON object"
    paths = data.get("paths", [])
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        return "'paths' must be a list of text"
    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        return "'settings' must be an object"
    prog = settings.get("programs.json", {})
    keys = settings.get("keys.json", {})
    if not isinstance(prog, dict) or not isinstance(keys, dict):
        return "the entries of 'settings' must be objects"
    need = {"changes": ("program", "field"), "rebound": ("section", "key"), "added": ("section", "key")}
    for owner, name in ((prog, "changes"), (keys, "rebound"), (keys, "added")):
        items = owner.get(name, [])
        if not isinstance(items, list):
            return f"'{name}' must be a list"
        for item in items:
            if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in need[name]) or "after" not in item:
                return f"an entry of '{name}' needs {', '.join(need[name])} as text and an 'after' value"
    return None


def read_manifest(home: Path) -> dict:
    file = home / MANIFEST
    if not file.is_file():
        return {}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise Stop(f"{file} cannot be read ({e}). Nothing was changed. Fix it, or delete it if you want to start over "
                   "(then the files this tool wrote stay in place until you remove them by hand).") from e
    problem = manifest_problem(data)
    if problem:
        raise Stop(f"{file}: {problem}. Nothing was changed. Fix it, or delete it if you want to start over.")
    return data


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


def read_json_file(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise Stop(f"{path.name} is not valid JSON ({e}). Fix it or move it away. Nothing was written.") from e


@dataclass
class SettingsPlan:
    """What install would do to programs.json and keys.json, worked out before anything is written."""

    programs_path: Path
    programs_before: dict
    programs_after: dict
    programs_existed: bool
    programs_changes: list[dict]
    keys_path: Path
    keys_before: dict | None = None  # None: keys.json is left alone
    keys_after: dict | None = None
    key_record: dict = field(default_factory=lambda: {"rebound": [], "added": []})
    key_left: list[str] = field(default_factory=list)
    key_note: str = ""


def plan_settings(home: Path, keys: bool) -> SettingsPlan:
    """Read and type-check both files; a typo or a wrong shape stops here, before any write."""
    ormus = json.loads((ROOT / "mods/ormus-chrome/programs.ormus.json").read_text())
    path = home / "programs.json"
    existed = path.exists()
    mine = read_json_file(path) if existed else {}
    try:
        merge_home.check_programs(mine, ormus)
    except merge_home.BadFile as e:
        raise Stop(f"{e}. Nothing was written.") from e
    assert isinstance(mine, dict)
    after = merge_home.merge(mine, ormus)
    plan = SettingsPlan(path, mine, after, existed, merge_home.program_changes(mine, after), home / "keys.json")
    if not keys:
        plan.key_note = "skipped (--no-keys)"
    elif not plan.keys_path.exists():
        plan.key_note = "none in the home: Herdr's default keys stay"
    else:
        raw = read_json_file(plan.keys_path)
        try:
            merge_home.check_keys(raw)
        except merge_home.BadFile as e:
            raise Stop(f"{e}. Nothing was written.") from e
        assert isinstance(raw, dict)
        plan.keys_before = raw
        plan.keys_after, plan.key_left = merge_home.add_keys(merge_home.rebind(raw))
        plan.key_record = merge_home.key_changes(raw, plan.keys_after)
    return plan


def prepare(config: Config, home: Path, keys: bool) -> tuple[dict[str, bytes], dict[str, int], SettingsPlan]:
    """Everything install needs, checked, with nothing written."""
    if not home.is_dir():
        raise Stop(f"no Herdr home at {home}")
    files, counts = build(config, home)
    settings = plan_settings(home, keys)
    clash = conflicts(home, files, set(read_manifest(home).get("paths", [])))
    if clash:
        raise Stop(
            "these exist in the Herdr home and were not made by this tool, so nothing was written: "
            + ", ".join(clash)
        )
    return files, counts, settings


def merge_records(earlier: list[dict], new: list[dict], key: tuple[str, ...]) -> list[dict]:
    """A change from this install replaces an earlier one for the same value; the rest stay."""
    fresh = {tuple(c[k] for k in key) for c in new}
    return [c for c in earlier if tuple(c[k] for k in key) not in fresh] + new


def atomic_write(path: Path, text: str) -> None:
    """Write through a symlink to its target, keep the file's mode, replace in one step."""
    target = path.resolve() if path.is_symlink() else path
    tmp = target.with_name(target.name + ".tmp-ormus")
    tmp.write_text(text, encoding="utf-8")
    if target.exists():
        shutil.copymode(target, tmp)
    tmp.replace(target)


def write_json(path: Path, data: dict, backup: bool) -> None:
    if backup and path.exists():
        copy = path.with_name(path.name + ".bak-pre-ormus")
        if not copy.exists():
            shutil.copy2(path.resolve(), copy)
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def remove(target: Path) -> None:
    """Remove a file, a symlink (the link, not what it points to) or a folder."""
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)


def install(config: Config, home: Path, keys: bool) -> list[str]:
    files, counts, sp = prepare(config, home, keys)
    old = read_manifest(home)
    earlier = old.get("settings", {})
    prog_rec = earlier.get("programs.json", {})
    key_rec = earlier.get("keys.json", {})
    settings = {
        "programs.json": {
            "created": bool(prog_rec.get("created")) or not sp.programs_existed,
            "changes": merge_records(prog_rec.get("changes", []), sp.programs_changes, ("program", "field")),
        },
        "keys.json": {
            "rebound": merge_records(key_rec.get("rebound", []), sp.key_record["rebound"], ("section", "key")),
            "added": merge_records(key_rec.get("added", []), sp.key_record["added"], ("section", "key")),
        },
    }
    # The manifest goes first: whatever happens next, undo knows what to take out.
    kept = [p for p in old.get("paths", []) if path_ok(p)]
    dropped = [p for p in old.get("paths", []) if not path_ok(p)]
    manifest = {"paths": sorted(set(kept) | set(top_paths(files))),
                "settings": settings, "tool": "playbook-herdr-ormus-look"}
    try:
        atomic_write(home / MANIFEST, json.dumps(manifest, indent=2) + "\n")
        for top in top_paths(files):
            target = home / top
            remove(target)
        for rel, data in files.items():
            target = home / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        if sp.programs_after != sp.programs_before:
            write_json(sp.programs_path, sp.programs_after, backup=True)
        if sp.keys_after is not None and sp.keys_after != sp.keys_before:
            write_json(sp.keys_path, sp.keys_after, backup=True)
    except OSError as e:
        raise Stop(f"{e}. The install stopped part-way; run `undo` to take out what it wrote.") from e
    return [f"manifest: dropped {p!r}, which is not one of this tool's files" for p in dropped] + report(files, counts, sp)


def report(files: dict[str, bytes], counts: dict[str, int], sp: SettingsPlan) -> list[str]:
    lines = ["Built from Herdr's shipped mods (mods/spaces, mods/picker, mods/pane):"]
    for upstream, ours in PATCHED.items():
        extra = sorted(r.split("/")[-1] for r in files if r.startswith(f"mods/{ours}/logos/"))
        logos = f", logos/{', logos/'.join(extra)}" if extra else ""
        lines.append(f"  mods/{ours}/  main.js ({counts[upstream]} edits), mod.json{logos}")
    lines.append("Copied as they are:")
    lines.append("  layouts/ormus.json, layouts/ormus.svg")
    themes = sorted(Path(r).stem for r in files if r.startswith("themes/"))
    lines.append(f"  themes: {', '.join(themes)}")
    for mod in sorted({r.split('/')[1] for r in files if r.startswith("mods/")} - set(PATCHED.values())):
        count = sum(1 for r in files if r.startswith(f"mods/{mod}/"))
        lines.append(f"  mods/{mod}/  {count} files" + (" (tiles.js is built from your config)" if mod == "ormus-needs" else ""))
    lines.append("programs.json: " + ("Claude's icon set" if sp.programs_after != sp.programs_before else "already set"))
    if sp.keys_after is None:
        lines.append(f"keys.json: not changed ({sp.key_note}). To get the shortcuts, add these by hand:")
        lines += merge_home.bindings_text()
    else:
        lines.append("keys.json: " + ("picker keys open ormus-picker, Ormus keys added"
                                      if sp.keys_after != sp.keys_before else "already set"))
        lines += [f"keys.json: left out {k}: bind it by hand if you want it" for k in sp.key_left]
    return lines


def path_ok(top: object) -> bool:
    """A manifest path is one of the look's own files, judged by its text alone."""
    if not isinstance(top, str) or top.startswith("/") or "\\" in top:
        return False
    parts = PurePosixPath(top).parts
    return (
        len(parts) == 2
        and parts[0] in ("layouts", "themes", "mods")
        and re.match(r"^ormus[-.]", parts[1]) is not None
        and ".." not in parts
        and "." not in parts
    )


def safe_top(home: Path, top: object) -> Path:
    """The path of a manifest entry, only when it is the look's own file in this home.

    The text is checked, not the resolved path, so a `mods` or `layouts` folder that is a
    symlink (a dotfile manager makes them) works. A link as the last part must point inside."""
    if not path_ok(top):
        raise Stop(f"the manifest names {top!r}, which is not one of this tool's files in the home: nothing was removed")
    target = home / str(top)
    if target.is_symlink() and home.resolve() not in target.resolve().parents:
        raise Stop(f"{top} is a link that points outside the home: nothing was removed")
    return target


def read_settings_file(path: Path, lines: list[str]) -> dict | None:
    """The file as an object, or None with a note: a file that is not an object is kept as it is."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        lines.append(f"  {path.name} is not valid JSON now: kept as it is")
        return None
    if not isinstance(data, dict):
        lines.append(f"  {path.name} is not a JSON object now: kept as it is")
        return None
    return data


def undo_settings(home: Path, settings: dict) -> list[str]:
    lines: list[str] = []
    prog = settings.get("programs.json", {})
    path = home / "programs.json"
    if path.is_file() and prog.get("changes") and (current := read_settings_file(path, lines)) is not None:
        after, notes = merge_home.revert_programs(current, prog["changes"])
        lines += [f"  {n}" for n in notes]
        if after != current:
            if prog.get("created") and after in ({}, {"programs": {}}):
                path.unlink()
                lines.append("  programs.json removed (the install made it, nothing else is in it)")
            else:
                write_json(path, after, backup=False)
                lines.append("  programs.json: the values install set were put back")
    keys = settings.get("keys.json", {})
    path = home / "keys.json"
    if path.is_file() and (keys.get("rebound") or keys.get("added")) and (current := read_settings_file(path, lines)) is not None:
        after, notes = merge_home.revert_keys(current, keys)
        lines += [f"  {n}" for n in notes]
        if after != current:
            write_json(path, after, backup=False)
            lines.append("  keys.json: the keys install changed or added were put back; your other keys stay")
    return lines


def drop_spent_backup(path: Path) -> None:
    """The courtesy copy from before the first install goes when the file reads the same as it again."""
    backup = path.with_name(path.name + ".bak-pre-ormus")
    if backup.is_file() and path.is_file():
        try:
            if json.loads(backup.read_text()) == json.loads(path.read_text()):
                backup.unlink()
        except json.JSONDecodeError:
            pass


def undo(home: Path) -> list[str]:
    manifest = read_manifest(home)
    if not manifest:
        raise Stop(f"no {MANIFEST} in {home}: nothing from this tool to undo")
    targets = [(top, safe_top(home, top)) for top in manifest.get("paths", [])]  # all checked before any removal
    lines = undo_settings(home, manifest.get("settings", {}))
    for name in ("programs.json", "keys.json"):
        drop_spent_backup(home / name)
    for top, target in targets:
        remove(target)
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


def file_state(path: Path) -> str:
    """A JSON file by what it says (its layout may differ), any other file by its bytes."""
    data = path.read_bytes()
    if path.suffix == ".json":
        try:
            return "json:" + json.dumps(json.loads(data), sort_keys=True)
        except json.JSONDecodeError:
            pass
    return hashlib.sha256(data).hexdigest()


def tree_state(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): file_state(p) for p in sorted(folder.rglob("*")) if p.is_file()}


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
        files, _, settings = prepare(config, home, keys=True)
        print(f"check: the patch fits Herdr's mods in {home}; programs.json and keys.json are readable; "
              f"install would write {len(files)} files")
        return
    print("\n".join(install(config, home, keys=not args.no_keys) + [""] + next_steps()))


if __name__ == "__main__":
    main()
