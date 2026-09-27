---
description: Show how much Claude and ChatGPT subscription usage is left, the pace you are burning it at, and how routing should adjust. Pass "live" to also poll Claude's usage endpoint (experimental).
allowed-tools: Bash
argument-hint: "[live]"
---

Run `af-pantry refresh` (lite install: `.claude/orchestra/bin/af-pantry refresh`). If the arguments contain "live", first run `af-pantry refresh --claude-oauth` and say in one line that it polls an undocumented endpoint and may break without notice.

Show the output verbatim in a code block. Then, in at most two sentences, say what it means for the current work: which lanes to lean on, which to spare, and when the tightest window resets. If a budget is unknown, say so plainly; unknown is not zero.

Arguments: $ARGUMENTS
