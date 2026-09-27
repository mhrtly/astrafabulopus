---
description: Ask the Potato Council. No argument shows every model's talents, prices and observed record; a task (routine, mechanical, complex, frontier, review, consult, architect) gets a budget-aware recommendation; a model name gets its card.
allowed-tools: Bash
argument-hint: "[task | model]"
---

Arguments: $ARGUMENTS

- No argument: run `af-council` and show it verbatim in a code block.
- A task name (routine, mechanical, complex, frontier, review, consult, architect): run `af-council recommend <task> --architect <your own model id, e.g. claude-opus-5-5>` and show it verbatim.
- Anything else: run `af-council show <argument>`; if the model is unknown, offer `/astrafabulopus:new-model <argument>`.

Lite install: prefix the commands with `.claude/orchestra/bin/`. Add at most two sentences of interpretation: the pick, and anything in the output that should change the current route.
