// Search all terminals (ctrl-shift-s). Herdr's own find bar (ctrl-shift-f) searches one terminal;
// this dialog searches the screen and history of every terminal in a tab, on every machine, at once.
// It reads each one with `hc read` (READERS at a time) when it opens, so results come in as the
// terminals are read, and typing filters what is read with no new reads. Type 2 or more characters,
// up/down to pick a line, Enter (or a click) to go there: the tab shows, the terminal gets the focus
// and its view scrolls to put that line in the middle. Esc closes. Hand-written (playbook-herdr-ormus-look).

import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex, InputState, Input, Scrollbar, v_virtual_list, VirtualListScrollHandle } from "gpui-base";
import { panes, spaces, exec, hc, run, theme, settings, props, closeOverlay } from "herdr";

const HISTORY_LINES = 10000; // lines of history above the screen read from each terminal
const READERS = 12; // terminals read at the same time (measured: 322 terminals in 21 s with 16)
const READ_TIMEOUT_MS = 15000; // a read that has not answered by then counts as failed
const TYPE_PAUSE_MS = 120; // the search runs when typing pauses this long (one pass over every text)
const MAX_HITS_PER_TERMINAL = 30; // lines shown per terminal; the rest is counted
const HEAD_H = 30;
const HIT_H = 24;
const MORE_H = 22;
const LIST_MAX_H = 520;

// --- pure helpers (test/test_search.py runs them in node) ---
const MIN_QUERY = 2; // characters before a search starts
const SNIPPET_BEFORE = 36; // characters of a line shown before the match

/** The terminals to search, in the sidebar's order (space, tab, pane), each once. */
function searchTargets(spaceList, paneList) {
  const out = [];
  const seen = new Set();
  for (const s of spaceList) {
    for (const tab of s.tabs ?? []) {
      for (const p of paneList) {
        if (p.tab !== tab.id || !p.terminal || seen.has(p.terminal)) continue;
        seen.add(p.terminal);
        out.push({ terminal: p.terminal, tab: tab.id, space: s.name, tabName: tab.name, title: p.title ?? "" });
      }
    }
  }
  return out;
}

/** `hc read` output as lines: no carriage returns, hc's own "[hc]" notes blanked (not removed, so
 *  every other line keeps its place), and no empty line after the last newline. */
function readLines(stdout) {
  const lines = String(stdout ?? "").replace(/\r/g, "").split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines.map((l) => (/^\[hc\]/.test(l.trim()) ? "" : l));
}

/** A query as a case-insensitive pattern that matches its text literally, or null when too short. */
function queryPattern(query) {
  if (String(query ?? "").trim().length < MIN_QUERY) return null;
  return new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "giu");
}

/** The lines of `text` that match `re`: one hit per line, at its first match, at most `max`;
 *  `more` counts the matching lines past `max`. */
function findHits(text, re, max) {
  const hits = [];
  let more = 0;
  let line = 0;
  let lineStart = 0;
  re.lastIndex = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    let nl = text.indexOf("\n", lineStart);
    while (nl !== -1 && nl < m.index) {
      line++;
      lineStart = nl + 1;
      nl = text.indexOf("\n", lineStart);
    }
    const end = nl === -1 ? text.length : nl;
    if (hits.length < max) hits.push({ line, col: m.index - lineStart, len: m[0].length, text: text.slice(lineStart, end) });
    else more++;
    if (end >= text.length) break;
    re.lastIndex = end + 1; // the next line
  }
  return { hits, more };
}

/** A hit's line cut for one row: up to `before` characters before the match. */
function snippet(text, col, len, before) {
  let start = Math.max(0, col - before);
  const c = text.charCodeAt(start);
  if (start > 0 && c >= 0xdc00 && c <= 0xdfff) start--; // not half of an emoji
  const lead = text.slice(start, col);
  return {
    cut: start > 0,
    before: start > 0 ? lead : lead.trimStart(),
    hit: text.slice(col, col + len),
    after: text.slice(col + len).trimEnd(),
  };
}

