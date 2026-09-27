---
description: Set up astrafabulopus. Checks Codex and Python, pins the model and default reasoning effort for each lane, installs the status-line tap that feeds the pantry with Claude usage, and offers permission rules so lanes run without a prompt each time.
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

Guide the user through setting up astrafabulopus, one short step at a time. The architect is whatever model this session runs on and is not configured here.

1. **Check the kitchen.** Run `af-doctor`. If `af-doctor` is not found, the plugin's `bin/` is not on the PATH (a lite install): use `.claude/orchestra/bin/af-doctor` and the same prefix for every `af-*` command below. Summarise what is missing. If codex is missing or not logged in, say the Codex lanes need it (`npm i -g @openai/codex && codex login`, then `codex update`) and continue; choices still save.

2. **Probe the Codex slugs** the login accepts, cheaply: for each slug printed by `af-doctor --candidates` run `codex exec -m <slug> -c model_reasoning_effort=low --sandbox read-only --skip-git-repo-check --cd "$(mktemp -d)" "Reply OK" </dev/null` with a 60-second cap (the stdin redirect matters: without it Codex waits for input). Record accepted versus rejected ("not supported when using Codex with a ChatGPT account" means the plan or the CLI version does not expose that model; suggest `codex update` once before giving up on it). Each probe also records a fresh ChatGPT usage reading for the pantry.

3. **Pin the lanes.** Show `af-council recommend routine`, `af-council recommend complex` and `af-council recommend review` so the user sees the Council's view, then ask one AskUserQuestion per group, offering only accepted slugs, most capable first, the current default marked "(Recommended)": implementation lanes (routine, complex, frontier), then advisors (consult, review), then the local lane (enable? which provider and model; only if `lms` or `ollama` is installed). For each implementation lane ask the default effort from that model's rungs (`af-council show <slug>` lists them). Save each choice with `af-council promote <slug> --lane <lane> --effort <rung>` (it writes only the changed keys to `~/.claude/astrafabulopus/lanes.json`). For the local lane, write `{"local": {"enabled": true, "provider": ..., "model": ...}}` into that file with Read and Edit, or Write if it does not exist.

4. **Install the status-line tap** so the pantry can see Claude's 5-hour and 7-day windows. Read `~/.claude/settings.json` (it may not exist). Ask before changing it. If a `statusLine` command already exists, the tap keeps it running in front: `af-pantry install-statusline --chain "<the existing command>"`; otherwise `af-pantry install-statusline`. Set `statusLine` to exactly the JSON the command prints. Say that Claude usage appears after the next response in an interactive session (Pro and Max plans only; API-key logins have no windows).

5. **Offer permission rules** so lanes do not prompt every run. Ask whether to add these to the project's `.claude/settings.json` (or the user's `~/.claude/settings.json`) under `permissions.allow`, merging with what is there:
   `Bash(af-lane:*)`, `Bash(af-consult:*)`, `Bash(af-review:*)`, `Bash(af-verify:*)`, `Bash(af-pantry:*)`, `Bash(af-council:*)`, `Bash(af-doctor:*)`, `Bash(git diff:*)`, `Bash(git status:*)`, `Bash(git log:*)`, `Bash(git show:*)`.

6. **Finish** with `af-doctor` again and `af-pantry --brief`, and print one line per lane: lane, model, effort, enabled. Close with one warm sentence; the user has just set up a kitchen.
