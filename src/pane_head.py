"""Pane names, the spotlight button and the overview: Herdr's `pane` header mod, extended.

Herdr's pane header shows an agent's program name, so every Claude pane reads
"Claude Code". This module makes `ormus-pane` from Herdr's own mod (the copy in
your Herdr home, mods/pane/) with anchored edits: when the pane's terminal carries the
label `ormus.title`, the header shows that name, and in the dim part the
terminal's own title (what the agent says it is on) in place of the folder.
Panes without the label look as Herdr draws them.

Name a pane:   hc label <terminal> ormus.title="Fix login test"
Clear a name:  hc label <terminal> ormus.title=

A pane whose terminal has the label `ormus.spotlight` (a command as a JSON list,
e.g. ["python3", "/path/to/focus.py", "t52"]) gets a "Spotlight" button
in its header; the button, or a double-click on the header, runs that command on
the pane's machine (the space's `machine`). A failed run shows a toast. A tool
that arranges a tab can set and clear the label.

Overview: the first pane of a tab with OVERVIEW_MIN or more terminal panes gets an
"Overview" button. It opens a window over the app with every terminal of the tab
in an equal grid at a smaller text size (Herdr draws a tab's own panes at one
size, but a window's layout takes `font_size`), each with this same header. The
window's top bar (this mod with the prop `overview`) has a Close button. In the
window a header click focuses that cell's terminal, the split/zoom/close buttons
are left out, and a Spotlight run that succeeds closes the window.

Each edit asserts its anchor, so a Herdr update that moves the code stops the
build instead of shipping a broken mod.
"""

from __future__ import annotations

from space_tiles import edit

LABEL = "ormus.title"
SPOT_LABEL = "ormus.spotlight"
OVERVIEW_MIN = (
    4  # terminal panes in a tab before its first pane shows the Overview button
)
OVERVIEW_FONT = 11  # px at zoom 1, the terminals in the overview window

NAME_JS = f"""
// Ormus: the pane's own name, from its terminal's label "{LABEL}" (hc label <t> {LABEL}=...).
function ormusName(p) {{
  if (!p.terminal) return "";
  const rec = terminals().find((x) => x.address === p.terminal);
  const v = rec?.labels?.["{LABEL}"];
  return typeof v === "string" ? v.trim() : "";
}}

// Ormus: the command the pane's spotlight button runs, from the label "{SPOT_LABEL}" (a JSON list).
function ormusSpot(p) {{
  if (!p.terminal) return null;
  const rec = terminals().find((x) => x.address === p.terminal);
  const v = rec?.labels?.["{SPOT_LABEL}"];
  if (typeof v !== "string" || !v.trim()) return null;
  try {{
    const argv = JSON.parse(v);
    return Array.isArray(argv) && argv.length > 0 && argv.every((a) => typeof a === "string" && a) ? argv : null;
  }} catch {{
    return null;
  }}
}}

// The machine of the pane's space (null: this computer), where its command runs.
function ormusMachine(p) {{
  return spaces().find((s) => s.tabs.some((t) => t.id === p.tab))?.machine ?? null;
}}

// Ormus: the overview window's layout: a top bar, then every terminal pane of the tab in an equal grid,
// each cell this header (props: pane, terminal) over its terminal, at a smaller text size.
function ormusOverview(tab, title) {{
  const cells = panes().filter((x) => x.tab === tab && x.terminal);
  const cols = Math.max(1, Math.ceil(Math.sqrt(cells.length)));
  const line = {{ width: 1, color: "border" }};
  const rows = [];
  for (let i = 0; i < cells.length; i += cols) {{
    rows.push({{
      id: `ov-r${{i / cols}}`,
      type: "row",
      divider: line,
      children: cells.slice(i, i + cols).map((c, j) => ({{
        id: `ov-c${{i + j}}`,
        type: "column",
        children: [
          {{ id: `ov-h${{i + j}}`, type: "block", size: {{ px: 30 }}, content: {{ mod: "ormus-pane", props: {{ pane: c.pane, terminal: c.terminal }} }} }},
          {{ id: `ov-t${{i + j}}`, type: "block", content: {{ terminal: c.terminal }} }},
        ],
      }})),
    }});
  }}
  return {{
    id: "ov-root",
    type: "column",
    font_size: {OVERVIEW_FONT},
    background: "background",
    children: [
      {{ id: "ov-bar", type: "block", size: {{ px: 36 }}, content: {{ mod: "ormus-pane", props: {{ overview: true, title, count: cells.length }} }} }},
      {{ id: "ov-grid", type: "column", divider: line, children: rows }},
    ],
  }};
}}

// Ormus: the pane that carries its tab's Overview button: the first terminal pane of a busy tab.
function ormusOverviewHere(p) {{
  const cells = panes().filter((x) => x.tab === p.tab && x.terminal);
  return cells.length >= {OVERVIEW_MIN} && cells[0].pane === p.pane;
}}
"""

