"""Merge the Ormus settings into the person's own files in a Herdr home.

- programs.json: Herdr reads it on top of its built-in program table. Adds or
  updates only the fields Ormus sets (today: Claude's icon and tint).
- keys.json: keys bound to Herdr's picker ("mod.open:picker") open the Ormus
  picker instead, which shows the space logos. The Ormus keys (ORMUS_KEYS: search
  all terminals, and the Ormus layout's own) are added, each only where the
  person has not bound that key.
  No other key changes. Herdr gives an untouched keys.json its new default keys
  on an upgrade; once this module writes the file, it is the person's own, as
  any edit makes it, and new default keys must then be added by hand.

Everything else in both files stays. The first change to a file keeps a backup
as <file>.bak-pre-ormus. Standard library only. ormus_look.py calls these
functions; the file writes and the undo live there.
"""

from __future__ import annotations

import json
from pathlib import Path

PICKER = "mod.open:picker"
ORMUS_PICKER = "mod.open:ormus-picker"
# The keys Ormus adds where they are free. Every layout: search all terminals (mods/ormus-search).
# The Ormus layout: Needs you, the Overview and the sidebar switch (mods/ormus-needs).
ORMUS_KEYS: dict[str, dict[str, str]] = {
    "global": {"ctrl-shift-s": "mod.open:ormus-search"},
    "layout:ormus": {
        "ctrl-shift-i": "ormus-needs.needs",
        "ctrl-shift-g": "ormus-needs.overview",
        "ctrl-shift-j": "ormus-needs.sidebar",
    },
}


def merge(mine: dict, ormus: dict) -> dict:
    """programs.json: Ormus's fields win; the person's other programs and fields stay."""
    out = json.loads(json.dumps(mine))
    programs = out.setdefault("programs", {})
    for key, fields in ormus.get("programs", {}).items():
        programs[key] = {**programs.get(key, {}), **fields}
    return out


def rebind(keys: dict) -> dict:
    """keys.json: every key that opens Herdr's picker opens the Ormus picker."""
    out = json.loads(json.dumps(keys))
    for section in out.values():
        if not isinstance(section, dict):
            continue
        for key, action in section.items():
            if action == PICKER:
                section[key] = ORMUS_PICKER
            elif (
                isinstance(action, dict)
                and action.get("command") == "mod.open"
                and isinstance(action.get("args"), dict)
                and action["args"].get("name") == "picker"
            ):
                action["args"]["name"] = "ormus-picker"
    return out


def key_id(key: str) -> tuple[frozenset[str], str]:
    """A key as Herdr matches it: its modifiers in any order and case, then the key.

    "shift-ctrl-I" and "ctrl-shift-i" are the same key. A minus key ends in "--"
    ("cmd-alt--").
    """
    k = key.strip().lower()
    if k.endswith("--") or k == "-":
        mods, last = k[:-2] if k != "-" else "", "-"
    else:
        mods, _, last = k.rpartition("-")
    return frozenset(m for m in mods.split("-") if m), last


def bound(section: dict, key: str) -> str | None:
    """The key in `section` that is the same key as `key` (written its own way), or None."""
    want = key_id(key)
    return next((k for k in section if isinstance(k, str) and key_id(k) == want), None)


def add_keys(keys: dict) -> tuple[dict, list[str]]:
    """keys.json: add ORMUS_KEYS where the key is free; return the keys left out.

    A key is taken when its section binds it to something else, when `global`
    binds it (the layout section would hide that), or when `terminal` binds it
    (that section wins inside a terminal, so the Ormus key would not work there).
    Keys match as Herdr matches them (key_id), not as written.
    """
    out = json.loads(json.dumps(keys))
    left: list[str] = []
    for section, binds in ORMUS_KEYS.items():
        mine = out.get(section, {})
        if not isinstance(mine, dict):
            left += [f"{key} ({section} is not a key table)" for key in binds]
            continue
        for key, action in binds.items():
            same = bound(mine, key)
            if same is not None:
                if mine[same] != action:
                    left.append(f"{key} (yours in {section}: {mine[same]})")
                continue
            taken = [
                (s, k)
                for s in ("global", "terminal")
                if isinstance(out.get(s), dict)
                for k in [bound(out[s], key)]
                if k is not None
            ]
            if taken:
                s, k = taken[0]
                left.append(f"{key} (yours in {s}: {out[s][k]})")
                continue
            mine[key] = action
        if mine:
            out[section] = mine
    return out, left


