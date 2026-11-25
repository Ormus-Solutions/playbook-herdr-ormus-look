// Ormus cards (playbook-herdr-ormus-look mods/ormus-cards): a board of cards, one per agent, for a pane of a tab.
//   tab tree block: { "content": { "mod": "ormus-cards", "props": { "source": [...], "spot": [...], "title": "..." } } }
// `source`: a command that prints {"cards": [card...]}; `spot`: a command that moves a card's terminal into the
// tab's big pane (the card's id is appended); `tab`: the id of the tab the board is in (as its machine names it).
// Both commands run on that tab's machine, and the board polls only while that tab is shown.
// A card: { id: "t52", title, status: "working" | "blocked" | "done" | "idle" | null, spot: bool, plan: bool,
//           card: { now, summary, question, choices: [{ label, reply }], kind } | null }.
// `kind` (what the card needs from the person) gives the card its color: send, merge, decide, waiting, done.
// A card with `pinned: true` is not an agent of its own (a status card): it has no Spotlight button, and a
// choice pastes its reply into the terminal `to` (the tab's orchestrator, shown in its own pane) without moving
// anything. A pinned card without `to` shows no choices. A pinned card with `lane` (a terminal of the board,
// its owner lane) answers in that lane instead: a choice moves the lane into the big pane and pastes there, as the
// lane's own card does.
// A choice can also be local: `{ label, copy: "text" }` puts the text on the clipboard, `{ label, run: [argv...] }` runs
// that command on the tab's machine and copies the last line it prints. A local choice shows on any card, also a pinned one with nowhere to answer.
// An agent that is stuck (status "blocked") is red whatever its kind. A card that asks while its agent works
// says that the question may be old.
// The card in the big pane (spot) is not shown. A choice moves its agent into the big pane, focuses it and
// pastes the reply without Enter: the person reads it and presses Enter. It pastes only when the focus is on
// that agent; else the reply stays on the clipboard and a toast says so. The board refreshes every POLL_MS
// while its tab is shown.
// An answer typed but not sent (another card was moved into the big pane before Enter) is marked "Not sent" on
// its card until its agent starts a turn or writes its card again. A second choice on that card moves it but types nothing more.
//
// Words used below, in plain words:
//   lane       one terminal that owns one part of the work, usually one agent in one pane of the tab.
//   big pane   the large pane in the middle of the tab (the "middle pane"): it shows one terminal at full size,
//              and the board's cards sit beside it. "Moves a lane into the big pane" means: swap that terminal in.
//   spot       the command that does that swap (the prop `spot`); `source` is the command that prints the cards.

import { View, div, svg } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { panes, props, run, theme, spaces, exec, notify, focused } from "herdr";

const POLL_MS = 4000;

// --- pure helpers (test/test_look.py runs them in node) ---
// The card colors, as #rrggbb (the board adds an alpha part for tints); STUCK uses the theme's "blocked" color,
// which the app's own pane header tints the same way.
const KINDS = {
  send: { label: "Send", color: "#f0883e", about: "a choice sends something to a person" },
  merge: { label: "Merge", color: "#a371f7", about: "a choice merges or deploys code" },
  decide: { label: "Decide", color: "#58a6ff", about: "a rule, design or priority choice" },
  waiting: { label: "Waiting", color: "#8b949e", about: "waits on someone else" },
  done: { label: "Done", color: "#3fb950", about: "nothing open for you" },
};
const STUCK = { label: "Stuck", color: "blocked", about: "the agent cannot go on without you" };

// A card's tone: { label, color } from its agent's status and its kind; null when it has no kind.
function cardTone(kind, status) {
  if (status === "blocked") return STUCK;
  return isKind(kind) ? KINDS[kind] : null;
}

function isKind(kind) {
  return typeof kind === "string" && Object.prototype.hasOwnProperty.call(KINDS, kind);
}

