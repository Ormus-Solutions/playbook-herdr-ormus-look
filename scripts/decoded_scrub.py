#!/usr/bin/env python3
"""decoded_scrub.py: the scrub on the text as a program reads it, not as it is typed.

scripts/scrub.sh reads the characters in a file. A word written with an escape
(a backslash-u code, a hex escape, an HTML entity) is not those characters in the
file, but it is the same word once a program reads it. This check closes that gap:

  - it decodes the backslash-u escapes in every text file and runs your deny-list
    on the decoded text; the one word the repo spells with an escape on purpose
    (SHIELD below) is skipped only for a deny-list entry that is exactly that word;
  - it refuses the other ways to spell letters without typing them: hex escapes
    (backslash-x), octal, named and doubled escapes, CSS escapes, the char-code and
    decoding functions of JavaScript and Python, numeric HTML entities, runs of
    percent codes, and letters outside ASCII in code files (lookalikes).

Usage: python3 scripts/decoded_scrub.py [dir]
The deny-list path is $PLAYBOOK_DENYLIST, default ~/.config/playbooks/denylist.txt;
without one the decoding checks still run. Findings print file, line and rule, never
the word. Exit 0 clean, 1 findings.
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from pathlib import Path

SHIELD = "hov" + "\\" + "u0065r"  # the one escaped word that is allowed, as typed in the files
SHIELD_WORD = "hov" + "er"  # what it decodes to
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
CODE_SUFFIXES = {".js", ".mjs", ".py", ".sh", ".css", ".html", ".ts"}
BS = re.escape(chr(92))  # a backslash, as a regex piece, so this file never types an escape itself
RULES = {
    "hex-escape": re.compile(BS + r"x[0-9a-fA-F]{2}"),
    "wide-escape": re.compile(BS + r"U[0-9a-fA-F]{8}"),
    "named-escape": re.compile(BS + r"N\{"),
    "octal-escape": re.compile(BS + r"[0-7]{3}"),
    "double-escape": re.compile(BS + BS + r"(?:u[0-9a-fA-F]{4}|u" + re.escape("{") + r"|x[0-9a-fA-F]{2}|U[0-9a-fA-F]{8}|N" + re.escape("{") + ")"),
    "char-code-function": re.compile(
        r"fromChar" + r"Code|fromCode" + r"Point|\bchr\(|\batob\(|\bunescape\(|decodeURI" + r"Component\(|from" + r"hex\(|rot" + "13",
        re.I,
    ),
    "html-entity": re.compile(r"&#[xX]?[0-9a-fA-F]+"),
    "percent-run": re.compile(r"(?:%[0-9a-fA-F]{2}){2,}"),
}
CSS_ESCAPE = re.compile(BS + r"[0-9a-fA-F]{1,6}")  # a CSS escape, checked in CSS files only
UNICODE = re.compile(BS + r"u\{([0-9a-fA-F]{1,8})\}|" + BS + r"u([0-9a-fA-F]{4})|" + BS + r"U([0-9a-fA-F]{8})")


def decode(line: str, blank_shield: bool = False) -> str:
    """The line as a program reads it. Raises ValueError on a code point that does not exist."""
    if blank_shield:
        line = line.replace(SHIELD, "\x00")
    return UNICODE.sub(lambda m: chr(int(m.group(1) or m.group(2) or m.group(3), 16)), line)


def load_denylist() -> list[tuple[re.Pattern[str], bool]]:
    path = Path(os.environ.get("PLAYBOOK_DENYLIST") or "~/.config/playbooks/denylist.txt").expanduser()
    if not path.is_file():
        return []
    patterns = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        words = [re.escape(w) for w in re.split(r"[\s._-]+", entry) if w]
        body = r"[\s._-]?".join(words)
        only_shield = [w.lower() for w in re.split(r"[\s._-]+", entry) if w] == [SHIELD_WORD]
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
        code = file.suffix in CODE_SUFFIXES or file.suffix == ".json"
        for n, line in enumerate(text.splitlines(), 1):
            where = f"{file.relative_to(root)}:{n}"
            for rule, rx in RULES.items():
                if rx.search(line):
                    print(f"{where}: {rule}")
                    found += 1
            if file.suffix == ".css" and CSS_ESCAPE.search(line):
                print(f"{where}: css-escape")
                found += 1
            if code and any(unicodedata.category(c).startswith("L") and ord(c) > 127 for c in line):
                print(f"{where}: non-ascii-letter (a lookalike letter can spell a word)")
                found += 1
            try:
                full, blank = decode(line), decode(line, blank_shield=True)
            except (ValueError, OverflowError):
                print(f"{where}: invalid-escape")
                found += 1
                continue
            if full == line and "\\" not in line:
                continue
            for i, (rx, only_shield) in enumerate(deny, 1):
                # An entry that is exactly the shielded word skips the shielded spelling; every
                # other entry, also one that has that word inside it, reads the fully decoded text.
                seen = rx.search(blank if only_shield else full)
                if seen and not rx.search(line):
                    print(f"{where}: deny-list entry {i} (after decoding escapes)")
                    found += 1
    status = "FAILED" if found else "clean"
    print(f"decoded-scrub: {status} ({checked} text files, deny-list: {len(deny)} entries, {found} findings)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