/** Where line `line` of an earlier read (`old`) is in a fresh read (`lines`): of the lines with its
 *  text, the one whose neighbors (3 above, 3 below) match most; on a tie, the one nearest to where it
 *  should be (`grown` more lines than before; a full history drops old lines instead, so the neighbors
 *  decide there). -1 when it is gone (a program redrew its screen). */
function relocate(lines, old, line, grown) {
  const text = old[line];
  const guess = line + grown;
  let best = -1;
  let bestScore = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i] !== text) continue;
    let score = 0;
    for (let k = -3; k <= 3; k++) {
      if (k && old[line + k] !== undefined && lines[i + k] === old[line + k]) score++;
    }
    if (score > bestScore || (score === bestScore && Math.abs(i - guess) < Math.abs(best - guess))) {
      best = i;
      bestScore = score;
    }
  }
  return best;
}

/** The `terminal.scroll` lines (negative: up into the history) that put line `line` of a read of
 *  `total` lines in the middle of the view; the last `rows` lines are the screen. 0: it is on screen. */
function scrollLines(total, line, rows) {
  const below = total - 1 - line;
  if (below < rows) return 0;
  return -(below - Math.floor(rows / 2));
}
// --- end of pure helpers ---

// `exec` ends a call that hangs; it rejects at once when it cannot start `hc` (not on PATH): then the
// app's own `hc` runs it. A later rejection (a timeout) is a failure, not a retry with no time limit.
function hcRun(args) {
  const started = Date.now();
  return exec("hc", args, { timeout: READ_TIMEOUT_MS }).catch((e) => {
    if (Date.now() - started < 1000) return hc(args);
    throw e;
  });
}

function read(terminal) {
  return hcRun(["read", terminal, "--lines", String(HISTORY_LINES)]);
}

export default class SearchTerminals extends View {
  init(_props, cx) {
    this.query = "";
    this.pattern = null;
    this.input = InputState.new({ placeholder: "Search the text of every terminal…" });
    this.input.on("change", (_e, cx) => {
      const typed = this.input.value();
      cx.timer.after(TYPE_PAUSE_MS, (cx) => {
        if (this.ended || typed !== this.input.value()) return; // still typing
        this.search(typed);
        cx.notify();
      });
    });
    this.input.on("submit", (_e, cx) => {
      if (this.input.value() !== this.query) this.search(this.input.value());
      this.go(this.picked(), cx);
    });
    this.input.focus();
    cx.timer.after(600, () => this.input.focus());
    this.handle = cx.focus_handle();
    this.scroll = VirtualListScrollHandle.new();
    this.targets = searchTargets(spaces(), panes());
    this.texts = new Map(); // terminal -> { text, total }
    this.hits = new Map();
    this.failed = 0;
    this.done = 0;
    this.at = 0;
    this.pickKey = null; // the picked line, by its key: lines read later can come in above it
    this.ended = false;
    this.note = null;
    this.readAll(cx);
  }

  search(query) {
    this.query = query;
    this.pattern = queryPattern(query);
    this.hits = new Map(); // terminal -> findHits(), for this query
    this.at = 0;
    this.pickKey = null;
    this.scroll.scroll_to_item(0);
  }

  // The host closes this copy: the readers stop at their next terminal.
  close() {
    this.ended = true;
  }

  leave() {
    this.ended = true;
    closeOverlay(props().overlay);
  }

  readAll(cx) {
    const queue = [...this.targets];
    cx.spawn(async (cx) => {
      const reader = async () => {
        while (queue.length && !this.ended) {
          const tg = queue.shift();
          try {
            const r = await read(tg.terminal);
            if (r.code === 0) {
              const lines = readLines(r.stdout);
              this.texts.set(tg.terminal, { text: lines.join("\n"), total: lines.length });
            } else this.failed++;
          } catch {
            this.failed++;
          }
          this.done++;
          if (!this.ended) cx.notify();
        }
      };
      await Promise.all(Array.from({ length: READERS }, reader));
    });
  }

