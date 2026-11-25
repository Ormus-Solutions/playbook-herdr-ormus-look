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
        self.assertNotIn("\\" + "u0065", text)
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

    def test_undo_keeps_a_key_you_added_after_install(self) -> None:
        self.install()
        keys = json.loads((self.home / "keys.json").read_text())
        keys["global"]["ctrl-shift-y"] = "tab.new"
        (self.home / "keys.json").write_text(json.dumps(keys))
        ol.undo(self.home)
        after = json.loads((self.home / "keys.json").read_text())
        self.assertEqual(after["global"]["ctrl-shift-y"], "tab.new")
        self.assertEqual(after["global"]["ctrl-shift-k"], "mod.open:picker")  # our rebind is reversed
        self.assertNotIn("ctrl-shift-s", after["global"])
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


class SettingsSafetyTest(TempHome):
    """H1: undo reverses only what install changed. H2: a bad file stops before any write."""

    def read(self, name: str) -> dict:
        return json.loads((self.home / name).read_text())

    def write(self, name: str, data: object) -> None:
        (self.home / name).write_text(json.dumps(data))

    def test_keys_edit_survives_install_again_and_undo(self) -> None:
        self.install()
        keys = self.read("keys.json")
        keys["global"]["ctrl-shift-y"] = "tab.new"
        self.write("keys.json", keys)
        self.install()
        ol.undo(self.home)
        after = self.read("keys.json")
        self.assertEqual(after["global"]["ctrl-shift-y"], "tab.new")
        self.assertEqual(after["global"]["ctrl-shift-k"], "mod.open:picker")
        self.assertEqual(after["global"]["ctrl-space a"]["args"]["name"], "picker")
        self.assertNotIn("layout:ormus", after)

    def test_programs_edit_survives_install_again_and_undo(self) -> None:
        self.write("programs.json", {"programs": {"claude": {"name": "Mine"}, "other": {"icon": "x.svg"}}})
        self.install()
        programs = self.read("programs.json")
        programs["programs"]["extra"] = {"icon": "y.svg"}
        programs["programs"]["claude"]["note"] = "later"
        self.write("programs.json", programs)
        self.install()
        ol.undo(self.home)
        after = self.read("programs.json")["programs"]
        self.assertEqual(after["claude"], {"name": "Mine", "note": "later"})
        self.assertEqual(after["other"], {"icon": "x.svg"})
        self.assertEqual(after["extra"], {"icon": "y.svg"})

    def test_a_programs_file_the_install_made_stays_when_you_added_to_it(self) -> None:
        self.install()
        programs = self.read("programs.json")
        programs["programs"]["extra"] = {"icon": "y.svg"}
        self.write("programs.json", programs)
        self.install()
        ol.undo(self.home)
        self.assertEqual(self.read("programs.json"), {"programs": {"extra": {"icon": "y.svg"}}})

    def test_a_value_you_changed_is_not_put_back_over(self) -> None:
        self.install()
        keys = self.read("keys.json")
        keys["global"]["ctrl-shift-k"] = "my.own.action"
        self.write("keys.json", keys)
        lines = ol.undo(self.home)
        self.assertEqual(self.read("keys.json")["global"]["ctrl-shift-k"], "my.own.action")
        self.assertTrue(any("ctrl-shift-k" in line and "kept" in line for line in lines))

    def test_a_typo_in_keys_json_stops_before_any_write(self) -> None:
        (self.home / "keys.json").write_text('{"global": {')
        before = ol.tree_state(self.home)
        with self.assertRaises(SystemExit) as raised:
            self.install()
        self.assertIn("keys.json is not valid JSON", str(raised.exception))
        self.assertEqual(ol.tree_state(self.home), before)
        self.assertFalse((self.home / ".ormus-look.json").exists())

    def test_programs_json_that_is_a_list_stops_with_a_message(self) -> None:
        self.write("programs.json", [1, 2])
        before = ol.tree_state(self.home)
        with self.assertRaises(SystemExit) as raised:
            self.install()
        self.assertIn("programs.json must hold a JSON object", str(raised.exception))
        self.assertEqual(ol.tree_state(self.home), before)

    def test_a_wrong_shape_inside_programs_json_stops_too(self) -> None:
        self.write("programs.json", {"programs": {"claude": "x"}})
        with self.assertRaises(SystemExit) as raised:
            self.install()
        self.assertIn("'claude' must be an object", str(raised.exception))

    def test_keys_json_that_is_a_list_stops(self) -> None:
        self.write("keys.json", [])
        with self.assertRaises(SystemExit) as raised:
            self.install()
        self.assertIn("keys.json must hold a JSON object", str(raised.exception))

    def test_check_finds_the_same_bad_files(self) -> None:
        (self.home / "keys.json").write_text("{")
        done = subprocess.run(
            [sys.executable, str(ROOT / "src/ormus_look.py"), "check", "--home", str(self.home),
             "--config", str(EXAMPLES / "spaces.json")], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("keys.json is not valid JSON", done.stderr)

    def test_a_failure_mid_install_leaves_undo_and_install_working(self) -> None:
        before = ol.tree_state(self.home)
        real = ol.write_json

        def boom(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        ol.write_json = boom  # type: ignore[assignment]
        try:
            with self.assertRaises(SystemExit) as raised:
                self.install()
        finally:
            ol.write_json = real  # type: ignore[assignment]
        self.assertIn("undo", str(raised.exception))
        self.assertTrue((self.home / ".ormus-look.json").is_file())
        self.install()  # a second install is not blocked
        ol.undo(self.home)
        self.assertEqual(ol.tree_state(self.home), before)

    def test_a_failure_then_undo_alone_cleans_up(self) -> None:
        before = ol.tree_state(self.home)
        real = ol.write_json

        def boom(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        ol.write_json = boom  # type: ignore[assignment]
        try:
            with self.assertRaises(SystemExit):
                self.install()
        finally:
            ol.write_json = real  # type: ignore[assignment]
        ol.undo(self.home)
        self.assertEqual(ol.tree_state(self.home), before)

    def test_undo_refuses_a_manifest_path_that_is_not_ours(self) -> None:
        self.install()
        manifest = json.loads((self.home / ol.MANIFEST).read_text())
        for bad in ("../outside", "/etc/passwd", "mods/spaces", "mods/ormus-x/y", "keys.json", "layouts/other.json"):
            with self.subTest(path=bad):
                (self.home / ol.MANIFEST).write_text(json.dumps({**manifest, "paths": [bad, *manifest["paths"]]}))
                with self.assertRaises(SystemExit):
                    ol.undo(self.home)
                self.assertTrue((self.home / "mods/ormus-chrome").is_dir())  # nothing was removed

    def test_without_keys_json_or_with_no_keys_the_bindings_are_printed(self) -> None:
        for make_file, keys in ((False, True), (True, False)):
            with self.subTest(file=make_file, keys=keys):
                home = self.tmp / f"home-{make_file}"
                shutil.copytree(EXAMPLES / "herdr-home", home)
                if not make_file:
                    (home / "keys.json").unlink()
                text = "\n".join(ol.install(self.config, home, keys))
                for word in ("ctrl-shift-s", "mod.open:ormus-search", "ctrl-shift-i", "ormus-needs.needs",
                             "ctrl-shift-g", "ormus-needs.overview", "ctrl-shift-j", "ormus-needs.sidebar",
                             "mod.open:ormus-picker"):
                    self.assertIn(word, text)

    def test_the_report_counts_the_real_edits(self) -> None:
        text = "\n".join(self.install())
        self.assertIn("mods/ormus-spaces/  main.js (3 edits)", text)
        self.assertIn("mods/ormus-picker/  main.js (3 edits)", text)
        self.assertIn("mods/ormus-pane/  main.js (10 edits)", text)
        src = (self.home / "mods/spaces/main.js").read_text()
        _, n = st.counted(lambda x: st.patch_spaces(x, "// shared\n"), src)
        self.assertEqual(n, 3)

    def test_generated_mods_carry_the_herdr_notice(self) -> None:
        self.install()
        for mod in ("ormus-spaces", "ormus-picker", "ormus-pane"):
            self.assertIn("Apache License 2.0", (self.home / "mods" / mod / "main.js").read_text().split("\n")[0])
        self.assertIn("Apache License 2.0", (ROOT / "mods/ormus-chrome/main.js").read_text().split("\n")[0])


class RepoContentTest(unittest.TestCase):
    def test_every_asset_a_mod_names_is_in_the_repo(self) -> None:
        ref = re.compile(r"""["'`](mods/([a-z0-9-]+)/([A-Za-z0-9_./-]+\.(?:svg|png|js|json|ttf)))["'`]""")
        sources = [*ROOT.glob("mods/*/*.js"), ROOT / "layouts/ormus.json", ROOT / "mods/ormus-chrome/programs.ormus.json"]
        seen = 0
        for file in sources:
            for m in ref.finditer(file.read_text()):
                seen += 1
                self.assertTrue(m.group(2).startswith("ormus-"), f"{file.name} loads {m.group(1)} from a Herdr folder")
                generated = m.group(1).startswith("mods/ormus-spaces/logos/")
                self.assertTrue(generated or (ROOT / m.group(1)).is_file(), f"{file.name}: {m.group(1)} is missing")
        self.assertGreater(seen, 3)
        icons = ROOT / "mods/ormus-chrome"
        for name in ("settings", "plus", "search", "sidebar", "spinner", "check"):
            self.assertTrue((icons / f"{name}.svg").is_file(), name)

    def test_the_licenses_are_shipped(self) -> None:
        lucide = (ROOT / "LICENSE-LUCIDE.txt").read_text()
        self.assertIn("ISC License", lucide)
        self.assertIn("The MIT License", lucide)
        self.assertIn("Cole Bemis", lucide)
        notice = (ROOT / "NOTICE").read_text()
        self.assertIn("no copyright line", notice)
        self.assertIn("not give the right to use them as another brand", notice)
        inter = (ROOT / "mods/ormus-chrome/fonts/Inter-OFL.txt").read_text().splitlines()[0]
        self.assertEqual(inter, "Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter)")

    def test_the_themes_are_valid_and_share_the_terminal_hues(self) -> None:
        fusion = ["#0b1226", "#d44f4f", "#8fb08a", "#d29e3d", "#6f93cf", "#a98bc2", "#6fa7a8", "#a5b0c4",
                  "#6d7891", "#e27a72", "#aecba7", "#e0b258", "#93b2e2", "#c4a9da", "#93c6c4", "#eceae3"]
        themes = sorted((ROOT / "themes").glob("ormus-*.json"))
        self.assertEqual([t.stem for t in themes], [
            "ormus-gold", "ormus-graphite", "ormus-jade", "ormus-quicksilver", "ormus-rust", "ormus-silver", "ormus-violet"])
        for file in themes:
            data = json.loads(file.read_text())
            hues = [1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14]  # the neutrals (0, 7, 8, 15) follow the theme
            self.assertEqual([data["ansi"][i] for i in hues], [fusion[i] for i in hues], file.name)
            colors = data["colors"]
            self.assertEqual(colors["blocked"], "#e27a72", file.name)
            for key in ("surface", "canvas", "chrome", "foreground", "working", "done", "idle", POINTER):
                self.assertRegex(colors.get(key, ""), r"^#[0-9a-f]{6,8}$", f"{file.name} {key}")
        self.assertEqual(
            st.ACCENTS,
            {"rose": "#e0849a", "teal": "#4fbcae", "leaf": "#86c272", "ember": "#e8955f", "sky": "#78a6ee", "iris": "#ad92e6"},
        )
        self.assertEqual(set(st.MARK_TO_ACCENT.values()), set(st.ACCENTS))

    def test_the_layout_names_mods_and_a_theme_that_exist(self) -> None:
        layout = json.loads((ROOT / "layouts/ormus.json").read_text())
        names: set[str] = set()

        def walk(node: object) -> None:
            if isinstance(node, dict):
                content = node.get("content")
                if isinstance(content, dict) and "mod" in content:
                    names.add(content["mod"])
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(layout)
        ours = {n for n in names if n.startswith("ormus-")}
        built = set(ol.PATCHED.values())
        for name in ours:
            self.assertTrue(name in built or (ROOT / "mods" / name / "main.js").is_file(), name)
        self.assertEqual(names - ours, {"agents", "changes", "files", "tabs", "workspace-status"})  # Herdr's own
        self.assertTrue((ROOT / "themes" / f"{layout['theme']}.json").is_file())
        self.assertEqual(layout["theme"], ol.DEFAULT_THEME)
        self.assertTrue((ROOT / layout["preview"]).is_file())

    def test_a_key_bound_in_global_blocks_a_layout_key(self) -> None:
        keys = {"global": {"ctrl-shift-i": "my.action"}}
        out, left = merge_home.add_keys(keys)
        self.assertTrue(any("ctrl-shift-i (yours in global" in x for x in left))
        self.assertNotIn("ctrl-shift-i", out.get("layout:ormus", {}))
        self.assertIn("ctrl-shift-g", out["layout:ormus"])


class DecodedScrubTest(unittest.TestCase):
    """M4: an escaped word is caught after decoding; only the one shielded word passes."""

    def run_scrub(self, text: str, deny: str = "zebra\n") -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "repo"
            folder.mkdir()
            (folder / "x.js").write_text(text)
            (Path(tmp) / "deny.txt").write_text(deny)
            env = {"PATH": "/usr/bin:/bin", "PLAYBOOK_DENYLIST": str(Path(tmp) / "deny.txt")}
            return subprocess.run([sys.executable, str(ROOT / "scripts/decoded_scrub.py"), str(folder)],
                                  capture_output=True, text=True, env=env)

    def test_an_escaped_deny_listed_word_is_caught(self) -> None:
        done = self.run_scrub("const a = 'ze" + "\\" + "u0062ra';\n")
        self.assertEqual(done.returncode, 1)
        self.assertIn("deny-list entry 1", done.stdout)
        self.assertNotIn("zebra", done.stdout)

    def test_a_braced_escape_is_caught_too(self) -> None:
        self.assertEqual(self.run_scrub("x = 'ze" + "\\" + "u{62}ra'\n").returncode, 1)

    def test_other_ways_to_spell_letters_are_refused(self) -> None:
        for text in ("'" + "\\" + "x7a" + "ebra'", "String.from" + "CharCode(122)", "chr" + "(122)", "&" + "#122;ebra"):
            with self.subTest(text=text):
                self.assertEqual(self.run_scrub(text + "\n").returncode, 1)

    def test_the_shielded_word_alone_passes(self) -> None:
        shielded = "hov" + "\\" + "u0065r"
        done = self.run_scrub(f"el.{shielded}(1);\n", deny=POINTER + "\n")
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_a_shielded_word_next_to_another_escaped_word_is_still_caught(self) -> None:
        shielded = "hov" + "\\" + "u0065r"
        done = self.run_scrub(f"{shielded} ze" + "\\" + "u0062ra\n", deny=POINTER + "\nzebra\n")
        self.assertEqual(done.returncode, 1)

    def test_the_repo_itself_passes(self) -> None:
        done = subprocess.run([sys.executable, str(ROOT / "scripts/decoded_scrub.py"), str(ROOT)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout)


class ManifestAndLinksTest(TempHome):
    """Re-review: a damaged manifest, odd settings files, symlinked folders, modes."""

    BAD = ["", '{"paths": [', "[]", '{"settings": []}', '{"paths": [1]}',
           '{"settings": {"programs.json": {"changes": [{"after": 1}]}}}',
           '{"settings": {"keys.json": {"added": "x"}}}']

    def test_a_damaged_manifest_stops_install_and_undo_with_a_message(self) -> None:
        for text in self.BAD:
            with self.subTest(manifest=text):
                (self.home / ol.MANIFEST).write_text(text)
                for action in (lambda: self.install(), lambda: ol.undo(self.home)):
                    with self.assertRaises(SystemExit) as raised:
                        action()
                    self.assertIn(ol.MANIFEST, str(raised.exception))
                self.assertFalse((self.home / "mods/ormus-chrome").exists())

    def test_the_manifest_is_written_in_one_step(self) -> None:
        self.install()
        self.assertEqual(list(self.home.glob("*.tmp-ormus")), [])
        self.assertIsNone(ol.manifest_problem(json.loads((self.home / ol.MANIFEST).read_text())))

    @unittest.skipIf(hasattr(__import__("os"), "geteuid") and __import__("os").geteuid() == 0, "root ignores modes")
    def test_a_read_only_home_gives_a_message_not_a_traceback(self) -> None:
        self.home.chmod(0o555)
        try:
            with self.assertRaises(SystemExit) as raised:
                self.install()
        finally:
            self.home.chmod(0o755)
        self.assertNotIsInstance(raised.exception.code, int)

    def test_undo_skips_a_settings_file_that_is_no_longer_an_object(self) -> None:
        for name, text in (("keys.json", "[]"), ("programs.json", "3"), ("keys.json", '"x"')):
            with self.subTest(file=name, text=text):
                home = self.tmp / f"h-{name}-{len(text)}"
                shutil.copytree(EXAMPLES / "herdr-home", home)
                ol.install(self.config, home, True)
                (home / name).write_text(text)
                lines = ol.undo(home)
                self.assertTrue(any(name in x and "kept as it is" in x for x in lines), lines)
                self.assertEqual((home / name).read_text(), text)
                self.assertFalse((home / "mods/ormus-chrome").exists())

    def test_symlinked_mods_and_layouts_folders_work(self) -> None:
        elsewhere = self.tmp / "dotfiles"
        for name in ("mods", "layouts", "themes"):
            (elsewhere).mkdir(exist_ok=True)
            if (self.home / name).exists():
                shutil.move(str(self.home / name), str(elsewhere / name))
            else:
                (elsewhere / name).mkdir()
            (self.home / name).symlink_to(elsewhere / name)
        self.install()
        self.assertTrue((elsewhere / "mods/ormus-chrome/main.js").is_file())
        ol.undo(self.home)
        self.assertFalse((elsewhere / "mods/ormus-chrome").exists())
        self.assertTrue((elsewhere / "mods/spaces/main.js").is_file())

    def test_a_link_as_the_last_part_must_point_inside_the_home(self) -> None:
        self.install()
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        shutil.rmtree(self.home / "mods/ormus-search")
        (self.home / "mods/ormus-search").symlink_to(outside)
        with self.assertRaises(SystemExit):
            ol.undo(self.home)
        self.assertTrue((outside / "keep.txt").is_file())
        (self.home / "mods/ormus-search").unlink()
        (self.home / "mods/inside").mkdir()
        (self.home / "mods/ormus-search").symlink_to(self.home / "mods/inside")
        ol.undo(self.home)  # removes the link, not the folder it points to
        self.assertTrue((self.home / "mods/inside").is_dir())
        self.assertFalse((self.home / "mods/ormus-search").exists())

    def test_odd_action_shapes_in_keys_json_do_not_crash_install(self) -> None:
        keys = json.loads((self.home / "keys.json").read_text())
        keys["global"]["a"] = {"command": "mod.open", "args": "picker"}
        keys["global"]["b"] = {"command": "mod.open", "args": ["picker"]}
        keys["global"]["c"] = {"command": "mod.open", "args": None}
        keys["global"]["d"] = 5
        (self.home / "keys.json").write_text(json.dumps(keys))
        self.install()
        after = json.loads((self.home / "keys.json").read_text())
        self.assertEqual(after["global"]["a"], {"command": "mod.open", "args": "picker"})
        self.assertEqual(after["global"]["ctrl-shift-k"], "mod.open:ormus-picker")

    def test_a_mode_and_a_symlink_survive_the_write(self) -> None:
        real = self.tmp / "dotfiles-keys.json"
        shutil.move(str(self.home / "keys.json"), real)
        (self.home / "keys.json").symlink_to(real)
        real.chmod(0o600)
        self.install()
        self.assertTrue((self.home / "keys.json").is_symlink())
        self.assertEqual(real.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(real.read_text())["global"]["ctrl-shift-k"], "mod.open:ormus-picker")
        ol.undo(self.home)
        self.assertTrue((self.home / "keys.json").is_symlink())
        self.assertEqual(real.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(real.read_text())["global"]["ctrl-shift-k"], "mod.open:picker")

    def test_a_bad_path_in_the_manifest_does_not_survive_a_new_install(self) -> None:
        self.install()
        manifest = json.loads((self.home / ol.MANIFEST).read_text())
        manifest["paths"].append("../outside")
        (self.home / ol.MANIFEST).write_text(json.dumps(manifest))
        lines = self.install()
        self.assertTrue(any("dropped '../outside'" in x for x in lines))
        self.assertNotIn("../outside", json.loads((self.home / ol.MANIFEST).read_text())["paths"])
        ol.undo(self.home)

    def test_the_readme_warns_that_undo_removes_everything_in_the_mod_folders(self) -> None:
        text = (ROOT / "README.md").read_text()
        self.assertIn("including files you put there", text)


class DecodedScrubMoreTest(unittest.TestCase):
    BS = "\\"

    def run_scrub(self, text: str, deny: str = "zebra\n", name: str = "x.js") -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "repo"
            folder.mkdir()
            (folder / name).write_text(text)
            (Path(tmp) / "deny.txt").write_text(deny)
            env = {"PATH": "/usr/bin:/bin", "PLAYBOOK_DENYLIST": str(Path(tmp) / "deny.txt")}
            return subprocess.run([sys.executable, str(ROOT / "scripts/decoded_scrub.py"), str(folder)],
                                  capture_output=True, text=True, env=env)

    def test_a_multi_word_entry_with_the_shielded_word_is_still_matched(self) -> None:
        shield = "hov" + self.BS + "u0065r"
        deny = POINTER + " zebra\n"
        for text in (f"{shield} zebra", f"{shield}-zebra", f"{shield}zebra", f"{shield} ze" + self.BS + "u0062ra"):
            with self.subTest(text=text):
                done = self.run_scrub(text + "\n", deny=deny)
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("deny-list entry 1", done.stdout)
                self.assertNotIn("zebra", done.stdout)

    def test_an_exact_entry_still_lets_the_one_spelling_through_and_not_another(self) -> None:
        shield = "hov" + self.BS + "u0065r"
        self.assertEqual(self.run_scrub(shield + "(1)\n", deny=POINTER + "\n").returncode, 0)
        other = "h" + self.BS + "u006fver"
        self.assertEqual(self.run_scrub(other + "(1)\n", deny=POINTER + "\n").returncode, 1)

    def test_more_ways_to_spell_letters_are_refused(self) -> None:
        bs = self.BS
        cases = {
            "x.js": ["'" + bs + "U00000062'", "'" + bs + "N{LATIN SMALL LETTER B}'", "'" + bs + "142'", "'" + bs + bs + "u0062'",
                     "&" + "#98", "'%7a" + "%65'", "at" + "ob('x')", "un" + "escape('x')", "decodeURI" + "Component('x')",
                     "bytes.from" + "hex('62')", "ro" + "t13('x')"],
            "x.css": ["a::before { content: '" + bs + "62'; }"],
        }
        for name, texts in cases.items():
            for text in texts:
                with self.subTest(file=name, text=text):
                    self.assertEqual(self.run_scrub(text + "\n", name=name).returncode, 1)

    def test_an_impossible_code_point_is_a_finding_not_a_crash(self) -> None:
        done = self.run_scrub("'" + self.BS + "u{FFFFFF}'\n")
        self.assertEqual(done.returncode, 1)
        self.assertIn("invalid-escape", done.stdout)
        self.assertNotIn("Traceback", done.stderr)

    def test_a_lookalike_letter_in_code_is_flagged_but_not_in_prose(self) -> None:
        cyrillic = "z\u0435bra"
        self.assertEqual(self.run_scrub(f"x = '{cyrillic}'\n").returncode, 1)
        self.assertEqual(self.run_scrub(f"{cyrillic}\n", name="notes.txt").returncode, 0)
        self.assertEqual(self.run_scrub("x = 'a \u00b7 b'\n").returncode, 0)  # a middle dot is not a letter


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
