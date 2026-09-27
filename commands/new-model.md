---
description: Seat a newly released model on the Potato Council. Research what it is, rate it relative to the nearest model you already know, audition it with af-tryout for real numbers, and promote it to a lane only if it earns it.
allowed-tools: Bash, Read, WebSearch, WebFetch, AskUserQuestion
argument-hint: "<model name or slug>"
---

The user wants to add a new model: $ARGUMENTS

1. **Find out what it is.** Search the vendor's official pages first (release post, model page, pricing page). Collect only facts with a source URL: exact API slug, release date, price per 1M tokens (input / cached / output), context window, supported reasoning efforts, headline coding and agentic benchmark numbers, speed or token-efficiency claims, and any retirement date for the model it replaces. Say "not found" rather than estimating.

2. **Pick the anchor.** Run `af-council` and choose the closest sibling on the Council (same vendor and tier, usually its predecessor). Rating relative to an anchor is the point: you already understand the anchor, so you only need the differences.

3. **Propose the ratings.** For each talent (architecture, implementation, debugging, review, speed, efficiency) propose a bump relative to the anchor, each with its evidence in one line, and show them to the user in a small table. Efficiency follows price times verbosity; speed follows published speed claims; the rest follow the benchmarks, conservatively. Ask the user to confirm or adjust with AskUserQuestion.

4. **Seat it:**
   `af-council add <slug> --like <anchor> --name "<display name>" --released <YYYY-MM-DD> --price <in>/<cached>/<out> --efforts <comma list> --bump <dim>=<+/-n> ... --notes "<one line>" --spud "<which potato it is, and why>"`
   (For a Claude model, add `--run claude` and `--slug <alias>`.) Then `af-council show <slug>`.

5. **Audition it** (ask first: it costs three small lane runs on that model's subscription): `af-tryout <slug>` for Codex or local models. Claude models run as agents: offer to run one small real task through `opus-implementer` with the Agent tool's model override, then `af-council log --model <slug> --verified pass|fail`.

6. **Decide.** Compare with `af-council recommend <task>` for the task classes the model targets. If it now wins a lane the user cares about, offer `af-council promote <slug> --lane <lane> --effort <rung>`. If it replaces a model, offer `af-council retire <old>`. Never promote or retire without the user's yes.

End with the model's card and one line on where it now fits. Welcome it warmly; everyone starts as a small potato.