SPOT_METHOD = """
  // Ormus: a small always-shown button in the header.
  pill(t, id, text, tip, onClick) {
    return div()
      .id(id)
      .flex_none()
      .px(6)
      .h(18)
      .flex()
      .items_center()
      .rounded(5)
      .border(1)
      .border_color(t.border)
      .text_size(10.5)
      .font_medium()
      .text_color(t.dim)
      .hov\u0065r((s) => s.bg(t.hov\u0065r).text_color(t.foreground))
      .tooltip(tip)
      .on_click((_e, cx) => {
        cx.stop_propagation();
        onClick(cx);
      })
      .child(text);
  }

  // Ormus: run the pane's spotlight command; a failure shows a toast. In the overview window, a run that
  // succeeds closes the window.
  spotlight(argv, on, cx) {
    if (this.busy) return;
    const overlay = props()?.overlay;
    this.busy = true;
    cx.notify();
    cx.spawn(async (cx) => {
      let ok = false;
      try {
        const r = await exec(argv[0], argv.slice(1), { on, timeout: 60000 });
        ok = r.code === 0;
        if (!ok) {
          notify({ title: "Spotlight failed", body: (r.stderr || r.stdout || `exit ${r.code}`).trim().slice(0, 300), level: "error" });
        }
      } catch (e) {
        notify({ title: "Spotlight failed", body: String(e?.message ?? e), level: "error" });
      }
      if (ok && overlay) {
        closeOverlay(overlay); // this view goes with the window: nothing of it is touched after this
        return;
      }
      this.busy = false;
      cx.notify();
    });
  }

  spotButton(t, pane, argv, on) {
    return this.pill(t, `ph-s-${pane}`, this.busy ? "Moving..." : "Spotlight",
      "Show this pane in the spotlight (or double-click the header)", (cx) => this.spotlight(argv, on, cx));
  }

  overviewButton(t, p) {
    const tab = spaces().flatMap((s) => s.tabs).find((x) => x.id === p.tab);
    return this.pill(t, `ph-o-${p.pane}`, "Overview", "Every pane of this tab in one window, smaller text", () =>
      openOverlay({ kind: "dialog", width: 0.98, height: 0.96, layout: ormusOverview(p.tab, tab?.name ?? "") }));
  }

  // Ormus: the overview window's top bar (props: overview, title, count, overlay).
  overviewBar(t) {
    const pr = props();
    return h_flex()
      .id("ov-bar")
      .size_full()
      .px(12)
      .gap(10)
      .items_center()
      .bg(t.chrome)
      .border_b(1)
      .border_color(t.border)
      .text_size(12)
      .child(div().flex_none().font_medium().text_color(t.foreground).child(`Overview: ${pr.title || "this tab"}`))
      .child(div().flex_1().truncate().text_color(t.dim).child(`${pr.count} panes. Click a pane to type in it.`))
      .child(this.pill(t, "ov-close", "Close", "Close the overview", () => closeOverlay(pr.overlay)));
  }
"""