  /** The terminals with hits for the query, in the sidebar's order. */
  results() {
    if (!this.pattern) return [];
    const out = [];
    for (const tg of this.targets) {
      const got = this.texts.get(tg.terminal);
      if (!got) continue;
      if (!this.hits.has(tg.terminal)) this.hits.set(tg.terminal, findHits(got.text, this.pattern, MAX_HITS_PER_TERMINAL));
      const r = this.hits.get(tg.terminal);
      if (r.hits.length) out.push({ tg, ...r });
    }
    return out;
  }

  rows() {
    const rows = [];
    for (const r of this.results()) {
      rows.push({ kind: "head", key: `h ${r.tg.terminal}`, r });
      r.hits.forEach((h, k) => rows.push({ kind: "hit", key: `l ${r.tg.terminal} ${h.line} ${k}`, r, h }));
      if (r.more) rows.push({ kind: "more", key: `m ${r.tg.terminal}`, r });
    }
    return rows;
  }

  picked() {
    const pickable = this.rows().filter((r) => r.kind === "hit");
    return pickable.find((r) => r.key === this.pickKey) ?? pickable[this.at];
  }

  // Show the terminal; for a line, read it again (it may have printed more since) and scroll there.
  go(row, cx) {
    if (!row || row.kind === "more" || this.going) return;
    const { tg } = row.r;
    const h = row.kind === "hit" ? row.h : null;
    this.going = true;
    this.note = "Opening…";
    cx.notify();
    cx.spawn(async (cx) => {
      let lines = null;
      let rows = null;
      if (h) {
        try {
          const [r, g] = await Promise.all([read(tg.terminal), hcRun(["get", tg.terminal, "--json"])]);
          if (r.code === 0) lines = readLines(r.stdout);
          if (g.code === 0) rows = JSON.parse(g.stdout).rows ?? null;
        } catch {}
      }
      this.leave();
      run("tab.select", { id: tg.tab });
      run("pane.focus", { terminal: tg.terminal });
      if (h && lines && rows) {
        const before = this.texts.get(tg.terminal);
        const at = before ? relocate(lines, before.text.split("\n"), h.line, lines.length - before.total) : -1;
        if (at >= 0) {
          run("terminal.scroll", { to: "bottom", terminal: tg.terminal });
          const n = scrollLines(lines.length, at, rows);
          if (n) run("terminal.scroll", { lines: n, terminal: tg.terminal });
        }
      }
    });
  }

  row(r, on, t, mono) {
    if (r.kind === "head") {
      const n = r.r.hits.length + r.r.more;
      return h_flex().h(HEAD_H).px(10).pt(8).gap(8).items_center().text_size(11.5)
        .child(div().flex_none().font_semibold().text_color(t.muted).child(`${r.r.tg.space} · ${r.r.tg.tabName}`))
        .child(div().flex_1().min_w(0).truncate().text_color(t.dim).child(r.r.tg.title))
        .child(div().flex_none().text_size(11).text_color(t.dim).child(`${n} line${n === 1 ? "" : "s"}`));
    }
    if (r.kind === "more") {
      return h_flex().h(MORE_H).px(24).items_center().text_size(11).text_color(t.dim)
        .child(`${r.r.more} more line${r.r.more === 1 ? "" : "s"} here: type more to narrow the search`);
    }
    const s = snippet(r.h.text, r.h.col, r.h.len, SNIPPET_BEFORE);
    return h_flex().h(HIT_H).mx(4).px(14).rounded(6).items_center().overflow_hidden().cursor_pointer()
      .font_family(mono).text_size(11.5).text_color(t.muted)
      .when(on, (el) => el.bg(t.selected).text_color(t.foreground))
      .hov\u0065r((st) => st.bg(t.hov\u0065r))
      .when(s.cut, (el) => el.child(div().flex_none().text_color(t.dim).child("…")))
      .child(div().flex_none().whitespace_nowrap().child(s.before))
      .child(div().flex_none().whitespace_nowrap().rounded(3).bg(t.selection).text_color(t.foreground).child(s.hit))
      .child(div().flex_1().min_w(0).truncate().child(s.after));
  }

