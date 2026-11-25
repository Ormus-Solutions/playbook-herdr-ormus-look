// Ormus needs (playbook-herdr-ormus-look mods/ormus-needs): what waits for Ormus, across every space of every machine.
// Ideas from Flockbook (github.com/minchenlee/flockbook, MIT): its Needs view and its Overview; written anew here.
//   sidebar block: { "content": { "mod": "ormus-needs", "props": { "view": "bar" } } }
// Views (props.view):
//   "bar"      two rows in the sidebar: "Needs you" with its counts and "Overview". A click, or the keys
//              (ormus-needs.needs, ormus-needs.overview in keys.json), opens the view as a dialog.
//   "needs"    the agents that wait for the person (status "blocked") and the ones that finished while
//              nobody looked ("done": a Claude agent that ends its turn with a question shows "done", not
//              "blocked"). The picked one shows its real screen, read with `hc read`, so the question on
//              screen is what the view shows. "Go to it" focuses that agent; "Peek" shows its terminal over
//              the tab. When the screen shows a menu (Claude Code's numbered choices with the ❯ selector), its
//              choices are buttons; a reply box sends words. The view types into an agent only on the
//              person's press, and only after it read the screen again and found the same question.
//              Keys: up/down (j/k) pick, 1-9 answer, / types, Enter goes to it, p peeks.
//   "overview" every tab of every space as a card, grouped by status or by space, with the age of its state.
//              A click shows that tab. Keys: arrows (h/j/k/l) move, Enter shows the tab, s groups.
//   "spaces"   the Flock sidebar (an idea from Flockbook's sidebar): each space with its tile and one mark per
//              tab that has an agent, so the agents show beside their space. A mark is a button to its tab.
//              The layout's stack "sidebar-lists" holds it beside the classic lists; the bar's Sidebar row
//              switches between them (layout.select), and the app keeps the choice. Its header switches
//              the sort: Active (the spaces where something happens first: needs you, finished unseen,
//              working, then idle; the newest change first) or Order (the spaces' own order, which a drag
//              changes for real with space.move, as Herdr's spaces list does). A drag in Active switches to
//              Order as soon as it reaches another space: a drag sets your own order, so you see that order.
// Every view reads the app's live state (agents(), spaces(), terminals()); nothing is stored.

import { View, div, svg, image } from "gpui-kit";
import { h_flex, v_flex, Textarea, TextareaState } from "gpui-base";
import { agents, spaces, terminals, theme, props, run, hc, exec, openOverlay, closeOverlay, nextCommand, shared, setShared, readTextFile, appHome } from "herdr";
import { spaceTile, keepSpaceColors } from "./tiles.js";

const SCREEN_LINES = 40; // the end of the picked agent's screen that the Needs view shows
const READ_MS = 1500; // how often the Needs view reads the picked agent's screen again
const AGE_MS = 30000; // the ages ("5m") are drawn again this often
const NARROW_PX = 150; // a sidebar narrower than this shows the bar as two marks with counts
const READ_TIMEOUT_MS = 10000; // a screen read that has not answered by then counts as failed
const SIDEBAR_STACK = "sidebar-lists"; // the stack in layouts/ormus.json that holds the two sidebars
const SIDEBAR_KEY = "ormus-needs.sidebar"; // shared(): "lists" or "flock", the sidebar shown
const FLOCK_SORT_KEY = "ormus-needs.flock-sort"; // shared(): "active" (default) or "order"
const SEND_TIMEOUT_MS = 20000; // hc send waits for a person's unfinished draft; it gives up by then

// --- pure helpers (test/test_needs.py runs them in node) ---
const CARD_W = 220; // an Overview card's width, px
const CARD_GAP = 8;
const STATUS_ORDER = ["blocked", "done", "working", "idle"];
const STATUS_TITLES = { blocked: "Needs you", done: "Finished, not seen", working: "Working", idle: "Idle" };

