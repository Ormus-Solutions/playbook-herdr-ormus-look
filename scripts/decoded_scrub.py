#!/usr/bin/env python3
"""decoded_scrub.py: the scrub on the text as a program reads it, not as it is typed.

scripts/scrub.sh reads the characters in a file. A word written with an escape
(a backslash-u code, a hex escape, an HTML entity) is not those characters in the
file, but it is the same word once a program reads it. This check closes that gap:

  - it decodes the backslash-u escapes in every text file and runs your deny-list
    on the decoded text; the one word the repo spells with an escape on purpose
    (SHIELD below) is the only exception;
  - it refuses the other ways to spell letters without typing them: hex escapes
    (backslash-x), the char-code functions of JavaScript and Python, and numeric
    HTML entities.

Usage: python3 scripts/decoded_scrub.py [dir]
The deny-list path is $PLAYBOOK_DENYLIST, default ~/.config/playbooks/denylist.txt;
without one the decoding checks still run. Findings print file, line and rule, never
the word. Exit 0 clean, 1 findings.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SHIELD = "hov" + "\\" + "u0065r"  # the one escaped word that is allowed, as typed in the files
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
RULES = {
    "hex-escape": re.compile(r"\\x[0-9a-fA-F]{2}"),
    "char-code-function": re.compile(r"fromChar" + r"Code|fromCode" + r"Point|\bchr\("),
    "html-entity": re.compile(r"&#[xX]?[0-9a-fA-F]+;"),
}
UNICODE = re.compile(r"\\u\{([0-9a-fA-F]{1,6})\}|\\u([0-9a-fA-F]{4})")


def decode(line: str) -> str:
    line = line.replace(SHIELD, "\x00")  # the allowed word stays out of the match
    return UNICODE.sub(lambda m: chr(int(m.group(1) or m.group(2), 16)), line)


def load_denylist() -> list[re.Pattern[str]]:
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
        patterns.append(re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.I))
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
            for rule, rx in RULES.items():
                if rx.search(line):
                    print(f"{file.relative_to(root)}:{n}: {rule}")
                    found += 1
            decoded = decode(line)
            if decoded != line.replace(SHIELD, "\x00") or "\\" in line:
                for i, rx in enumerate(deny, 1):
                    if rx.search(decoded) and not rx.search(line.replace(SHIELD, "\x00")):
                        print(f"{file.relative_to(root)}:{n}: deny-list entry {i} (after decoding escapes)")
                        found += 1
    status = "FAILED" if found else "clean"
    print(f"decoded-scrub: {status} ({checked} text files, deny-list: {len(deny)} entries, {found} findings)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
