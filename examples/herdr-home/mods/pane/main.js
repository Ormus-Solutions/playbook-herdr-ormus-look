// Stand-in: only the lines of Herdr 0.1.15 that the Ormus patch looks for (Apache-2.0), around made-up code.
// A pane's header, for layouts that frame their panes:
import { panes, props, run, theme, home, layout } from "herdr";

export default class Pane extends View {
  init() { this.hovered = false; }

  me() {
    return panes().find((p) => p.pane === props()?.pane);
  }

  render() {
    const t = theme();
    const p = this.me();
    const name = ((p.program?.agent || p.program?.shell) && p.program.name) || p.title || p.program?.name || "shell";
    return div()
      .on_click(() => run("pane.focus", { pane }))
      .when(this.hovered, el => el
        .child(div()))
      .child(div().flex_1().truncate().text_color(t.dim).child(folder(p.cwd)));
  }
}
