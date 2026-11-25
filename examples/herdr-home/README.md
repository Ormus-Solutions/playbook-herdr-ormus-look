# A synthetic Herdr home

A stand-in for the folder the Herdr desktop app keeps its files in
(`~/.config/herdr-app`), for the demo and the tests. Nothing here is Herdr's
code except the anchor lines the patch looks for, copied from Herdr 0.1.15
(Apache License 2.0). The three mods (`spaces`, `picker`, `pane`) are small
made-up ones around those lines, so the patch has something to find.
`keys.json` stands for your own keys. There is no `programs.json`: the
install makes one and the undo removes it again.