// "now", "5m", "3h", "2d" since `ms` (ms since the epoch); "" when unknown or later than `now`.
function ago(ms, now) {
  if (typeof ms !== "number" || !Number.isFinite(ms) || ms <= 0 || ms > now) return "";
  const m = Math.floor((now - ms) / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

// A terminal's labels as { key: value }: hc gives an object, an older core a list of "key=value".
function labelsOf(term) {
  const l = term?.labels;
  if (Array.isArray(l)) {
    const out = {};
    for (const x of l) {
      if (typeof x !== "string") continue;
      const i = x.indexOf("=");
      if (i > 0) out[x.slice(0, i)] = x.slice(i + 1);
    }
    return out;
  }
  return l && typeof l === "object" ? l : {};
}

// The pane names people set (the `ormus.title` label), by terminal address.
function paneTitles(termList) {
  const out = {};
  for (const term of Array.isArray(termList) ? termList : []) {
    const title = labelsOf(term)["ormus.title"];
    if (typeof term?.address === "string" && typeof title === "string" && title.trim()) out[term.address] = title.trim();
  }
  return out;
}

// What to call an agent: its pane name, else its tab's name (unless it is only a number), else its program.
function agentName(a, titles) {
  const own = titles?.[a.address];
  if (own) return own;
  const tab = typeof a.tab_name === "string" ? a.tab_name.trim() : "";
  if (tab && !/^\d+$/.test(tab)) return tab;
  return a.program?.name || a.app || "Agent";
}

// The Needs list: [{ key, title, items }], blocked first, then done; newest change first in each; empty
// groups left out.
function needsGroups(agentList) {
  const list = Array.isArray(agentList) ? agentList : [];
  return ["blocked", "done"]
    .map((key) => ({
      key,
      title: STATUS_TITLES[key],
      items: list.filter((a) => a && a.status === key).sort((x, y) => (y.seq ?? 0) - (x.seq ?? 0)),
    }))
    .filter((g) => g.items.length > 0);
}

// The agent the Needs view shows: the one picked while it still waits, else the first one.
function pickedAgent(groups, picked) {
  const all = groups.flatMap((g) => g.items);
  return all.find((a) => a.address === picked) ?? all[0] ?? null;
}

// How many agents wait for the person and how many finished unseen.
function counts(agentList) {
  const list = Array.isArray(agentList) ? agentList : [];
  return {
    blocked: list.filter((a) => a?.status === "blocked").length,
    done: list.filter((a) => a?.status === "done").length,
  };
}

// Since when a tab is in its state: working since it started working, else its last change.
function since(tab) {
  if (tab?.status === "working" && typeof tab.working_since === "number") return tab.working_since;
  return typeof tab?.changed_at === "number" ? tab.changed_at : null;
}

// Every tab not put away, with its space: [{ space, tab }].
function overviewItems(spaceList) {
  return (Array.isArray(spaceList) ? spaceList : []).flatMap((space) =>
    (space?.tabs ?? []).filter((tab) => tab && !tab.settled).map((tab) => ({ space, tab })));
}

// The Overview's sections: [{ title, items }]. By status: Needs you, Finished, Working, Idle (a tab with no
// agent counts as idle), the newest change first. By space: the spaces in order, their tabs in order.
// Empty sections are left out.
function overviewSections(items, by) {
  if (by === "space") {
    const out = new Map();
    for (const it of items) {
      if (!out.has(it.space.id)) out.set(it.space.id, { title: it.space.name, items: [] });
      out.get(it.space.id).items.push(it);
    }
    return [...out.values()];
  }
  const key = (s) => (STATUS_ORDER.includes(s) ? s : "idle");
  return STATUS_ORDER.map((s) => ({
    title: STATUS_TITLES[s],
    items: items.filter((it) => key(it.tab.status) === s).sort((x, y) => (since(y.tab) ?? 0) - (since(x.tab) ?? 0)),
  })).filter((g) => g.items.length > 0);
}

// The end of a terminal's screen as `hc read` prints it: no color codes, no blank lines at the end, the last
// `n` lines.
function screenTail(text, n) {
  const clean = String(text ?? "")
    .replace(/\x1b\][^\x07\x1b]*(\x07|\x1b\\)/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/\r/g, "");
  const lines = clean.split("\n").map((l) => l.replace(/\s+$/, ""));
  while (lines.length && !lines[lines.length - 1]) lines.pop();
  return lines.slice(-n);
}
// The bar's badges: { need, over }, each a list of { n, tone } (a count in that status color) or { shape }
// (an empty mark: "ring" for Needs you, "square" for the Overview, so the two rows differ in a folded
// sidebar). Wide: Needs you shows the waiting and the finished counts, or "clear". Narrow (a 44 px sidebar
// has room for one badge a row): the most urgent count only.
function barBadges(c, working, narrow) {
  const need = [];
  if (c.blocked) need.push({ n: c.blocked, tone: "blocked" });
  if (c.done && !(narrow && c.blocked)) need.push({ n: c.done, tone: "done" });
  if (!need.length) need.push(narrow ? { shape: "ring" } : { text: "clear" });
  const over = working ? [{ n: working, tone: "working" }] : narrow ? [{ shape: "square" }] : [];
  return { need, over };
}

// A screen read's result as the Needs view keeps it: { address, lines } or { address, error }.
function screenFrom(address, r, n) {
  if (r && r.code === 0) {
    const all = String(r.stdout ?? "").split("\n").map((l) => l.replace(/\r/g, ""));
    const lines = screenTail(r.stdout, n).filter((l) => !/^\[hc\]/.test(l.trim()));
    return { address, lines, menu: parseMenu(screenTail(all.join("\n"), 80)) };
  }
  const why = r ? String(r.stderr ?? "").trim() || `hc read ended with code ${r.code}` : "no answer";
  return { address, error: why };
}

// Whether two kept screens show the same (then the view does not draw again).
function sameScreen(a, b) {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

// The Flock marks of a space's tabs: the tabs with an agent, in tab order (a mark stays where its tab is);
// all of them up to `max`, else the first max - 2 and "+N".
function tabMarks(tabs, max) {
  const live = (Array.isArray(tabs) ? tabs : []).filter((t) => t && t.status && !t.settled);
  if (live.length <= max) return { shown: live, more: [] };
  return { shown: live.slice(0, max - 2), more: live.slice(max - 2) };
}

// The spaces by machine, in order: [{ machine, title, spaces }]; this computer is "This computer".
function machineGroups(spaceList) {
  const out = new Map();
  for (const s of Array.isArray(spaceList) ? spaceList : []) {
    if (!s) continue;
    const m = s.machine ?? null;
    if (!out.has(m)) out.set(m, { machine: m, title: m ?? "This computer", spaces: [] });
    out.get(m).spaces.push(s);
  }
  return [...out.values()];
}

const STATUS_WORDS = { working: "working", blocked: "needs you", done: "finished, not seen", idle: "idle" };

// A mark's tooltip: the tab and what its agent does.
function markTip(tab) {
  return `${tab.name} · ${STATUS_WORDS[tab.status] ?? "no agent"}`;
}

// The sidebar shown, from the app's saved layout state (layouts/.state/ormus.json): "flock" when the stack
// shows the Flock child, "lists" when it shows the lists, null when the state does not say. The app keeps a
// stack's choice as nodes.<stack id>.active (measured in Flockbook's saved state: "screen": {"active": "tab"}).
function sidebarFromState(text, stack) {
  let d;
  try {
    d = JSON.parse(text);
  } catch {
    return null;
  }
  const active = d?.nodes?.[stack]?.active;
  if (active === "sidebar-flock") return "flock";
  if (active === "sidebar-lists-classic") return "lists";
  return null;
}

// The layout.select that shows a sidebar: "flock" or "lists".
function sidebarSelect(which) {
  return { stack: "sidebar-lists", child: which === "flock" ? "sidebar-flock" : "sidebar-lists-classic" };
}

// A screen line without the side bars of a box ("│ text │" → "text").
function unboxed(line) {
  return String(line ?? "").replace(/^\s*│ ?/, "").replace(/\s*│\s*$/, "");
}

const OPTION_LINE = /^(\s*)([❯›])?\s*(\d{1,2})[.)]\s+(\S.*?)\s*$/;
const RULE_LINE = /^\s*[─━═]{3,}\s*$/; // Claude Code's rules are box drawing, never a typed "---"
const TAB_ROW = /[☐☑☒✔✓]/;
// The tab row of a question with several parts: check marks and an arrow (a ✓ alone is ordinary output).
function isTabRow(line) {
  return TAB_ROW.test(line) && /[←→]/.test(line);
}

// The menu at the end of a screen, as Claude Code draws a question or a permission prompt: numbered choices
// 1, 2, 3 ... with the selector ❯ on one of them. Null when there is none. A numbered list in an agent's
// answer has no selector, so it is never taken for a menu. { question, context, options: [{ n, label,
// detail, selected }], multi, steps: [{ label, done }] }. `context` is every line above the choices up to
// the box's top, a rule or the tab row (the command or tool the prompt is about, and the question): two
// prompts are the same only when it is the same. `multi`: the choices are check boxes ([ ] / [x]), where a
// number toggles and does not answer. `steps`: the tab row of a question with several parts.
function parseMenu(lines) {
  const all = (Array.isArray(lines) ? lines : []).map((l) => String(l ?? ""));
  let end = all.length;
  while (end > 0 && (!all[end - 1].trim() || /^\[hc\]/.test(all[end - 1].trim()))) end -= 1;
  const start = Math.max(0, end - 60);
  const found = [];
  for (let i = start; i < end; i++) {
    const m = unboxed(all[i]).match(OPTION_LINE);
    if (m) found.push({ i, n: Number(m[3]), label: m[4], selected: Boolean(m[2]), indent: m[1].length });
  }
  let run = null;
  for (let j = found.length - 1; j >= 0 && !run; j--) {
    if (found[j].n !== 1) continue;
    const r = [found[j]];
    for (let k = j + 1; k < found.length && found[k].n === r[r.length - 1].n + 1; k++) r.push(found[k]);
    run = r;
  }
  if (!run || run.length < 2) return null;
  if (run.filter((o) => o.selected).length !== 1) return null;
  if (run[run.length - 1].i < end - 12) return null; // a menu sits at the end of the screen
  const options = run.map((o, idx) => {
    const stop = idx + 1 < run.length ? run[idx + 1].i : Math.min(end, o.i + 4);
    const detail = [];
    for (let i = o.i + 1; i < stop; i++) {
      const line = unboxed(all[i]);
      if (!line.trim() || RULE_LINE.test(line)) break;
      if (line.search(/\S/) <= o.indent + 1) break; // not indented under the choice: the footer
      detail.push(line.trim());
    }
    return { n: o.n, label: o.label, detail: detail.join(" ").slice(0, 240), selected: o.selected };
  });
  // The question: the paragraph right above the choices.
  const words = [];
  let i = run[0].i - 1;
  while (i >= start && !unboxed(all[i]).trim()) i -= 1;
  for (; i >= start; i--) {
    const line = unboxed(all[i]);
    if (!line.trim() || RULE_LINE.test(line) || isTabRow(line)) break;
    words.unshift(line.trim());
  }
  // The context: every line above the choices, up to the box's top, a rule or the tab row (at most 20).
  const context = [];
  for (let k = run[0].i - 1; k >= start && context.length < 20; k--) {
    const raw = all[k];
    const line = unboxed(raw);
    if (RULE_LINE.test(line) || isTabRow(raw) || /^\s*[╭╰┌└]/.test(raw) || /^\s*[╭╰┌└]/.test(line)) break;
    if (unboxed(raw).trim()) context.unshift(unboxed(raw).trim());
  }
  let steps = [];
  for (let k = run[0].i - 1; k >= start; k--) {
    const line = all[k];
    if (isTabRow(line)) {
      steps = line.replace(/[←→]/g, "").split(/\s{2,}/).map((x) => x.trim()).filter(Boolean)
        .map((x) => ({ label: x.replace(/^[☐☑☒✔✓]\s*/, ""), done: /^[☑☒✔✓]/.test(x) }));
      break;
    }
  }
  const multi = options.some((o) => /^\[[ xX✓✔]\]/.test(o.label));
  return { question: words.join(" ").slice(0, 400), context: context.join("\n"), options, multi, steps };
}

// Whether two screens ask the same: the same context (command and question) and the same choices.
function sameMenu(a, b) {
  const key = (m) => (m ? JSON.stringify([m.context, m.options.map((o) => o.label)]) : null);
  return key(a) === key(b);
}

// What an answer does to the agent, step by step, or null when it cannot be sent:
//   { kind: "option", n }  presses the number (1-9) of a menu choice (not in a check box menu);
//   { kind: "text", text } with a menu: Esc (says no to it), then the words as a message;
//                          with no menu: the words as a reply.
// A step is { keys: [...], free } (hc keys; free: wait until the agent no longer waits on the menu) or
// { send } (hc send, which refuses an agent that still waits on a menu).
function answerPlan(menu, choice) {
  if (choice?.kind === "option") {
    const o = menu && !menu.multi ? menu.options.find((x) => x.n === choice.n) : null;
    return o && o.n <= 9 ? [{ keys: [String(o.n)] }] : null;
  }
  const text = typeof choice?.text === "string" ? choice.text.trim() : "";
  if (choice?.kind !== "text" || !text) return null;
  if (menu) return [{ keys: ["esc"], free: true }, { send: text }];
  return [{ send: text }];
}

// The plan in words, for the note after a send and the tooltips.
function planWords(plan) {
  return (plan ?? []).map((s) => (s.keys ? `pressed ${s.keys.join(" ")}` : `sent "${s.send.length > 60 ? s.send.slice(0, 57) + "..." : s.send}"`)).join(", then ");
}

// Send an answer to the agent at `address`. `shown`: the menu the person saw (null: none); `io`: { read(a)
// -> { menu } | { error }, keys(a, keys) and send(a, text) -> { code, stderr }, status(a) -> the app's status
// now, wait(ms) }. A menu counts only while the agent waits on it ("blocked"): a finished agent gets words,
// never keys. The screen is read again first; nothing goes out when its menu is not the one shown, or the
// agent works. Returns { ok, text } for the note, and `screen` when the read found a change.
async function runAnswer(io, address, shown, choice) {
  const why = (r) => String(r?.stderr ?? "").trim() || `hc ended with code ${r?.code}`;
  const menu = io.status(address) === "blocked" ? shown : null;
  const plan = answerPlan(menu, choice);
  if (!plan) {
    return { ok: false, text: choice?.kind === "option" ? "There is no menu with that number to answer here." : "Nothing to send." };
  }
  const again = await io.read(address);
  if (again.error) return { ok: false, text: `Not sent: ${again.error}` };
  const status = io.status(address);
  if (status === "working") return { ok: false, text: "It works now, so nothing was sent.", screen: again };
  if (!sameMenu(status === "blocked" ? again.menu : null, menu)) {
    return { ok: false, text: "The question changed, so nothing was sent. Look at it again.", screen: again };
  }
  let closed = false;
  for (const step of plan) {
    if (step.keys) {
      if (io.status(address) !== "blocked") return { ok: false, text: "It no longer waits on the menu, so nothing was sent." };
      const r = await io.keys(address, step.keys);
      if (r.code !== 0) return { ok: false, text: `Not sent: ${why(r)}` };
      if (step.free) {
        closed = true;
        for (let k = 0; k < 15 && io.status(address) === "blocked"; k++) await io.wait(200);
        if (io.status(address) === "blocked") {
          return { ok: false, text: "The menu was closed (Esc), but it still waits, so your words were not sent." };
        }
      }
    } else {
      const now = io.status(address);
      if (now === "working" || now === "blocked") {
        const what = now === "working" ? "it works now" : "it waits on a menu";
        return { ok: false, text: closed ? `The menu was closed (Esc), but ${what}, so your words were not sent.` : `Not sent: ${what}.` };
      }
      let r;
      try {
        r = await io.send(address, step.send);
      } catch (e) {
        // A send that did not answer may have typed already: say so, and do not invite a second send.
        return { ok: false, unsure: true, text: `The send did not answer (${e?.message ?? e}). Look at the agent before you send again.` };
      }
      if (r.code !== 0) {
        return { ok: false, text: closed ? `The menu was closed (Esc), but your words were not sent: ${why(r)}` : `Not sent: ${why(r)}` };
      }
    }
  }
  return { ok: true, text: `Sent: ${planWords(plan)}.` };
}

// A key with no Ctrl, Alt or Cmd, pressed now (a held key repeats: it answers nothing). Shift counts:
// `key` is the key printed on the cap, so Shift+1 ("!") must not read as 1.
function plainKey(e) {
  const m = e?.modifiers ?? {};
  if (e?.is_held || m.control || m.alt || m.platform || m.cmd || m.function) return null;
  const k = String(e?.key ?? "").toLowerCase();
  return m.shift ? `shift-${k}` : k;
}

// What a key does in the Needs view: { move: -1 | 1 } | { pick: n } | { go } | { peek } | { reply } | null.
function needsKey(e) {
  const k = plainKey(e);
  if (k === null) return null;
  if (/^[1-9]$/.test(k)) return { pick: Number(k) };
  if (k === "up" || k === "k") return { move: -1 };
  if (k === "down" || k === "j") return { move: 1 };
  if (k === "enter") return { go: true };
  if (k === "p") return { peek: true };
  if (k === "/" || k === "r" || k === "tab") return { reply: true };
  return null;
}

// What a key does in the Overview: { move: n } (cards, in reading order) | { open } | { group } | null.
function overviewKey(e, cols) {
  const k = plainKey(e);
  const c = Math.max(1, cols | 0);
  if (k === "left" || k === "h") return { move: -1 };
  if (k === "right" || k === "l") return { move: 1 };
  if (k === "up" || k === "k") return { move: -c };
  if (k === "down" || k === "j") return { move: c };
  if (k === "enter") return { open: true };
  if (k === "s") return { group: true };
  return null;
}

// The index after a move, kept inside a list of `len` (-1 when the list is empty).
function moveIndex(i, d, len) {
  if (len <= 0) return -1;
  const from = i < 0 ? 0 : i;
  return Math.max(0, Math.min(len - 1, from + d));
}

// How many Overview cards fit in a row of `width` px.
function cardsPerRow(width) {
  return Math.max(1, Math.floor(((width ?? 0) + CARD_GAP) / (CARD_W + CARD_GAP)));
}

// A space's band, for the Active sort: 0 an agent needs you, 1 one finished unseen, 2 one works, 3 idle; from
// its tabs that are not put away.
const ACTIVITY_RANK = { blocked: 0, done: 1, working: 2 };
function spaceRank(space) {
  const tabs = (space?.tabs ?? []).filter((tab) => tab && !tab.settled);
  return Math.min(3, ...tabs.map((tab) => ACTIVITY_RANK[tab.status] ?? 3));
}

// The band of each space: { [id]: rank }. `held` keeps the bands shown when the pointer came on the list, so
// a row does not move away under a click (a click on a space can turn its "finished" tab into idle); a space
// not in `held` (a new one) gets its band now.
function spaceBands(list, held) {
  const keep = held && typeof held === "object" ? held : {};
  return Object.fromEntries((Array.isArray(list) ? list : []).map((s) => [s.id, s.id in keep ? keep[s.id] : spaceRank(s)]));
}

// Spaces by activity: the lowest band first; inside a band, the spaces' own order (the order a drag sets),
// so the list moves only when a space changes band.
function byActivity(list, bands) {
  const b = bands ?? spaceBands(list);
  return (Array.isArray(list) ? list : [])
    .map((s, i) => ({ s, i, r: b[s.id] ?? 3 }))
    .sort((x, y) => x.r - y.r || x.i - y.i)
    .map((x) => x.s);
}

// The space a drag is over: `rowId` when it is on the dragged space's machine (a space stays on its machine,
// as in Herdr's spaces list) and, with `bands` (the Active sort), in the dragged space's band; else null.
function dragOver(list, fromId, rowId, bands) {
  const from = list.find((s) => s.id === fromId);
  const row = list.find((s) => s.id === rowId);
  if (!from || !row || (from.machine ?? null) !== (row.machine ?? null)) return null;
  return !bands || bands[fromId] === bands[rowId] ? rowId : null;
}

// The space.move a drop makes: { id, index } (index: the target's place in all spaces, from 1, as Herdr's
// spaces list counts it), or null when the drop moves nothing.
function dropMove(list, fromId, overId, bands) {
  if (!fromId || !overId || fromId === overId || dragOver(list, fromId, overId, bands) !== overId) return null;
  const index = list.findIndex((s) => s.id === overId);
  return index < 0 ? null : { id: fromId, index: index + 1 };
}

// The words for a count, for the bar's tooltip.
function needsTip(c) {
  if (!c.blocked && !c.done) return "No agent waits for you (ctrl-shift-i)";
  return `${c.blocked} wait for you, ${c.done} finished unseen (ctrl-shift-i)`;
}
// --- end of pure helpers ---

export default class Needs extends View {
  init(p, cx) {
    this.props = props() ?? p ?? {};
    this.view = this.props.view ?? "bar";
    this.overlay = null; // bar: the dialog it opened last
    this.narrow = false; // bar: the sidebar is folded
    this.picked = null; // needs: the agent picked in the list
    this.screen = null; // needs: { address, lines } | { address, error } for the picked agent
    this.reading = false;
    this.readSeq = 0; // the screen reads started: an answer from an older one is dropped
    this.by = "status"; // overview: "status" or "space"
    this.sending = false; // needs: an answer goes out now
    this.note = null; // needs: { address, bad, text } after an answer
    this.sel = null; // overview: the tab id the keys move
    this.pressed = null; // spaces: the space a drag holds
    this.over = null; // spaces: the space the drag is over
    this.inside = false; // spaces: the pointer is on the list (the Active bands stay still)
    this.held = null; // spaces: { [id]: band } the Active bands shown when the pointer came in
    this.cols = 4; // overview: cards in a row, from its width
    if (this.view === "needs" || this.view === "overview") {
      // The dialog takes the keyboard when it opens, so the keys work at once.
      this.focus = cx.focus_handle();
      cx.timer.after(60, () => this.focus.focus());
    }
    if (this.view === "needs") {
      // Made once here: a view may not make input state while it draws.
      this.input = TextareaState.new({ placeholder: "Type an answer (Enter sends, Shift+Enter: a new line)", rows: 1 });
      this.input.set_auto_grow?.(1, 6);
      this.drafts = new Map(); // address -> text typed and not sent
      this.inputFor = null; // the agent the box holds text for
      this.input.on("submit", (e, cx) => {
        if (e?.shift) return; // Shift+Enter: the box adds the new line itself
        const cur = pickedAgent(needsGroups(agents()), this.picked);
        // The box holds the text of `inputFor`: send it only to that agent (the list may change under it).
        if (cur && this.inputFor === cur.address) this.answer(cx, cur, { kind: "text", text: this.input.value().replace(/\n+$/, "") });
      });
      this.input.on("change", () => {
        if (this.inputFor) this.drafts.set(this.inputFor, this.input.value());
      });
    }
    if (this.view === "bar") {
      if (shared(SIDEBAR_KEY) == null) {
        cx.spawn(async (cx) => {
          try {
            const text = await readTextFile(`${appHome()}/layouts/.state/ormus.json`);
            const got = text ? sidebarFromState(text, SIDEBAR_STACK) : null;
            if (got && shared(SIDEBAR_KEY) == null) setShared(SIDEBAR_KEY, got);
          } catch {
            // no saved state: the layout file's own choice (the lists) shows
          }
          cx.notify();
        });
      }
      cx.spawn(async (cx) => {
        for (;;) {
          // A failure here must not end the loop: the keys would stop working until the mod reloads.
          try {
            const c = await nextCommand();
            if (c === "needs" || c === "overview") this.open(c);
            if (c === "sidebar") this.sidebar(shared(SIDEBAR_KEY) === "flock" ? "lists" : "flock");
            cx.notify();
          } catch (e) {
            console.log(`ormus-needs: a key command failed: ${e?.message ?? e}`);
            await new Promise((done) => cx.timer.after(1000, () => done()));
          }
        }
      });
    }
    if (this.view === "needs") {
      cx.timer.every(READ_MS, (cx) => this.read(cx));
      this.read(cx);
    }
    if (this.view !== "bar") cx.timer.every(AGE_MS, (cx) => cx.notify());
  }

  // bar: show a view as a dialog over the window; a second one replaces the first.
  open(view) {
    // The last dialog may be closed already (Esc, a click beside it): closing it again is harmless.
    if (this.overlay) {
      try {
        closeOverlay(this.overlay);
      } catch {
        // gone already
      }
    }
    this.overlay = openOverlay({ mod: "ormus-needs", props: { view }, kind: "dialog", width: 0.82, height: 0.82 });
  }

  // bar: show the lists or the Flock sidebar.
  sidebar(which) {
    run("layout.select", sidebarSelect(which));
    setShared(SIDEBAR_KEY, which);
  }

  // An overlay copy closes its own dialog. (Not named close: the app calls a View's close(cx) when it goes.)
  dismiss() {
    const id = this.props.overlay;
    try {
      if (id) closeOverlay(id);
    } catch {
      // closed already (Esc): the action after it still runs
    }
  }

  // needs: read the picked agent's screen again (one read at a time). `exec` ends a read that hangs after
  // READ_TIMEOUT_MS and stops its `hc`; the timer below is a second guard, and an answer from an older read
  // (the person picked another agent, or the timer came first) is dropped by its number.
  read(cx) {
    const cur = pickedAgent(needsGroups(agents()), this.picked);
    if (!cur || this.reading || this.sending) return;
    const address = cur.address;
    const seq = ++this.readSeq;
    const keep = (cx, screen) => {
      if (seq !== this.readSeq) return;
      if (this.sending) return; // a send runs: its own read comes after it (an old screen would bring back its buttons)
      this.readSeq += 1;
      this.reading = false;
      // Draw again only when the screen changed: a redraw every READ_MS costs the whole window.
      if (!sameScreen(screen, this.screen)) {
        this.screen = screen;
        cx.notify();
      }
    };
    this.reading = true;
    try {
      cx.timer.after(READ_TIMEOUT_MS + 2000, (cx) => keep(cx, { address, error: "hc read did not answer" }));
      cx.spawn(async (cx) => {
        const started = Date.now();
        let screen;
        try {
          screen = screenFrom(address, await exec("hc", ["read", address], { timeout: READ_TIMEOUT_MS }), SCREEN_LINES);
        } catch (e) {
          // `exec` rejects at once when it cannot start `hc` (not on PATH): then ask the app's own `hc`.
          if (Date.now() - started < 1000) {
            try {
              screen = screenFrom(address, await hc(["read", address]), SCREEN_LINES);
            } catch (e2) {
              screen = { address, error: String(e2?.message ?? e2) };
            }
          } else {
            screen = { address, error: String(e?.message ?? e) };
          }
        }
        keep(cx, screen);
      });
    } catch (e) {
      this.reading = false;
      this.screen = { address, error: String(e?.message ?? e) };
    }
  }

  // needs: send an answer to agent `cur` (runAnswer does the checks). The shown screen is dropped at once, so
  // its buttons and keys are gone until a fresh read: a second press cannot reach the next prompt.
  answer(cx, cur, choice) {
    if (this.sending || !cur) return;
    const shown = this.screen?.address === cur.address ? this.screen : null;
    if (!shown || shown.error) {
      this.note = { address: cur.address, bad: true, text: "Its screen is not read yet, so nothing was sent. Try again in a moment." };
      cx.notify();
      return;
    }
    const address = cur.address;
    const io = {
      read: async (a) => screenFrom(a, await exec("hc", ["read", a], { timeout: READ_TIMEOUT_MS }), SCREEN_LINES),
      keys: (a, keys) => exec("hc", ["keys", a, ...keys], { timeout: READ_TIMEOUT_MS }),
      // "--": words that start with "-" stay words (measured: hc send t -- "-h" types "-h").
      send: (a, text) => exec("hc", ["send", a, "--", text], { timeout: SEND_TIMEOUT_MS }),
      status: (a) => agents().find((x) => x.address === a)?.status ?? null,
      wait: (ms) => new Promise((done) => cx.timer.after(ms, () => done())),
    };
    this.sending = true;
    this.note = null;
    this.screen = null;
    cx.notify();
    cx.spawn(async (cx) => {
      let res;
      try {
        res = await runAnswer(io, address, shown.menu ?? null, choice);
      } catch (e) {
        res = { ok: false, text: `Not sent: ${e?.message ?? e}` };
      }
      this.note = { address, bad: !res.ok, text: res.text };
      if (res.ok && choice.kind === "text") {
        // Clear the box and the draft only when they still hold the words that went out (more may be typed meanwhile).
        if ((this.drafts.get(address) ?? "").trim() === choice.text.trim()) this.drafts.delete(address);
        if (this.inputFor === address && this.input.value().trim() === choice.text.trim()) this.input.set_value("");
      }
      this.sending = false;
      this.screen = null; // no choices until the read below shows what the agent does now
      this.readSeq += 1; // read the answer's effect at once
      this.reading = false;
      this.read(cx);
      cx.notify();
    });
  }

  // needs: show agent `address` (its draft goes into the box; the old one is kept).
  pick(address, cx) {
    if (this.picked === address) return;
    this.picked = address;
    this.note = null;
    this.readSeq += 1; // drop a read of the agent shown before
    this.reading = false;
    this.read(cx);
    cx.notify();
  }

  goTo(a) {
    this.dismiss();
    run("agent.focus", { terminal: a.address });
  }

  peek(a) {
    this.dismiss();
    run("terminal.peek", { terminal: a.address });
  }

  showTab(it) {
    this.dismiss();
    run("space.select", { id: it.space.id });
    run("tab.select", { id: it.tab.id });
  }

  // A status mark: a spinner while working, a red dot when it waits, a gold check when done, a ring when idle.
  mark(t, status) {
    if (status === "working") return svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900);
    if (status === "done") return svg("mods/workspace-chrome/check.svg").size(13).flex_none().text_color(t.done);
    if (status === "blocked") return div().size(9).flex_none().rounded(5).bg(t.blocked);
    return div().size(10).flex_none().rounded(5).border(1).border_color(t.dim);
  }

  button(t, id, label, tip, onClick, solid) {
    return div().id(id).flex_none().px(12).h(30).flex().items_center().rounded(7).text_size(12.5).font_medium()
      .when(Boolean(solid), (el) => el.bg(t.solid).text_color(t.solid_foreground).hov\u0065r((s) => s.opacity(0.9)))
      .when(!solid, (el) => el.border(1).border_color(t.border).text_color(t.foreground).hov\u0065r((s) => s.bg(t.hov\u0065r)))
      .tooltip(tip)
      .on_click((_e, cx) => {
        cx.stop_propagation();
        onClick(cx);
      })
      .child(label);
  }

  // --- bar ---
  count(t, n, color) {
    return div().flex_none().min_w(18).px(5).h(18).flex().items_center().justify_center().rounded(9)
      .bg(color + "2e").text_size(11).font_semibold().text_color(color).child(String(n));
  }

  badge(t, b) {
    if (b.n) return this.count(t, b.n, t[b.tone]);
    if (b.shape) return div().size(9).flex_none().rounded(b.shape === "ring" ? 5 : 2).border(1).border_color(t.dim);
    return div().flex_none().text_size(11).text_color(t.dim).child(b.text ?? "");
  }

  barRow(t, id, label, tip, badges, onClick, key) {
    return h_flex().id(id).h(28).px(this.narrow ? 2 : 8).gap(6).items_center().rounded(7).text_size(12.5).text_color(t.muted)
      .when(this.narrow, (el) => el.justify_center())
      .hov\u0065r((s) => s.bg(t.hov\u0065r).text_color(t.foreground))
      .tooltip(tip)
      .on_click((_e, cx) => onClick(cx))
      .when(!this.narrow, (el) => el.child(div().flex_1().truncate().child(label)))
      .when(!this.narrow && Boolean(key), (el) => el.child(div().flex_none().font_family("JetBrains Mono").text_size(10.5)
        .text_color(t.dim).child(key)))
      .children(badges);
  }

  renderBar(t) {
    const c = counts(agents());
    const working = overviewItems(spaces()).filter((it) => it.tab.status === "working").length;
    const b = barBadges(c, working, this.narrow);
    const needBadges = b.need.map((x) => this.badge(t, x));
    const overBadges = b.over.map((x) => this.badge(t, x));
    return v_flex().id("needs-bar").size_full().px(this.narrow ? 4 : 8).py(4).gap(2).justify_center()
      .on_size_change((size, cx) => {
        const narrow = (size?.width ?? 999) < NARROW_PX;
        if (narrow !== this.narrow) {
          this.narrow = narrow;
          cx.notify();
        }
      })
      .child(this.barRow(t, "bar-needs", "Needs you", needsTip(c), needBadges, () => this.open("needs"), "⌃⇧I"))
      .child(this.barRow(t, "bar-overview", "Overview", "Every tab of every space, by status (ctrl-shift-g)", overBadges, () => this.open("overview"), "⌃⇧G"))
      .child(this.sidebarRow(t));
  }

  // The Sidebar row: Lists (the spaces and agents lists) or Flock (each space with its agents' marks).
  sidebarRow(t) {
    const flock = shared(SIDEBAR_KEY) === "flock";
    const seg = (id, label, on, which) => div().id(id).px(7).h(20).flex().items_center().rounded(5).text_size(11.5)
      .bg(on ? t.selected : t.background).text_color(on ? t.foreground : t.muted)
      .hov\u0065r((s) => s.text_color(t.foreground))
      .on_click((_e, cx) => {
        cx.stop_propagation();
        // Always select, also the segment shown as on: after a layout reset the app and the bar can differ.
        this.sidebar(which);
        cx.notify();
      })
      .child(label);
    if (this.narrow) {
      return h_flex().id("bar-sidebar").h(28).px(2).justify_center().items_center().rounded(7)
        .hov\u0065r((s) => s.bg(t.hov\u0065r))
        .tooltip(flock ? "Show the lists (ctrl-shift-j)" : "Show Flock: each space with its agents (ctrl-shift-j)")
        .on_click((_e, cx) => {
          this.sidebar(flock ? "lists" : "flock");
          cx.notify();
        })
        .child(div().size(10).flex_none().rounded(2).border(1).border_color(flock ? t.foreground : t.dim));
    }
    return h_flex().id("bar-sidebar").h(28).px(8).gap(6).items_center().text_size(12.5).text_color(t.muted)
      .child(div().flex_1().truncate().child("Sidebar"))
      .child(div().flex_none().font_family("JetBrains Mono").text_size(10.5).text_color(t.dim).child("⌃⇧J"))
      .child(h_flex().flex_none().p(2).gap(2).rounded(7).border(1).border_color(t.border)
        .tooltip("Lists: spaces and agents. Flock: each space with its agents' marks (ctrl-shift-j)")
        .child(seg("bar-lists", "Lists", !flock, "lists"))
        .child(seg("bar-flock", "Flock", flock, "flock")));
  }

  // --- needs ---
  // A key hint: a small box with the key.
  hint(t, k) {
    return div().flex_none().min_w(18).h(18).px(4).flex().items_center().justify_center().rounded(5).border(1)
      .border_color(t.border).text_size(10.5).text_color(t.muted).child(k);
  }

  menuView(t, cur, menu) {
    const busy = this.sending;
    const box = v_flex().id("needs-menu").gap(8).p(14).rounded(10).bg(t.raised).border(1).border_color(t.border);
    if (menu.steps.length > 1) {
      box.child(h_flex().gap(6).flex_wrap().children(menu.steps.map((st, i) => div().id(`step-${i}`).px(8).h(20).flex()
        .items_center().rounded(5).text_size(11).bg(st.done ? t.surface : t.background).border(1).border_color(t.border)
        .text_color(st.done ? t.dim : t.muted).child(`${st.done ? "✓ " : ""}${st.label}`))));
    }
    if (menu.question) box.child(div().text_size(14).font_semibold().text_color(t.foreground).child(menu.question));
    const live = !busy && !menu.multi;
    if (menu.multi) {
      box.child(div().text_size(11.5).text_color(t.muted)
        .child("Several answers can be checked here: answer in words below, or in the agent (Go to it)."));
    }
    box.children(menu.options.map((o) => h_flex().id(`opt-${o.n}`).px(10).py(7).gap(10).items_center().rounded(8)
      .bg(t.background).border(1).border_color(o.selected ? t.accent : t.border)
      .when(live, (el) => el.hov\u0065r((x) => x.bg(t.hov\u0065r)).on_click((_e, cx) => {
        cx.stop_propagation();
        this.answer(cx, cur, { kind: "option", n: o.n });
      }))
      .tooltip(menu.multi ? "A check box: answer in words or in the agent" : o.n <= 9 ? `Press ${o.n} in the agent` : "Too far down for a number key: answer in the agent")
      .child(this.hint(t, String(o.n)))
      .child(v_flex().flex_1().min_w(0)
        .child(div().text_size(13).text_color(busy ? t.dim : t.foreground).child(o.label))
        .when(Boolean(o.detail), (el) => el.child(div().text_size(11.5).text_color(t.muted).child(o.detail))))));
    return box;
  }

  replyView(t, cur, menu) {
    if (this.inputFor !== cur.address) {
      this.inputFor = cur.address;
      this.input.set_value(this.drafts.get(cur.address) ?? "");
    }
    const how = !menu
      ? "Enter sends it as your reply."
      : "Enter closes the menu (Esc, a no) and sends your words as a message.";
    // Keys stay in the box: the view would read 1-9 and Enter as answers.
    const keep = (e, cx) => {
      if (e?.key === "escape") this.focus.focus();
      cx.stop_propagation();
    };
    return v_flex().gap(4)
      .child(h_flex().id("needs-reply").px(10).py(6).gap(8).items_center().rounded(8).bg(t.background).border(1)
        .border_color(t.border).on_mouse_down("left", (_e, cx) => cx.stop_propagation()).on_key_down(keep)
        .child(div().flex_1().min_w(0).child(Textarea.new(this.input).w_full().text_size(13))))
      .child(div().text_size(11).text_color(t.dim).child(how));
  }

  renderNeeds(t) {
    const groups = needsGroups(agents());
    const root = v_flex().id("needs-root").size_full().bg(t.background).track_focus(this.focus);
    if (!groups.length) {
      return root.items_center().justify_center().gap(8)
        .child(div().text_size(17).font_semibold().text_color(t.foreground).child("All clear"))
        .child(div().text_size(13).text_color(t.muted).child("No agent waits for you, and no agent finished unseen."))
        .child(this.button(t, "needs-close", "Close", "Close this view (Esc)", () => this.dismiss()));
    }
    const titles = paneTitles(terminals());
    const cur = pickedAgent(groups, this.picked);
    const order = groups.flatMap((g) => g.items);
    const tabs = new Map(overviewItems(spaces()).map((it) => [it.tab.id, it.tab]));
    const now = Date.now();
    const screen = this.screen?.address === cur.address ? this.screen : null;
    // A menu counts only while the agent waits on it: a finished agent's screen gets a reply box only.
    const menu = cur.status === "blocked" ? screen?.menu ?? null : null;
    const row = (a) => {
      const on = a.address === cur.address;
      const p = a.program;
      const age = ago(since(tabs.get(a.tab)), now);
      return h_flex().id(`need-${a.address}`).h(50).px(10).gap(10).items_center().rounded(8)
        .bg(on ? t.selected : t.background).hov\u0065r((s) => s.bg(on ? t.selected : t.hov\u0065r))
        .on_click((_e, cx) => this.pick(a.address, cx))
        .when(Boolean(p?.icon), (el) => el.child(p.tint ? svg(p.icon).size(18).flex_none().text_color(t.muted) : image(p.icon).size(18).flex_none()))
        .child(v_flex().flex_1().min_w(0)
          .child(div().truncate().text_size(13).text_color(t.foreground).child(agentName(a, titles)))
          .child(div().truncate().text_size(11.5).text_color(t.muted).child(`${a.space_name} · ${a.tab_name}`)))
        .when(Boolean(age), (el) => el.child(div().flex_none().text_size(11).text_color(t.dim).child(age)))
        .child(this.mark(t, a.status));
    };
    const list = v_flex().id("needs-list").w(320).flex_none().h_full().p(10).gap(2).border_r(1).border_color(t.border)
      .overflow_y_scrollbar()
      .children(groups.flatMap((g) => [
        div().px(4).pt(8).pb(4).text_size(12).font_semibold().text_color(t.muted).child(`${g.title} · ${g.items.length}`),
        ...g.items.map(row),
      ]));
    const body = !screen
      ? div().text_size(12.5).text_color(t.muted).child(this.sending ? "Sending..." : "Reading its screen...")
      : screen.error
        ? div().text_size(12.5).text_color(t.blocked).child(`Cannot read its screen: ${screen.error}`)
        : v_flex().id("needs-screen").p(12).rounded(8).bg(t.surface).border(1).border_color(t.border)
          .font_family("JetBrains Mono").text_size(12).text_color(t.foreground)
          .children(screen.lines.map((l, i) => div().id(`line-${i}`).whitespace_nowrap().overflow_hidden().child(l || " ")));
    const note = this.note?.address === cur.address ? this.note : null;
    const keys = h_flex().gap(10).flex_wrap().items_center().text_size(11).text_color(t.dim)
      .children([["↑↓", "agents"], ["1-9", "answer"], ["/", "type"], ["Enter", "go to it"], ["P", "peek"], ["Esc", "close"]]
        .map(([k, what], i) => h_flex().id(`key-${i}`).gap(4).items_center().child(this.hint(t, k)).child(what)));
    const detail = v_flex().id("needs-detail").flex_1().min_w(0).h_full().p(20).gap(10).overflow_y_scrollbar()
      .child(h_flex().gap(10).items_center()
        .child(this.mark(t, cur.status))
        .child(div().flex_1().truncate().text_size(17).font_semibold().text_color(t.foreground).child(agentName(cur, titles)))
        .child(this.button(t, "needs-go", "Go to it", "Show this agent and give it the keyboard (Enter)", () => this.goTo(cur), true))
        .child(this.button(t, "needs-peek", "Peek", "Show its terminal over the tab (P)", () => this.peek(cur)))
        .child(this.button(t, "needs-close", "Close", "Close this view (Esc)", () => this.dismiss())))
      .child(div().text_size(12.5).text_color(t.muted)
        .child(`${cur.space_name} · ${cur.tab_name}${cur.title ? " · " + cur.title : ""}`))
      .when(Boolean(menu), (el) => el.child(this.menuView(t, cur, menu)))
      .child(this.replyView(t, cur, menu))
      .when(this.sending, (el) => el.child(div().text_size(12).text_color(t.muted).child("Sending...")))
      .when(Boolean(note), (el) => el.child(div().text_size(12).text_color(note.bad ? t.blocked : t.done).child(note.text)))
      .child(keys)
      .child(div().text_size(11.5).text_color(t.dim)
        .child(cur.status === "blocked" ? "It waits for you. The end of its screen:" : "It finished while you did not look. The end of its screen:"))
      .child(body);
    return root
      .on_mouse_down("left", () => this.focus.focus())
      .on_key_down((e, cx) => {
        const act = needsKey(e);
        if (!act) return;
        cx.stop_propagation();
        if (act.move) {
          const i = moveIndex(order.findIndex((a) => a.address === cur.address), act.move, order.length);
          if (i >= 0) this.pick(order[i].address, cx);
        } else if (act.pick) this.answer(cx, cur, { kind: "option", n: act.pick });
        else if (act.go) this.goTo(cur);
        else if (act.peek) this.peek(cur);
        else if (act.reply) this.input.focus?.();
      })
      .child(h_flex().size_full().items_start().child(list).child(detail));
  }

  // --- overview ---
  toggle(t, id, label, value) {
    const on = this.by === value;
    return div().id(id).px(10).h(26).flex().items_center().rounded(6).text_size(12)
      .bg(on ? t.selected : t.background).text_color(on ? t.foreground : t.muted).hov\u0065r((s) => s.bg(t.hov\u0065r))
      .on_click((_e, cx) => {
        this.by = value;
        cx.notify();
      })
      .child(label);
  }

  renderOverview(t) {
    const items = overviewItems(spaces());
    const sections = overviewSections(items, this.by);
    const order = sections.flatMap((s) => s.items);
    const selIndex = Math.max(0, order.findIndex((it) => it.tab.id === this.sel));
    const selected = order[selIndex] ?? null;
    const now = Date.now();
    const card = (it) => {
      const age = ago(since(it.tab), now);
      const what = it.tab.status === "working" ? `working ${age}` : age;
      const on = selected?.tab.id === it.tab.id;
      return v_flex().id(`tab-${it.tab.id}`).w(CARD_W).flex_none().p(10).gap(4).rounded(8).border(on ? 2 : 1)
        .border_color(on ? t.accent : t.border)
        .bg(it.tab.active && it.space.active ? t.selected : t.surface).hov\u0065r((s) => s.bg(t.hov\u0065r))
        .tooltip(`Show ${it.space.name} · ${it.tab.name}`)
        .on_click(() => this.showTab(it))
        .child(h_flex().gap(8).items_center()
          .child(this.mark(t, it.tab.status))
          .child(div().flex_1().truncate().text_size(13).font_medium().text_color(t.foreground).child(it.tab.name)))
        .child(h_flex().gap(6).text_size(11.5).text_color(t.muted)
          .child(div().flex_1().truncate().child(this.by === "space" ? `${it.tab.panes} panes` : it.space.name))
          .when(Boolean(what), (el) => el.child(div().flex_none().text_color(t.dim).child(what))));
    };
    const root = v_flex().id("overview-root").size_full().bg(t.background).p(16).gap(12).overflow_y_scrollbar()
      .track_focus(this.focus)
      .on_mouse_down("left", () => this.focus.focus())
      .on_size_change((size, cx) => {
        const cols = cardsPerRow((size?.width ?? 0) - 32);
        if (cols !== this.cols) {
          this.cols = cols;
          cx.notify();
        }
      })
      .on_key_down((e, cx) => {
        const act = overviewKey(e, this.cols);
        if (!act) return;
        cx.stop_propagation();
        if (act.move) {
          const i = moveIndex(selIndex, act.move, order.length);
          if (i >= 0) this.sel = order[i].tab.id;
        } else if (act.open && selected) this.showTab(selected);
        else if (act.group) this.by = this.by === "status" ? "space" : "status";
        cx.notify();
      })
      .child(h_flex().gap(8).items_center()
        .child(div().flex_1().text_size(17).font_semibold().text_color(t.foreground).child(`Overview · ${items.length} tabs`))
        .child(this.toggle(t, "by-status", "By status", "status"))
        .child(this.toggle(t, "by-space", "By space", "space"))
        .child(this.button(t, "overview-close", "Close", "Close this view (Esc)", () => this.dismiss())))
      .child(h_flex().gap(10).flex_wrap().items_center().text_size(11).text_color(t.dim)
        .children([["←↑↓→", "move"], ["Enter", "show the tab"], ["S", "by status or space"], ["Esc", "close"]]
          .map(([k, what], i) => h_flex().id(`okey-${i}`).gap(4).items_center().child(this.hint(t, k)).child(what))));
    if (!sections.length) return root.child(div().text_size(13).text_color(t.muted).child("No tabs."));
    return root.children(sections.map((s, i) => v_flex().id(`section-${i}`).gap(6)
      .child(div().text_size(12).font_semibold().text_color(t.muted).child(`${s.title} · ${s.items.length}`))
      .child(h_flex().flex_wrap().gap(8).children(s.items.map(card)))));
  }

  // --- spaces (Flock) ---
  flockMark(t, s, tab) {
    return div().id(`fm-${tab.id}`).size(16).flex_none().flex().items_center().justify_center().rounded(4)
      .hov\u0065r((x) => x.bg(t.hov\u0065r))
      .tooltip(markTip(tab))
      // A press on a mark is a click on its tab, not the start of a drag of its space.
      .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
      .on_click((_e, cx) => {
        cx.stop_propagation();
        run("space.select", { id: s.id });
        run("tab.select", { id: tab.id });
      })
      .child(this.mark(t, tab.status));
  }

  renderSpaces(t) {
    const list = spaces();
    // The classic list gives each space its color; it may not have started (Flock shown first).
    keepSpaceColors(list);
    const sort = shared(FLOCK_SORT_KEY) === "order" ? "order" : "active";
    // Active: in bands by activity, your order inside a band. The bands stay still while the pointer is on the
    // list, so a row does not move away under a click; a drop still shows at once (the order inside is live).
    // A space that comes while the pointer is there is held from its first band; a removed one drops out.
    this.held = spaceBands(list, this.inside ? this.held : null);
    const bands = sort === "active" ? this.held : null;
    const groups = machineGroups(list).map((g) => (bands ? { ...g, spaces: byActivity(g.spaces, bands) } : g));
    const many = groups.length > 1;
    const fromIndex = this.pressed === null ? -1 : list.findIndex((x) => x.id === this.pressed);
    const row = (s) => {
      const { shown, more } = tabMarks(s.tabs, 5);
      const i = list.findIndex((x) => x.id === s.id);
      const dropHere = this.pressed !== null && this.over === s.id && this.pressed !== s.id;
      const el = h_flex().id(`fs-${s.id}`).relative().h(32).px(this.narrow ? 2 : 8).gap(9).items_center().rounded(7).flex_none()
        .when(this.narrow, (el) => el.justify_center())
        .bg(s.active ? t.selected : t.chrome).hov\u0065r((x) => x.bg(s.active ? t.selected : t.hov\u0065r))
        .tooltip(bands ? `${s.name} (drag to set your order among spaces like it)` : `${s.name} (drag to set your order)`)
        .when(this.pressed === s.id && this.over !== s.id, (el) => el.opacity(0.5))
        // Where the drop puts it: a line under the row when it moves down, above it when it moves up.
        .when(dropHere, (el) => el.child(div().absolute().left(0).right(0).h(2).bg(t.accent)
          .when(fromIndex < i, (line) => line.bottom(0))
          .when(fromIndex > i, (line) => line.top(0))));
      // A drag works in both sorts and keeps the sort. In Active it moves a space among the spaces of its band
      // (the order inside a band is your order); a press and a release on one space is a click.
      const body = el
        .on_mouse_down("left", () => {
          this.pressed = s.id;
          this.over = s.id;
        })
        .on_mouse_move((_e, cx) => {
          if (this.pressed === null) return;
          const over = dragOver(list, this.pressed, s.id, bands);
          if (over !== this.over) {
            this.over = over;
            cx.notify();
          }
        })
        .on_mouse_up("left", (_e, cx) => {
          const from = this.pressed;
          const move = dropMove(list, from, this.over, bands);
          this.pressed = null;
          this.over = null;
          if (move) run("space.move", move);
          else if (from === s.id) run("space.select", { id: s.id });
          cx.notify();
        });
      return body
        .child(div().relative().flex_none().child(spaceTile(s))
          // Folded: the space's most urgent mark sits on its tile's corner.
          .when(this.narrow && Boolean(s.status), (el) => el.child(div().absolute().right(-4).bottom(-4)
            .child(this.mark(t, s.status)))))
        .when(!this.narrow, (el) => el
          .child(div().flex_1().min_w(0).truncate().text_size(13).text_color(s.active ? t.foreground : t.muted).child(s.name))
          .child(h_flex().flex_none().gap(3).items_center()
            .children(shown.map((tab) => this.flockMark(t, s, tab)))
            .when(more.length > 0, (el) => el.child(div().id(`fmore-${s.id}`).px(2).text_size(11).text_color(t.muted)
              .tooltip(more.map(markTip).join("\n"))
              .child(`+${more.length}`)))));
    };
    // A "+" makes a space on that machine, as Herdr's own spaces list does.
    const plus = (id, m) => div().id(id).size(20).flex_none().flex().items_center().justify_center().rounded(5)
      .text_size(14).text_color(t.muted).hov\u0065r((x) => x.bg(t.hov\u0065r).text_color(t.foreground))
      .tooltip(m ? `New space on ${m}` : "New space on this computer")
      .on_click((_e, cx) => {
        cx.stop_propagation();
        run("space.new", { machine: m ?? "" });
      })
      .child("+");
    const items = groups.flatMap((g) => [
      ...(many && !this.narrow
        ? [h_flex().h(26).px(8).pt(6).items_center().flex_none()
          .child(div().flex_1().truncate().text_size(11).font_semibold().text_color(t.dim).child(g.title))
          .child(plus(`flock-new-${g.machine ?? "local"}`, g.machine))]
        : []),
      ...g.spaces.map(row),
    ]);
    const seg = (id, label, value, tip) => div().id(id).px(6).h(18).flex().items_center().rounded(4).text_size(11)
      .bg(sort === value ? t.selected : t.chrome).text_color(sort === value ? t.foreground : t.muted)
      .hov\u0065r((x) => x.text_color(t.foreground)).tooltip(tip)
      .on_click((_e, cx) => {
        cx.stop_propagation();
        this.held = null; // a new sort starts from what happens now, not from bands held before
        setShared(FLOCK_SORT_KEY, value);
        cx.notify();
      })
      .child(label);
    // The header (Active | Order) stays on top; only the spaces scroll, so the sort is always in sight.
    return v_flex().id("flock-root").size_full().min_h(0).px(this.narrow ? 2 : 6).py(4).gap(1)
      // A release outside a row, or the pointer leaving the list, ends a drag without a move. The release waits
      // a tick: a row's own release (the move or the click) runs first, whichever handler the app calls first.
      .on_mouse_up("left", (_e, cx) => {
        cx.timer.after(0, (cx) => {
          if (this.pressed === null) return;
          this.pressed = null;
          this.over = null;
          cx.notify();
        });
      })
      .on_hov\u0065r((inside, cx) => {
        this.inside = inside;
        if (!inside) {
          this.pressed = null;
          this.over = null;
        }
        cx.notify();
      })
      .on_size_change((size, cx) => {
        const narrow = (size?.width ?? 999) < NARROW_PX;
        if (narrow !== this.narrow) {
          this.narrow = narrow;
          cx.notify();
        }
      })
      .when(!this.narrow, (el) => el.child(h_flex().h(26).px(8).items_center().flex_none()
        .child(div().flex_1().text_size(11.5).font_semibold().text_color(t.muted).child("Spaces"))
        .child(h_flex().flex_none().gap(1).p(1).mr(4).rounded(5).border(1).border_color(t.border)
          .child(seg("flock-active", "Active", "active", "By activity, by itself: needs you, finished, working, then idle; inside each, your order (drag to set it)"))
          .child(seg("flock-order", "Order", "order", "Your own order only: drag a space to move it (the Lists show the same order)")))
        .when(!many, (el) => el.child(plus("flock-new", groups[0]?.machine ?? null)))))
      .child(v_flex().id("flock-list").flex_1().min_h(0).gap(1).overflow_y_scrollbar().children(items));
  }

  render(cx) {
    this.props = props() ?? this.props;
    const t = theme();
    if (this.view === "spaces") return this.renderSpaces(t);
    if (this.view === "needs") return this.renderNeeds(t);
    if (this.view === "overview") return this.renderOverview(t);
    return this.renderBar(t);
  }
}
