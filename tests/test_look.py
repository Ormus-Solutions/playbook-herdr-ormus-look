"""Offline tests: they pin the behaviour on synthetic data, with no setup.

Run them with: python3 -m unittest discover -s tests
They never touch a real Herdr home: each test works in its own temporary copy
of examples/herdr-home. The node tests run only when node is installed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(ROOT / "src"))

import merge_home  # noqa: E402
import ormus_look as ol  # noqa: E402
import pane_head  # noqa: E402
import space_tiles as st  # noqa: E402

NODE = shutil.which("node") or ""
POINTER = "hov" + "er"  # the word the repo writes with an escape (see SHIELD in src/ormus_look.py)


class TempHome(unittest.TestCase):
    """A fresh copy of the synthetic Herdr home, with the example config."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "herdr-home"
        shutil.copytree(EXAMPLES / "herdr-home", self.home)
        self.config = ol.load_config(str(EXAMPLES / "spaces.json"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def install(self, keys: bool = True) -> list[str]:
        return ol.install(self.config, self.home, keys)


class InstallTest(TempHome):
    def test_install_writes_the_look_and_the_patched_mods(self) -> None:
        self.install()
        for rel in (
            "layouts/ormus.json",
            "themes/ormus-gold.json",
            "mods/ormus-chrome/main.js",
            "mods/ormus-chrome/fonts/Inter-OFL.txt",
            "mods/ormus-needs/tiles.js",
            "mods/ormus-search/main.js",
            "mods/ormus-cards/main.js",
            "mods/ormus-spaces/logos/acme.svg",
            "mods/ormus-spaces/logos/ormus-mark.svg",
            ".ormus-look.json",
        ):
            self.assertTrue((self.home / rel).is_file(), rel)
        for ours, upstream in (("ormus-spaces", "spaces"), ("ormus-picker", "picker"), ("ormus-pane", "pane")):
            mod = json.loads((self.home / "mods" / ours / "mod.json").read_text())
            self.assertEqual(mod["cloned_from"], {"name": upstream, "version": ol.HERDR_VERSION})
        # Herdr's own folders are not touched.
        self.assertEqual(
            (self.home / "mods/spaces/main.js").read_bytes(),
            (EXAMPLES / "herdr-home/mods/spaces/main.js").read_bytes(),
        )

    def test_patched_tiles_use_the_config(self) -> None:
        self.install()
        text = (self.home / "mods/ormus-spaces/main.js").read_text()
        self.assertIn("ormusTile(w, fill)", text)
        self.assertIn('"acme · WEB": {"logo": "acme.svg"}', text)
        self.assertIn('import { View, div, svg, image } from "gpui-kit";', text)
        self.assertIn(st.ACCENTS["teal"], text)
        picker = (self.home / "mods/ormus-picker/main.js").read_text()
        self.assertIn("ormusTile(r.w, spaceColor(t, r.w))", picker)

    def test_the_shield_is_gone_in_what_is_installed(self) -> None:
        self.install()
        theme = json.loads((self.home / "themes/ormus-gold.json").read_text())
        self.assertIn(POINTER, theme["colors"])
        text = (self.home / "mods/ormus-chrome/main.js").read_text()
        self.assertNotIn("\\u0065", text)
        self.assertIn(f".{POINTER}(", text)
        self.assertIn(f".{POINTER}(", (self.home / "mods/ormus-pane/main.js").read_text())

    def test_settings_are_merged_and_the_rest_stays(self) -> None:
        self.install()
        programs = json.loads((self.home / "programs.json").read_text())
        self.assertEqual(programs["programs"]["claude"]["icon"], "mods/ormus-chrome/ormus-mark.svg")
        keys = json.loads((self.home / "keys.json").read_text())
        self.assertEqual(keys["global"]["ctrl-shift-k"], "mod.open:ormus-picker")
        self.assertEqual(keys["global"]["ctrl-shift-t"], "tab.new")
        self.assertEqual(keys["global"]["ctrl-space a"]["args"]["name"], "ormus-picker")
        self.assertEqual(keys["global"]["ctrl-shift-s"], "mod.open:ormus-search")
        self.assertEqual(keys["layout:ormus"]["ctrl-shift-i"], "ormus-needs.needs")
        self.assertEqual(keys["terminal"]["ctrl-shift-c"], "terminal.copy")
        self.assertTrue((self.home / "keys.json.bak-pre-ormus").is_file())

    def test_no_keys_leaves_keys_json_alone(self) -> None:
        before = (self.home / "keys.json").read_bytes()
        self.install(keys=False)
        self.assertEqual((self.home / "keys.json").read_bytes(), before)
        self.assertFalse((self.home / "keys.json.bak-pre-ormus").exists())

    def test_a_key_you_bound_is_left_out_and_reported(self) -> None:
        keys = json.loads((self.home / "keys.json").read_text())
        keys["global"]["shift-ctrl-S"] = "tab.new"
        (self.home / "keys.json").write_text(json.dumps(keys))
        lines = self.install()
        self.assertTrue(any("left out ctrl-shift-s" in line for line in lines))
        after = json.loads((self.home / "keys.json").read_text())
        self.assertEqual(after["global"]["shift-ctrl-S"], "tab.new")
        self.assertNotIn("ctrl-shift-s", after["global"])

    def test_install_twice_then_undo_restores_the_home(self) -> None:
        before = ol.tree_state(self.home)
        self.install()
        self.install()
        ol.undo(self.home)
        self.assertEqual(ol.tree_state(self.home), before)

    def test_undo_keeps_a_file_you_changed_after_install(self) -> None:
        self.install()
        keys = json.loads((self.home / "keys.json").read_text())
        keys["global"]["ctrl-shift-y"] = "tab.new"
        (self.home / "keys.json").write_text(json.dumps(keys))
        lines = ol.undo(self.home)
        self.assertTrue(any("keys.json changed after install: kept" in line for line in lines))
        self.assertIn("ctrl-shift-y", json.loads((self.home / "keys.json").read_text())["global"])
        self.assertFalse((self.home / "mods/ormus-chrome").exists())

    def test_a_folder_that_is_not_ours_stops_the_install(self) -> None:
        (self.home / "mods/ormus-chrome").mkdir()
        (self.home / "mods/ormus-chrome/main.js").write_text("// yours\n")
        with self.assertRaises(SystemExit) as raised:
            self.install()
        self.assertIn("ormus-chrome", str(raised.exception))
        self.assertFalse((self.home / ".ormus-look.json").exists())
        self.assertEqual((self.home / "mods/ormus-chrome/main.js").read_text(), "// yours\n")

    def test_a_moved_anchor_stops_before_anything_is_written(self) -> None:
        main = self.home / "mods/picker/main.js"
        main.write_text(main.read_text().replace(".justify_center()", ".justify_start()"))
        before = ol.tree_state(self.home)
        with self.assertRaises(SystemExit) as raised:
            self.install()
        self.assertIn("anchor", str(raised.exception))
        self.assertEqual(ol.tree_state(self.home), before)

    def test_a_home_without_herdrs_own_mods_stops(self) -> None:
        shutil.rmtree(self.home / "mods/pane")
        with self.assertRaises(SystemExit) as raised:
            self.install()
        self.assertIn("Herdr's own mod pane", str(raised.exception))
        self.assertFalse((self.home / ".ormus-look.json").exists())


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        shutil.copytree(EXAMPLES / "logos", self.dir / "logos")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def load(self, spaces: dict) -> ol.Config:
        file = self.dir / "spaces.json"
        file.write_text(json.dumps({"spaces": spaces}))
        return ol.load_config(str(file))

    def test_the_example_loads(self) -> None:
        config = ol.load_config(str(EXAMPLES / "spaces.json"))
        self.assertEqual(len(config.spaces), 7)

    def test_bad_entries_are_named(self) -> None:
        for spaces, word in (
            ({"a": {"logo": "../x.svg"}}, "logo"),
            ({"a": {"logo": "missing.svg"}}, "missing"),
            ({"a": {"bg": "red"}}, "bg"),
            ({"a": {"pad": 40}}, "pad"),
            ({"a": {"accent": "pink"}}, "accent"),
            ({"a": {"letter": "ABC"}}, "letter"),
            ({"a": {"colour": "#ffffff"}}, "unknown"),
            ({"a": "x"}, "object"),
        ):
            with self.subTest(spaces=spaces), self.assertRaises(SystemExit) as raised:
                self.load(spaces)
            self.assertIn(word, str(raised.exception))

    def test_a_text_file_named_svg_is_refused(self) -> None:
        (self.dir / "logos/fake.svg").write_text("just words\n")
        with self.assertRaises(SystemExit):
            self.load({"a": {"logo": "fake.svg"}})

    def test_a_config_path_you_name_must_exist(self) -> None:
        with self.assertRaises(SystemExit):
            ol.load_config(str(self.dir / "nope.json"))


class AnchorTest(unittest.TestCase):
    def test_each_anchor_appears_once_in_the_stand_ins(self) -> None:
        home = EXAMPLES / "herdr-home/mods"
        spaces = (home / "spaces/main.js").read_text()
        picker = (home / "picker/main.js").read_text()
        for text, anchors in (
            (spaces, [st.GPUI_IMPORT, st.UPSTREAM_MARK, st.SPACES_TILE]),
            (picker, [st.GPUI_IMPORT, st.UPSTREAM_MARK, st.PICKER_TILE]),
        ):
            for anchor in anchors:
                self.assertEqual(text.count(anchor), 1, anchor)

    def test_pane_patch_makes_ten_edits_and_adds_the_features(self) -> None:
        src = (EXAMPLES / "herdr-home/mods/pane/main.js").read_text()
        out = pane_head.patch_pane(src)
        for word in ("ormusName(p)", "ormusSpot(p)", "ormusOverviewHere(p)", "ormus.title", "ormus.spotlight"):
            self.assertIn(word, out)
        self.assertIn("Spotlight", out)

    def test_edit_refuses_an_anchor_that_is_not_unique(self) -> None:
        with self.assertRaises(SystemExit):
            st.edit("aa", "a", "b", "the test anchor")
        with self.assertRaises(SystemExit):
            st.edit("xx", "a", "b", "the test anchor")


class MergeHomeTest(unittest.TestCase):
    def test_key_id_ignores_order_and_case(self) -> None:
        self.assertEqual(merge_home.key_id("shift-ctrl-I"), merge_home.key_id("ctrl-shift-i"))
        self.assertEqual(merge_home.key_id("cmd-alt--")[1], "-")

    def test_programs_merge_keeps_other_fields(self) -> None:
        mine = {"programs": {"claude": {"name": "Mine"}, "other": {"icon": "x.svg"}}}
        ormus = {"programs": {"claude": {"icon": "i.svg", "tint": True}}}
        out = merge_home.merge(mine, ormus)
        self.assertEqual(out["programs"]["claude"], {"name": "Mine", "icon": "i.svg", "tint": True})
        self.assertEqual(out["programs"]["other"], {"icon": "x.svg"})

    def test_a_terminal_key_blocks_the_ormus_key(self) -> None:
        out, left = merge_home.add_keys({"terminal": {"ctrl-shift-s": "terminal.copy"}})
        self.assertTrue(any("ctrl-shift-s" in x for x in left))
        self.assertNotIn("ctrl-shift-s", out.get("global", {}))


class SourceTest(unittest.TestCase):
    def test_the_repo_spells_the_shielded_word_only_with_its_escape(self) -> None:
        raw = re.compile(rf"\b{POINTER}\b")
        offenders = []
        for base in ("layouts", "themes", "mods", "src", "examples", "tests"):
            for file in (ROOT / base).rglob("*"):
                if file.suffix in (".js", ".json", ".py", ".svg", ".txt", ".md") and file.is_file():
                    if "__pycache__" in file.parts:
                        continue
                    if raw.search(file.read_text(encoding="utf-8", errors="ignore")):
                        offenders.append(file.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [])

    def test_the_fonts_keep_their_licenses(self) -> None:
        fonts = ROOT / "mods/ormus-chrome/fonts"
        for font in ("Inter", "CormorantGaramond"):
            self.assertTrue((fonts / f"{font}.ttf").is_file())
            self.assertIn("SIL Open Font License", (fonts / f"{font}-OFL.txt").read_text())

    def test_the_apache_notice_is_there(self) -> None:
        self.assertIn("Apache License", (ROOT / "LICENSE-APACHE-2.0.txt").read_text())
        notice = (ROOT / "NOTICE").read_text()
        self.assertIn("Apache License, Version 2.0", notice)
        self.assertIn("Changes", notice)

    def test_no_logo_but_the_examples_and_the_mark_ship(self) -> None:
        shipped = sorted(p.name for p in ROOT.rglob("*") if p.suffix in (".png",) and ".git" not in p.parts)
        self.assertEqual(shipped, [])
        svgs = sorted(p.name for p in (EXAMPLES / "logos").iterdir())
        self.assertEqual(svgs, ["acme.svg", "orbit.svg", "ormus-mark.svg", "peak.svg"])


@unittest.skipUnless(NODE, "node is not installed")
class NodeTest(TempHome):
    def node(self, code: str) -> str:
        done = subprocess.run([NODE, "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def test_every_installed_mod_parses(self) -> None:
        self.install()
        for mod in sorted((self.home / "mods").glob("ormus-*")):
            copy = self.tmp / f"{mod.name}.mjs"
            copy.write_text((mod / "main.js").read_text())
            done = subprocess.run([NODE, "--check", str(copy)], capture_output=True, text=True, timeout=60)
            self.assertEqual(done.returncode, 0, f"{mod.name}: {done.stderr}")

    def test_letters_come_from_the_part_after_the_separator(self) -> None:
        shared = st.tile_js({}, " · ")
        start = shared.index("function ormusLetter")
        end = shared.index("function ormusTile")
        code = (
            'const ORMUS_SEPARATOR = " · ";\n' + shared[start:end]
            + 'console.log(JSON.stringify(["acme · WEB", "acme · API", "docs", "x · (hi)", "x · "].map(ormusLetter)));'
        )
        self.assertEqual(self.node(code), '["W","A","D","H","?"]')

    def test_space_colors_pick_the_least_used_and_keep_choices(self) -> None:
        text = st.needs_tiles_js(st.tile_js({}, " · "))
        start = text.index("const SPACE_PALETTE")
        end = text.index("// --- end of space colors ---")
        code = (
            text[start:end]
            + 'const a = assignSpaceColors({}, [{id:"1",name:"a"},{id:"2",name:"b"},{id:"3",name:"~"}]);'
            + 'const b = assignSpaceColors(a.kept, [{id:"2",name:"b"}]);'
            + "console.log(JSON.stringify([a.kept, a.changed, b.kept, b.changed]));"
        )
        self.assertEqual(
            self.node(code),
            '[{"1":"ansi6","2":"ansi3"},true,{"2":"ansi3"},true]',
        )


class DemoTest(unittest.TestCase):
    def test_run_sh_prints_the_expected_output(self) -> None:
        done = subprocess.run(["bash", str(EXAMPLES / "run.sh")], capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, (EXAMPLES / "expected-output.txt").read_text())
        self.assertTrue(done.stdout.rstrip().endswith("The demo home is back as it was: yes"))

    def test_the_demo_does_not_touch_the_examples(self) -> None:
        before = ol.tree_state(EXAMPLES / "herdr-home")
        ol.demo()
        self.assertEqual(ol.tree_state(EXAMPLES / "herdr-home"), before)


if __name__ == "__main__":
    unittest.main()
