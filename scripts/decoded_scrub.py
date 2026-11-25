#!/usr/bin/env python3
"""decoded_scrub.py: the deny-list scrub on the text as a program reads it.

scripts/scrub.sh reads the characters in a file. A word written with an escape is
not those characters in the file, but it is the same word once a program decodes
it. This check decodes every escape form it knows, again and again until the text
stops changing, and runs your deny-list on the result.

Decoding repeats up to 50 times; a line that still changes after that is a finding.
Decoded: backslash-u (4 hex, braced, and the 8-hex capital form), \\N{NAME},
backslash-x, octal (3 digits), CSS escapes (1 to 6 hex digits), numeric HTML
entities with or without the semicolon, named HTML entities, and percent codes.

Not covered (do not rely on it for these): a word split by string concatenation or
a join, lookalike letters (Cyrillic or fullwidth), zero-width characters, and
encodings such as base64 or rot13. The deny-list match on the plain text is
scripts/scrub.sh's job; this script reports a word only when it shows up after
decoding and not before.

The one word the repo spells with an escape on purpose (SHIELD) is skipped only for a
deny-list entry that is exactly that word; an entry that has it inside several
words is matched on the fully decoded text.

Usage: python3 scripts/decoded_scrub.py [dir]
The deny-list path is $PLAYBOOK_DENYLIST, default ~/.config/playbooks/denylist.txt;
without one nothing is matched. Findings print file, line and rule, never the
word. A code point that does not exist is a finding. Exit 0 clean, 1 findings.
"""
from __future__ import annotations

import html
import os
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path

SHIELD = "hov" + "\\" + "u0065r"  # the one escaped word that is allowed, as typed in the files
SHIELD_WORD = "hov" + "er"  # what it decodes to
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
BS = re.escape("\\")  # a backslash, as a regex piece
MAX_PASSES = 50  # a line that still changes after this many rounds is a finding
MAX_CODE_POINT = 0x10FFFF

# One pattern per escape form; each is replaced by the character it stands for.
ESCAPES: list[tuple[re.Pattern[str], str]] = [
    # Explicit forms: a code point that does not exist is a finding.
    (re.compile(BS + r"u\{([0-9a-fA-F]{1,8})\}"), "hex"),
    (re.compile(BS + r"u([0-9a-fA-F]{4})"), "hex"),
    (re.compile(BS + r"U([0-9a-fA-F]{8})"), "hex"),
    (re.compile(BS + r"x([0-9a-fA-F]{2})"), "hex"),
    (re.compile(BS + r"N\{([^}\n]{1,100})\}"), "name"),
    # Forms that also look like ordinary text (paths, regexes, CSS): out of range stays literal.
    (re.compile(BS + r"([0-7]{3})"), "octal"),
    (re.compile(BS + r"([0-9a-fA-F]{1,6})[ \t]?"), "css"),
]


class BadCodePoint(ValueError):
    pass


def replace(match: re.Match[str], kind: str) -> str:
    text = match.group(1)
    if kind == "name":
        try:
            return unicodedata.lookup(text)
        except KeyError:
            return match.group(0)  # not a name Python knows: leave it
    value = int(text, 8 if kind == "octal" else 16)
    if value > MAX_CODE_POINT:
        if kind == "hex":
            raise BadCodePoint(match.group(0))
        return match.group(0)
    if kind == "css" and value < 0x20:
        return match.group(0)  # a control character would only make false matches
    return chr(value)


NUMERIC_ENTITY = re.compile(r"&#(?:[xX]([0-9a-fA-F]+)|([0-9]+));?")


def check_entities(line: str) -> None:
    """A numeric HTML entity past the last code point is a finding (html.unescape would hide it)."""
    for m in NUMERIC_ENTITY.finditer(line):
        try:
            value = int(m.group(1), 16) if m.group(1) else int(m.group(2))
        except ValueError:  # a number of thousands of digits
            raise BadCodePoint(m.group(0)[:20]) from None
        if value > MAX_CODE_POINT:
            raise BadCodePoint(m.group(0)[:20])


def decode_once(line: str) -> str:
    for rx, kind in ESCAPES:
        line = rx.sub(lambda m, k=kind: replace(m, k), line)
    check_entities(line)
    line = html.unescape(line)
    return urllib.parse.unquote(line)


class TooDeep(ValueError):
    pass


def decode(line: str, blank_shield: bool = False) -> str:
    """The line with every known escape decoded until it stops changing.

    Raises TooDeep when it still changes after MAX_PASSES rounds."""
    if blank_shield:
        line = line.replace(SHIELD, "\x00")
    for _ in range(MAX_PASSES):
        step = decode_once(line)
        if step == line:
            return line
        line = step
    if decode_once(line) != line:
        raise TooDeep(line[:20])
    return line


def load_denylist() -> list[tuple[re.Pattern[str], bool]]:
    path = Path(os.environ.get("PLAYBOOK_DENYLIST") or "~/.config/playbooks/denylist.txt").expanduser()
    if not path.is_file():
        return []
    patterns = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        words = [w for w in re.split(r"[\s._-]+", entry) if w]
        body = r"[\s._-]?".join(re.escape(w) for w in words)
        only_shield = [w.lower() for w in words] == [SHIELD_WORD]
        patterns.append((re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.I), only_shield))
    return patterns


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    deny = load_denylist()
    self_path = Path(__file__).resolve()
    found = 0
    checked = 0
    for file in sorted(root.rglob("*")):
        if not file.is_file() or SKIP_DIRS & set(file.relative_to(root).parts) or file.resolve() == self_path:
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        checked += 1
        for n, line in enumerate(text.splitlines(), 1):
            where = f"{file.relative_to(root)}:{n}"
            try:
                full, blank = decode(line), decode(line, blank_shield=True)
            except BadCodePoint:
                print(f"{where}: invalid-escape")
                found += 1
                continue
            except TooDeep:
                print(f"{where}: nesting deeper than {MAX_PASSES} levels")
                found += 1
                continue
            for i, (rx, only_shield) in enumerate(deny, 1):
                # An entry that is exactly the shielded word skips the shielded spelling; every
                # other entry, also one that has that word inside it, reads the fully decoded text.
                if rx.search(blank if only_shield else full) and not rx.search(line):
                    print(f"{where}: deny-list entry {i} (after decoding escapes)")
                    found += 1
    status = "FAILED" if found else "clean"
    print(f"decoded-scrub: {status} ({checked} text files, deny-list: {len(deny)} entries, {found} findings)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