  render() {
    const t = theme();
    const mono = settings().font_family ?? "JetBrains Mono";
    const rows = this.rows();
    const pickable = rows.filter((r) => r.kind === "hit");
    const kept = this.pickKey ? pickable.findIndex((r) => r.key === this.pickKey) : -1;
    this.at = kept >= 0 ? kept : Math.max(0, Math.min(this.at, pickable.length - 1));
    const sel = pickable[this.at];
    this.pickKey = sel?.key ?? null;
    const heights = rows.map((r) => (r.kind === "head" ? HEAD_H : r.kind === "more" ? MORE_H : HIT_H));
    const total = heights.reduce((a, b) => a + b, 0);
    const reading = this.done < this.targets.length;
    const lines = pickable.length + rows.filter((r) => r.kind === "more").reduce((a, r) => a + r.r.more, 0);
    const where = rows.filter((r) => r.kind === "head").length;
    const progress = reading ? `Reading ${this.done} of ${this.targets.length} terminals…` : `${this.targets.length} terminals read`;
    const failed = this.failed ? ` · ${this.failed} could not be read` : "";
    const found = !this.pattern
      ? `Type ${MIN_QUERY} or more characters.`
      : lines
        ? `${lines} line${lines === 1 ? "" : "s"} in ${where} terminal${where === 1 ? "" : "s"}`
        : reading
          ? "No match yet."
          : "No terminal shows this text.";
    const move = (to, cx) => {
      this.at = to;
      this.pickKey = pickable[to].key;
      this.scroll.scroll_to_item(rows.indexOf(pickable[to]), "center");
      cx.notify();
    };

    return v_flex()
      .id("ormus-search")
      .track_focus(this.handle)
      .w_full()
      .min_h(0)
      .p(18)
      .gap(10)
      .bg(t.popover)
      .text_size(13)
      .on_key_down((e, cx) => {
        const k = e.key;
        if (k === "escape") return this.leave();
        if (!pickable.length) return;
        if (k === "down") move((this.at + 1) % pickable.length, cx);
        else if (k === "up") move((this.at + pickable.length - 1) % pickable.length, cx);
        else return;
        cx.stop_propagation();
      })
      .child(h_flex().items_center()
        .child(div().flex_1().text_size(15).font_semibold().text_color(t.foreground).child("Search all terminals"))
        .child(div().id("search-esc").px(6).py(2).rounded(5).text_size(11).text_color(t.dim).cursor_pointer()
          .hov\u0065r((s) => s.bg(t.hov\u0065r).text_color(t.foreground)).on_click(() => this.leave()).child("Esc")))
      .child(h_flex().h(36).flex_none().px(10).gap(8).items_center().rounded(9).border_1().border_color(t.accent).bg(t.background)
        .child(svg("mods/ormus-chrome/search.svg").size(15).text_color(t.dim))
        .child(Input.new(this.input).flex_1().h_full().text_size(12.8).text_color(t.foreground)))
      .child(h_flex().gap(8).text_size(11.5).text_color(t.dim)
        .child(div().flex_1().child(found))
        .child(div().child(this.note ?? progress + failed)))
      .when(rows.length > 0, (el) => el.child(div().relative().h(Math.min(LIST_MAX_H, total)).min_h(0)
        .child(v_virtual_list("search-hits", rows.length, heights, (i) => rows[i].key,
          (range) => rows.slice(range.start, range.end).map((r) => this.row(r, r === sel, t, mono)))
          .size_full().track_scroll(this.scroll)
          .on_item_click((key, cx) => {
            const r = rows.find((x) => x.key === key);
            if (r?.kind === "hit") {
              this.at = pickable.indexOf(r);
              this.pickKey = r.key;
            }
            this.go(r, cx);
          }))
        .child(Scrollbar.vertical("search-hits").absolute().inset_0())))
      .child(div().text_size(11).text_color(t.dim).child("↑↓ pick a line · Enter goes there · Esc closes · ctrl-shift-f finds in one terminal"));
  }
}