def write(path: Path, before: dict, after: dict) -> bool:
    """Atomic write with a first-change backup; False when nothing changed."""
    if after == before:
        return False
    if path.exists():
        backup = path.with_name(path.name + ".bak-pre-ormus")
        if not backup.exists():
            backup.write_text(path.read_text())
    tmp = path.with_name(path.name + ".tmp-ormus")
    tmp.write_text(json.dumps(after, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)  # Herdr reloads both files live
    return True


# ---- what a change was, and how to take back only that ---------------------------------
# The install records each value it set or rebound (before and after). Undo puts a value
# back only while it still reads as the install left it, and never replaces a whole file.


class BadFile(ValueError):
    """A settings file that is not the shape Herdr reads: the message says what to fix."""


def check_programs(mine: object, ormus: dict) -> dict:
    if not isinstance(mine, dict):
        raise BadFile("programs.json must hold a JSON object")
    programs = mine.get("programs", {})
    if not isinstance(programs, dict):
        raise BadFile("programs.json: 'programs' must be an object")
    for key in ormus.get("programs", {}):
        if key in programs and not isinstance(programs[key], dict):
            raise BadFile(f"programs.json: the entry '{key}' must be an object")
    return mine


def check_keys(keys: object) -> dict:
    if not isinstance(keys, dict):
        raise BadFile("keys.json must hold a JSON object")
    return keys


def program_changes(mine: dict, after: dict) -> list[dict]:
    out = []
    for prog, fields in after.get("programs", {}).items():
        was = mine.get("programs", {}).get(prog)
        for field, value in fields.items():
            if was is None or field not in was or was[field] != value:
                out.append({
                    "program": prog, "field": field, "after": value,
                    "had": was is not None and field in was,
                    "before": None if was is None else was.get(field),
                    "made_program": was is None,
                })
    return out


def key_changes(before: dict, after: dict) -> dict[str, list[dict]]:
    rebound, added = [], []
    for section, binds in after.items():
        old = before.get(section)
        if not isinstance(binds, dict):
            continue
        for key, action in binds.items():
            if isinstance(old, dict) and key in old:
                if old[key] != action:
                    rebound.append({"section": section, "key": key, "before": old[key], "after": action})
            else:
                added.append({"section": section, "key": key, "after": action,
                              "made_section": not isinstance(old, dict)})
    return {"rebound": rebound, "added": added}


def revert_programs(current: dict, changes: list[dict]) -> tuple[dict, list[str]]:
    out, notes = json.loads(json.dumps(current)), []
    programs = out.get("programs")
    if not isinstance(programs, dict):
        return out, notes
    for c in changes:
        entry = programs.get(c["program"])
        if not isinstance(entry, dict) or entry.get(c["field"]) != c["after"]:
            notes.append(f"programs.json: {c['program']}.{c['field']} is not as install left it: kept")
            continue
        if c.get("had"):
            entry[c["field"]] = c.get("before")
        else:
            del entry[c["field"]]
            if not entry and c.get("made_program"):
                del programs[c["program"]]
    return out, notes


def revert_keys(current: dict, record: dict) -> tuple[dict, list[str]]:
    out, notes = json.loads(json.dumps(current)), []
    for c in record.get("rebound", []):
        section = out.get(c["section"])
        if isinstance(section, dict) and section.get(c["key"]) == c["after"]:
            section[c["key"]] = c.get("before")
        else:
            notes.append(f"keys.json: {c['key']} in {c['section']} is not as install left it: kept")
    for c in record.get("added", []):
        section = out.get(c["section"])
        if isinstance(section, dict) and section.get(c["key"]) == c["after"]:
            del section[c["key"]]
            if not section and c.get("made_section"):
                del out[c["section"]]
    return out, notes


def bindings_text() -> list[str]:
    """The bindings to add by hand, as lines for a person to read."""
    lines = [f'  replace "{PICKER}" with "{ORMUS_PICKER}" wherever a key opens it,']
    for section, binds in ORMUS_KEYS.items():
        for key, action in binds.items():
            lines.append(f'  in "{section}": "{key}": "{action}"')
    return lines