UPSTREAM_NAME = (
    "const name = ((p.program?.agent || p.program?.shell) && p.program.name) "
    '|| p.title || p.program?.name || "shell";'
)


HEAD_COMMENT = (
    "// Ormus (playbook-herdr-ormus-look, src/pane_head.py): a pane whose terminal has the label\n"
    f"// {LABEL} shows that name, and the agent's own title in place of the folder\n"
    '// (the folder when the title is empty or the same). Layout: { "mod": "ormus-pane" }.\n'
    f"// A pane whose terminal has the label {SPOT_LABEL} (a command, JSON list) gets a\n"
    "// Spotlight button; it, or a double-click on the header, runs it on the pane's machine.\n"
    f"// The first pane of a tab with {OVERVIEW_MIN}+ terminal panes gets an Overview button: every\n"
    "// terminal of the tab in a grid window (this mod draws its cells' headers and its top bar).\n"
)


def patch_pane(src: str) -> str:
    s = edit(
        src,
        "// A pane's header, for layouts that frame their panes:\n",
        HEAD_COMMENT + "// A pane's header, for layouts that frame their panes:\n",
        "the header comment",
    )
    s = edit(
        s,
        'import { panes, props, run, theme, home, layout } from "herdr";',
        'import { panes, props, run, theme, home, layout, terminals, spaces, exec, notify, openOverlay, closeOverlay } from "herdr";',
        "the herdr import",
    )
    s = edit(
        s,
        "export default class Pane extends View {",
        NAME_JS.lstrip("\n") + "\nexport default class Pane extends View {",
        "the Pane class",
    )
    s = edit(
        s,
        "  init() { this.hovered = false; }\n",
        "  init() { this.hovered = false; this.busy = false; }\n" + SPOT_METHOD,
        "the init method",
    )
    s = edit(
        s,
        "    return panes().find((p) => p.pane === props()?.pane);\n",
        "    const pr = props();\n"
        "    // Ormus: an overview cell finds its pane by terminal too (a new layout gives panes new ids).\n"
        "    return panes().find((p) => p.pane === pr?.pane)"
        " ?? (pr?.terminal ? panes().find((p) => p.terminal === pr.terminal) : undefined);\n",
        "the pane lookup",
    )
    s = edit(
        s,
        "    const t = theme();\n    const p = this.me();\n",
        "    const t = theme();\n"
        "    if (props()?.overview) return this.overviewBar(t);\n"
        "    const inOverlay = Boolean(props()?.overlay);\n"
        "    const p = this.me();\n",
        "the render start",
    )
    s = edit(
        s,
        UPSTREAM_NAME,
        "const own = ormusName(p);\n    const spot = ormusSpot(p);\n    const name = own || "
        + UPSTREAM_NAME.removeprefix("const name = "),
        "the pane name",
    )
    s = edit(
        s,
        '.on_click(() => run("pane.focus", { pane }))',
        ".on_click((e, cx) => {\n"
        '        run("pane.focus", inOverlay ? { terminal: p.terminal } : { pane });\n'
        "        if (spot && e?.click_count === 2) this.spotlight(spot, ormusMachine(p), cx);\n"
        "      })",
        "the header click",
    )
    s = edit(
        s,
        "      .when(this.hovered, el => el\n",
        "      .when(Boolean(spot), el => el.child(this.spotButton(t, pane, spot, ormusMachine(p))))\n"
        "      .when(!inOverlay && ormusOverviewHere(p), el => el.child(this.overviewButton(t, p)))\n"
        "      .when(this.hovered && !inOverlay, el => el\n",
        "the buttons that show under the pointer",
    )
    return edit(
        s,
        ".child(div().flex_1().truncate().text_color(t.dim).child(folder(p.cwd)))",
        ".child(div().flex_1().truncate().text_color(t.dim)"
        ".child(own && p.title && p.title !== own ? p.title : folder(p.cwd)))",
        "the folder line",
    )
