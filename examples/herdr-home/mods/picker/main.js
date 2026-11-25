// Stand-in: only the lines of Herdr 0.1.15 that the Ormus patch looks for (Apache-2.0), around made-up code.
import { View, div, svg } from "gpui-kit";
import { h_flex } from "gpui-base";

const MARK = { ansi6: "#22a99a", ansi3: "#e3814f", ansi4: "#5b8def", ansi5: "#8b7cf6", ansi2: "#3fae6a", ansi1: "#d9649a" };

export default class Picker extends View {
  render() {
    return div()
      .child(h_flex().size(18).rounded(5).bg(spaceColor(t, r.w)).items_center().justify_center().text_size(10.5).font_bold().text_color("#ffffff").child([...r.w.name][0]?.toUpperCase() ?? "?"));
  }
}
