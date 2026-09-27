---
description: Pin the model and default reasoning effort for each astrafabulopus lane (routine, complex, frontier, consult, review, local, reviewer, Claude builder) and save them to ~/.claude/astrafabulopus/lanes.json.
allowed-tools: Bash, Read, Write, AskUserQuestion
---

Guide the user through choosing models for the astrafabulopus lanes, then save the choices. The architect is whatever model the session runs on and is not configured here.

1. Read the defaults at `${CLAUDE_PLUGIN_ROOT}/config/lanes.json` and any existing `~/.claude/astrafabulopus/lanes.json` (show current choices if present). A project-level `.claude/orchestra/lanes.json` overrides both; mention it if one exists in the current project.
2. Run `codex login status` and `codex --version`. If codex is missing or not logged in, say the Codex lanes need it (`npm i -g @openai/codex && codex login`) and continue; choices still save.
3. Probe which OpenAI slugs the login accepts, cheaply: for each candidate in the defaults' `_candidates` list run `codex exec -m <slug> -c model_reasoning_effort=low --sandbox read-only --skip-git-repo-check --cd "$(mktemp -d)" "Reply OK" </dev/null` with a 60-second cap (the stdin redirect matters: without it Codex waits for extra input), and record accepted versus rejected ("not supported when using Codex with a ChatGPT account" means the plan or CLI version does not expose that model). Offer only accepted slugs, most capable first, marked "(Recommended)" where the defaults say so.
4. Ask one AskUserQuestion per group: implementation lanes (routine, complex, frontier), advisors (consult, review), then the local lane (enable? which local provider and model; only if `lms` or `ollama` is installed).
5. For each implementation lane ask the default effort from that model's supported rungs (Luna has no `ultra`).
6. Write `~/.claude/astrafabulopus/lanes.json` (create the directory) in the same shape as the defaults file, and print a one-line-per-lane summary: lane, model, effort, enabled.