function text(v) {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

// A command as a list of strings, or null (a choice that runs one: see isLocal).
function argvOf(v) {
  if (!Array.isArray(v) || v.length === 0) return null;
  const argv = v.filter((a) => typeof a === "string");
  return argv.length > 0 ? argv : null;
}

// A local choice never pastes into a pane:
// `copy` puts its text on the clipboard; `run` runs a command on the tab's machine and copies the last line it prints.
function isLocal(ch) {
  return Boolean(ch && (ch.copy || (Array.isArray(ch.run) && ch.run.length > 0)));
}

// The last line of a command's output that holds text, or null.
function lastLine(stdout) {
  const lines = String(stdout ?? "").split("\n").map((l) => l.trim()).filter(Boolean);
  return lines.length > 0 ? lines[lines.length - 1] : null;
}

// The command's output as cards, or null when it is not a card list.
function parseCards(stdout) {
  let d;
  try {
    d = JSON.parse(stdout);
  } catch {
    return null;
  }
  if (!d || !Array.isArray(d.cards)) return null;
  return d.cards
    .filter((c) => c && typeof c.id === "string" && c.id)
    .map((c) => {
      const k = c.card && typeof c.card === "object" ? c.card : null;
      return {
        id: c.id,
        title: text(c.title) ?? c.id,
        status: text(c.status),
        spot: c.spot === true,
        plan: c.plan === true,
        pinned: c.pinned === true,
        to: text(c.to),
        lane: text(c.lane),
        card: k && {
          now: text(k.now),
          summary: text(k.summary),
          question: text(k.question),
          choices: (Array.isArray(k.choices) ? k.choices : [])
            .map((x) => (x && text(x.label) ? { label: text(x.label), reply: typeof x.reply === "string" ? x.reply : "", run: argvOf(x.run), copy: text(x.copy) } : null))
            .filter((x) => x && (x.reply.trim() || x.run || x.copy))
            .slice(0, 4)
            // A reply may end in a space ("Change the draft: "): the person types on after it.
            .map((x) => ({ ...x, reply: x.reply.trimStart() })),
          kind: isKind(k.kind) ? k.kind : null,
          updated: text(k.updated),
        },
      };
    });
}

// Where a choice of card `c` goes: "spot" (move its agent into the big pane, then paste), "lane" (a pinned card
// that names its owner lane: move that lane into the big pane, then paste there), "to" (paste into the terminal
// `c.to`, nothing moves) or "none" (a pinned card with nowhere to send the reply).
function answerPath(c) {
  if (!c.pinned) return "spot";
  if (c.lane) return "lane";
  return c.to ? "to" : "none";
}

// The lane card a pinned card answers in: the board's own card for that terminal, else a bare one (the lane may be
// the one in the big pane, which the board does not list).
function laneCard(cards, c) {
  const own = (cards ?? []).find((x) => x.id === c.lane && !x.pinned);
  return own ?? { id: c.lane, title: c.title, status: null, spot: false, plan: false, pinned: false, to: null, lane: null, card: null };
}

// A terminal id on a machine, as the app names it.
function qualify(id, machine) {
  return machine ? `${machine}/${id}` : id;
}

// The board's tab in the app's spaces: { space, tab } for the tab whose id is `id` (bare, or with a machine
// prefix), or null.
function findTab(spaceList, id) {
  if (typeof id !== "string" || !id) return null;
  for (const space of spaceList) {
    const tab = space.tabs.find((t) => t.id === id || t.id.endsWith("/" + id));
    if (tab) return { space, tab };
  }
  return null;
}
// The cards as they are once `id` is in the big pane: the board shows that at once, before the command
// confirms it.
function withSpot(cards, id) {
  return cards.map((c) => (c.spot === (c.id === id) ? c : { ...c, spot: c.id === id }));
}

// The paste's next step for `address`: "paste" once the agent has the focus, "focus" once the app shows its
// pane, else "wait". Asking the app to focus a terminal it does not show yet fails with a toast, and the app
// shows the new layout a moment after the spotlight command returns.
function focusStep(paneList, focusedTerminal, address) {
  if (focusedTerminal === address) return "paste";
  return paneList.some((p) => p.terminal === address) ? "focus" : "wait";
}
// The answers typed but not sent yet, after the refresh number `seq`: `typed` is { [id]: { label, status,
// updated, seq } }, with the agent's status, the card's `updated` and the refresh count when the answer was
// typed. A refresh that started before the paste says nothing about it. After it, the answer is taken once the
// agent goes into "working" or "blocked" from another status (a "Stuck" agent stays blocked until Enter) or
// wrote its card again; "done" and "idle" can change into each other without a turn, so they say nothing. It is
// over when the card is gone.
function typedLeft(typed, cards, seq) {
  const out = {};
  for (const c of cards) {
    const t = typed[c.id];
    if (!t) continue;
    const turn = (c.status === "working" || c.status === "blocked") && c.status !== t.status;
    if (seq > t.seq && (turn || (c.card?.updated ?? null) !== t.updated)) continue;
    out[c.id] = t;
  }
  return out;
}

// A card that still asks while its agent works: the agent went on, so the question may be answered or old.
// What the card says is the lane's own report; the status is what the app measures (an idea from Flockbook,
// which reads what an agent waits for from the agent itself).
function questionMayBeOld(c) {
  return Boolean(c?.card?.question) && c.status === "working";
}

const TYPED_COLOR = "#d29922";
// --- end of pure helpers ---

// Where the board's commands run: its tab's machine, while that tab is shown; else null (then it does not poll).
function shownOn(tabId) {
  const found = findTab(spaces(), tabId);
  if (!found || !found.space.active || !found.tab.active) return null;
  return { on: found.space.machine ?? null };
}

// A tone color: a theme color's name, else the color itself.
function color(t, c) {
  return t[c] ?? c;
}

function why(r) {
  return (r.stderr || r.stdout || `exit ${r.code}`).trim().slice(0, 300);
}

export default class Cards extends View {
  init(p, cx) {
    this.props = props() ?? p ?? {};
    this.cards = null;
    this.error = null;
    this.loading = false;
    this.busy = {};
    this.gen = 0; // bumped by a click: a refresh that started before it is dropped
    this.pending = null; // the card whose move runs now: every refresh shows it moved until the command ends
    this.again = false; // a refresh was asked for while one ran: run it after
    this.typed = {}; // the answers typed into an agent and not sent yet (typedLeft)
    this.seq = 0; // refreshes started
    cx.timer.every(POLL_MS, (cx) => this.refresh(cx));
    this.refresh(cx);
  }

  refresh(cx) {
    const where = shownOn(this.props.tab);
    const argv = this.props.source;
    if (!where || !Array.isArray(argv) || argv.length === 0) return;
    if (this.loading) {
      this.again = true;
      return;
    }
    this.loading = true;
    const { on } = where;
    const gen = this.gen;
    const seq = ++this.seq;
    cx.spawn(async (cx) => {
      try {
        const r = await exec(argv[0], argv.slice(1), { on, timeout: 20000 });
        const got = r.code === 0 ? parseCards(r.stdout) : null;
        if (gen !== this.gen) {
          // A click changed the board while this ran: this answer is from before it.
        } else if (got) {
          this.cards = this.pending ? withSpot(got, this.pending) : got;
          this.typed = typedLeft(this.typed, got, seq);
          this.error = null;
        } else {
          this.error = r.code === 0 ? "the command did not print cards" : why(r);
        }
      } catch (e) {
        this.error = String(e?.message ?? e);
      }
      this.loading = false;
      cx.notify();
      if (gen !== this.gen || this.again) {
        this.again = false;
        this.refresh(cx);
      }
    });
  }

  // Move a card's agent into the big pane; `then(cx, address)` runs when that worked. The board shows the move
  // at once and goes back if the command fails.
  spotlight(c, cx, then, failed) {
    const where = shownOn(this.props.tab);
    const argv = this.props.spot;
    if (!where || !Array.isArray(argv) || argv.length === 0) return;
    if (this.busy[c.id]) {
      // Its move runs already (a second click): an answer for it takes the fallback, never nothing.
      if (failed) failed(cx, where.on);
      return;
    }
    const { on } = where;
    this.busy[c.id] = true;
    const before = this.cards;
    const moved = before ? withSpot(before, c.id) : before;
    this.cards = moved;
    this.pending = c.id;
    this.gen += 1;
    cx.notify();
    cx.spawn(async (cx) => {
      let ok = false;
      try {
        const r = await exec(argv[0], [...argv.slice(1), c.id], { on, timeout: 60000 });
        ok = r.code === 0;
        if (!ok) notify({ title: "Spotlight failed", body: why(r), level: "error" });
      } catch (e) {
        notify({ title: "Spotlight failed", body: String(e?.message ?? e), level: "error" });
      }
      this.busy[c.id] = false;
      if (this.pending === c.id) this.pending = null;
      if (!ok && this.cards === moved) {
        this.cards = before;
        this.gen += 1;
      }
      cx.notify();
      if (ok && then) then(cx, qualify(c.id, on));
      if (!ok && failed) failed(cx, on);
      this.refresh(cx);
    });
  }

  // A local choice: copy its text, or run its command on the tab's machine and copy the last line it prints.
  chooseLocal(ch, cx) {
    if (ch.copy) {
      cx.write_to_clipboard(ch.copy);
      notify({ title: "Copied", body: ch.copy.slice(0, 200), level: "info" });
      return;
    }
    const where = shownOn(this.props.tab);
    const key = `local:${ch.label}`;
    if (!where || this.busy[key]) return;
    this.busy[key] = true;
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        const r = await exec(ch.run[0], ch.run.slice(1), { on: where.on, timeout: 120000 });
        const line = r.code === 0 ? lastLine(r.stdout) : null;
        if (line) {
          cx.write_to_clipboard(line);
          notify({ title: `${ch.label}: copied`, body: line.slice(0, 200), level: "info" });
        } else {
          notify({ title: `${ch.label} failed`, body: r.code === 0 ? "the command printed nothing" : why(r), level: "error" });
        }
      } catch (e) {
        notify({ title: `${ch.label} failed`, body: String(e?.message ?? e), level: "error" });
      }
      this.busy[key] = false;
      cx.notify();
      this.refresh(cx);
    });
  }

  choose(c, reply, cx) {
    const path = answerPath(c);
    if (path === "to") {
      const where = shownOn(this.props.tab);
      if (where) this.paste(qualify(c.to, where.on), reply, cx, 0);
      return;
    }
    const label = c.card?.choices?.find((ch) => ch.reply === reply)?.label ?? "your answer";
    if (path === "lane") {
      // A lane that cannot be moved (it stopped, or the card names a wrong one) must not lose the answer: it goes
      // to the orchestrator as before, else to the clipboard.
      this.answerIn(laneCard(this.cards, c), reply, label, cx, (cx, on) => {
        if (c.to) {
          this.paste(qualify(c.to, on), reply, cx, 0);
          return;
        }
        cx.write_to_clipboard(reply);
        notify({ title: "Answer on the clipboard", body: "Its lane could not be moved into the big pane. Paste it where it belongs (Ctrl+Shift+V).", level: "warning" });
      });
      return;
    }
    if (path !== "spot") return;
    this.answerIn(c, reply, label, cx);
  }

  // Move the agent of card `c` into the big pane and paste the reply into it (not sent: the person presses Enter).
  answerIn(c, reply, label, cx, failed) {
    if (this.typed[c.id]) {
      // Its input has an answer already: a second paste would join the two. Move it only.
      delete this.typed[c.id];
      this.spotlight(c, cx);
      notify({
        title: "An answer is typed already",
        body: `"${c.title}" has an answer in its input that is not sent. Press Enter to send it, or clear the line and pick again.`,
        level: "warning",
      });
      return;
    }
    const typedNow = () => {
      // The card as the board has it now, not as it was at the click (the move can take a while).
      const now = this.cards?.find((x) => x.id === c.id) ?? c;
      this.typed[c.id] = { label, status: now.status ?? null, updated: now.card?.updated ?? null, seq: this.seq };
    };
    if (c.spot) {
      // Already in the big pane: paste at once, with no move and no write of the tab.
      const where = shownOn(this.props.tab);
      if (where) this.paste(qualify(c.id, where.on), reply, cx, 0, typedNow);
      return;
    }
    this.spotlight(c, cx, (cx, address) => this.paste(address, reply, cx, 0, typedNow), failed);
  }

  // Wait for the agent's pane, focus it, then paste the reply only when the focus is on it (focusStep). The person's clipboard text comes back after the paste. Limits: a clipboard that
  // held no text (an image) keeps the reply, and a copy made in the 800 ms before the restore is replaced.
  paste(address, reply, cx, tries, pasted) {
    let step = focusStep(panes(), focused()?.terminal ?? null, address);
    if (step === "focus") {
      run("pane.focus", { terminal: address });
      step = focusStep(panes(), focused()?.terminal ?? null, address);
    }
    if (step === "paste") {
      const old = cx.read_from_clipboard();
      cx.write_to_clipboard(reply);
      run("terminal.paste");
      if (pasted) pasted();
      cx.timer.after(800, (cx) => {
        if (old !== undefined) cx.write_to_clipboard(old);
      });
      return;
    }
    if (tries >= 20) {
      cx.write_to_clipboard(reply);
      notify({
        title: "Answer on the clipboard",
        body: "The agent's pane did not take the focus. Click its pane and paste (Ctrl+Shift+V).",
        level: "warning",
      });
      return;
    }
    cx.timer.after(250, (cx) => this.paste(address, reply, cx, tries + 1, pasted));
  }

  pill(t, id, label, tip, onClick) {
    return div()
      .id(id)
      .flex_none()
      .px(6)
      .h(20)
      .flex()
      .items_center()
      .rounded(5)
      .border(1)
      .border_color(t.border)
      .text_size(11)
      .font_medium()
      .text_color(t.dim)
      .hov\u0065r((s) => s.bg(t.hov\u0065r).text_color(t.foreground))
      .tooltip(tip)
      .on_click((_e, cx) => {
        cx.stop_propagation();
        onClick(cx);
      })
      .child(label);
  }

  state(t, st) {
    if (st === "working") return svg("mods/ormus-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900);
    if (st === "blocked") {
      return div().flex_none().px(6).h(18).flex().items_center().rounded(5).bg(t.blocked + "26").text_size(10.5)
        .font_semibold().text_color(t.blocked).child("Needs you");
    }
    if (st === "done") return div().size(7).flex_none().rounded(4).bg(t.done);
    return div().flex_none().text_size(10.5).text_color(t.dim).child(st ? "Idle" : "");
  }

  choiceButton(t, c, ch, i, col) {
    return div()
      .id(`choice-${c.id}-${i}`)
      .flex_none()
      .px(10)
      .h(26)
      .flex()
      .items_center()
      .rounded(6)
      .border(1)
      .border_color(col)
      .bg(t.raised)
      .text_size(12)
      .font_medium()
      .text_color(t.foreground)
      .hov\u0065r((s) => s.bg(col + "40"))
      .tooltip(isLocal(ch) ? (ch.copy ? `Copies: ${ch.copy}` : "Runs a command and copies the last line it prints")
        : answerPath(c) === "lane" ? `Moves its lane into the big pane and types there: "${ch.reply}" (you press Enter)`
        : c.pinned ? `Types into the orchestrator: "${ch.reply}" (you press Enter)` : `Types into this agent: "${ch.reply}" (you press Enter)`)
      .on_click((_e, cx) => {
        cx.stop_propagation();
        if (isLocal(ch)) this.chooseLocal(ch, cx);
        else this.choose(c, ch.reply, cx);
      })
      .child(this.busy[`local:${ch.label}`] ? "Working..." : ch.label);
  }

  // A small colored label: the card's kind.
  chip(label, col) {
    return div().flex_none().px(6).h(18).flex().items_center().rounded(5).bg(col + "26").text_size(10.5)
      .font_semibold().text_color(col).child(label);
  }

  legend(t) {
    return h_flex().flex_none().flex_wrap().gap(10).px(2).text_size(11).text_color(t.dim).children(
      [...Object.values(KINDS), STUCK].map((k) => h_flex().id(`legend-${k.label}`).gap(4).items_center().tooltip(k.about)
        .child(div().size(8).rounded(4).bg(color(t, k.color)))
        .child(k.label)));
  }

  cardView(t, c) {
    const k = c.card;
    const choices = k?.choices ?? [];
    const shown = answerPath(c) === "none" ? choices.filter(isLocal) : choices;
    const tone = cardTone(k?.kind, c.status);
    // A status card shows the mark of the lane it answers in: that lane's own card is hidden while in the big pane.
    const typed = this.typed[c.id] ?? (c.pinned && c.lane ? this.typed[c.lane] : undefined);
    const col = tone ? color(t, tone.color) : t.accent;
    return v_flex()
      .id(`card-${c.id}`)
      .flex_none()
      .gap(6)
      .p(10)
      .rounded(8)
      .border(1)
      .border_l(4)
      .border_color(tone ? col + "aa" : k?.question ? t.accent : t.border)
      .bg(t.surface)
      .child(
        h_flex()
          .gap(8)
          .items_center()
          .child(div().flex_1().truncate().font_semibold().text_color(t.foreground).child(c.title))
          .when(Boolean(typed), (el) => el.child(this.chip("Not sent", TYPED_COLOR)))
          .when(Boolean(tone), (el) => el.child(this.chip(tone.label, col)))
          .child(this.state(t, c.status))
          .when(!c.pinned, (el) => el.child(this.pill(t, `spot-${c.id}`, this.busy[c.id] ? "Moving..." : "Spotlight",
            "Show this agent's terminal in the big pane", (cx) => this.spotlight(c, cx)))),
      )
      .when(Boolean(typed), (el) => el.child(div().text_size(11.5).font_semibold().text_color(TYPED_COLOR)
        .child(c.pinned ? `"${typed?.label}" is typed in its lane, not sent. Press Enter in the middle pane.`
          : `"${typed?.label}" is typed in its input, not sent. Spotlight it and press Enter.`)))
      .when(Boolean(k?.now), (el) => el.child(div().text_size(11.5).text_color(t.dim).child(k.now)))
      .when(Boolean(k?.summary), (el) => el.child(div().text_color(t.foreground).child(k.summary)))
      .when(!k, (el) => el.child(div().text_color(t.dim).child(c.plan ? "No card yet. Its plan file is written." : "No card yet.")))
      .when(Boolean(k?.question), (el) => el.child(div().font_semibold().text_color(t.foreground).child(k.question)))
      .when(questionMayBeOld(c), (el) => el.child(div().text_size(11.5).text_color(t.dim)
        .child("It works now, so this question may be old. Check that it still asks.")))
      .when(shown.length > 0, (el) => el.child(h_flex().flex_wrap().gap(6).children(shown.map((ch, i) => this.choiceButton(t, c, ch, i, col)))));
  }

  render(cx) {
    this.props = props() ?? this.props;
    const t = theme();
    const root = v_flex().id("cards-root").size_full().bg(t.background).text_size(12.5).overflow_y_scrollbar().p(8).gap(8);
    if (!this.cards) {
      return root.child(div().p(8).text_color(t.dim).child(this.error ? `No cards: ${this.error}` : "Loading the cards..."));
    }
    const shown = this.cards.filter((c) => !c.spot);
    return root
      .child(this.legend(t))
      .when(Boolean(this.error), (el) => el.child(div().text_size(11).text_color(t.blocked).child(`The last refresh failed: ${this.error}`)))
      .when(shown.length === 0, (el) => el.child(div().p(8).text_color(t.dim).child("No other agents.")))
      .children(shown.map((c) => this.cardView(t, c)));
  }
}
