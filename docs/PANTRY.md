# 🥔 The Pantry

*How much potato is left in each sack, how fast you are eating it, and what to cook instead.*

Two subscriptions power this orchestra. The Claude one pays for judgment: the architect, `opus-implementer`, `fable-advisor` and the verifier. The ChatGPT one pays for typing: Luna, Sol, Astra, `af-review` and `astra-advisor`. Run one dry mid-deliverable and the orchestra does not slow down gracefully. It stops, usually halfway through a spec, usually on a Friday. The Pantry exists so the architect sees the bottom of the sack coming and routes around it.

## Where the numbers come from

The Pantry reads real limits. It never estimates them from token counts, because the vendors' own meters are the only ones that matter.

### ChatGPT (Codex)

Codex writes a session file for every run: `${CODEX_HOME:-~/.codex}/sessions/YYYY/MM/DD/rollout-*.jsonl`. Each model response appends an `event_msg` of type `token_count`, and that event carries the account's rate limits:

```json
{"type": "token_count",
 "info": {"total_token_usage": {"input_tokens": 12000, "cached_input_tokens": 8000, "output_tokens": 900, "reasoning_output_tokens": 400}},
 "rate_limits": {"limit_id": "codex",
                 "primary":   {"used_percent": 42.0, "window_minutes": 300,   "resets_at": 1790000000},
                 "secondary": {"used_percent": 5.0,  "window_minutes": 10080, "resets_at": 1790500000},
                 "credits": {"has_credits": false, "unlimited": false, "balance": null},
                 "plan_type": "plus", "rate_limit_reached_type": null}}
```

The Pantry reads the newest one, preferring `limit_id: "codex"`, the account's main limit. Every `af-lane`, `af-consult` and `af-review` run writes a fresh reading, so the lanes keep the Pantry current for free. Files older than about a week get compressed by Codex (`.jsonl.zst`); those are history, and the Pantry skips them.

### Claude

Since Claude Code 2.1.80, the JSON piped to a status-line command includes `rate_limits.five_hour` and `rate_limits.seven_day`, each with `used_percentage` and `resets_at`, for Pro and Max plans. It appears after the first response of a session. `af-statusline` saves that object to `~/.claude/astrafabulopus/pantry/claude.json` and prints a one-line summary. Your interactive architect session redraws its status line constantly, so the reading stays fresh while you work.

`/astrafabulopus:setup` installs it. If you already have a status line, it keeps yours running in front (`--chain`). The installed launcher finds the plugin wherever the current version lives, so updates don't break it.

### Claude, live (experimental, opt-in)

`af-pantry refresh --claude-oauth` polls `https://api.anthropic.com/api/oauth/usage`, the endpoint behind Claude Code's own `/usage` screen. It uses the OAuth token Claude Code already stores: `~/.claude/.credentials.json` on Linux, or the macOS Keychain item `Claude Code-credentials`. It is **undocumented** and may change without notice. It is never polled automatically, and it waits at least two minutes between polls. It also reports model-scoped windows (`7d opus`, `7d sonnet`) and extra-usage credits when your plan has them. It never refreshes or writes your token.

### Anything else

API credit balances, a team plan you check by hand, OpenRouter:

```
af-pantry set openai-api --balance 12.50 --of 50 --note "API key credits"
af-pantry set team-plan --budget chatgpt --used 70 --window month --resets +9d
af-pantry forget openai-api
```

A manual reading for `claude` or `chatgpt` is only used when there is no automatic one.

## Levels

Each window gets a level. A sack takes the level of its worst window.

| Level | When | Means |
|---|---|---|
| 🥔 **plenty** (raw & plentiful) | under 60% used, and the pace is fine | route by talent, not thrift |
| 🍟 **watch** (frying) | 60% or more used, or 25%+ used and on pace to fill the window before it resets | normal routing, lean on the cheap lanes |
| 🔥 **tight** (crispy) | 85% or more used, or 50%+ used and on pace for 125%+ | route around this sack |
| 💀 **empty** (burnt) | 99.5%+ used, or the vendor says the limit is reached | this sack's lanes report `unavailable` |
| ❔ **unknown** (in the dark) | no reading | unknown is not zero: do not assume headroom |

**Pace.** Here's an example. You've used 50% of a five-hour window, and only a quarter of it has elapsed. That's on pace for 200% at the reset, and you'll run dry in about 75 minutes. The Pantry projects usage once 15% of a window has elapsed (earlier projections are noise) and prints `at this pace: dry in …` when you'll hit the wall before the reset.

**Resets.** A reading whose window has since reset counts as 0% used. The sack refilled; the reading is just old. Readings older than 6 hours (Claude), 12 hours (Codex) or a day (manual) are marked `STALE`.

## What changes when a sack runs low

- **Lanes gate.** `af-lane`, `af-consult` and `af-review` refuse to start on an empty ChatGPT sack. They report `unavailable` with the reset time, instead of failing halfway through a spec. `--ignore-pantry` (or `AF_IGNORE_PANTRY=1`) overrides it; the doctrine says only with the user's say-so. A tight sack adds a `PANTRY:` line to the report.
- **Reports measure.** Each lane report carries a `BUDGET:` line showing how much of each window that run consumed (`5h 58.0% → 59.5% (+1.5)`). The number only appears when the before and after readings describe the same window. Other ChatGPT use during the run gets attributed to it, so treat it as an upper bound.
- **The doctrine reroutes.** `af-pantry advise` holds the rules, and the orchestration skill carries them:
  - **ChatGPT tight:** Luna only. Sol-class work goes to `opus-implementer`. Skip `astra-advisor` and `af-review` unless it's a release.
  - **ChatGPT empty:** the codex lanes are unavailable. Tell the user, then re-route or queue explicitly.
  - **Claude tight:** architect turns short, effort medium. Every build and search goes to the codex lanes, `astra-advisor` handles commitment-boundary checks, and `fable-advisor` does only the final review.
  - **Claude empty:** write down the state and stop. The user decides.
  - **Both low:** only what the user is waiting on. Push mechanical work to the local lane.
- **The Council subtracts pressure.** `af-council recommend` drops candidates on an empty sack and takes points off tight ones. When ChatGPT is tight, Sonnet or the local lane can win work Luna would normally take.

## Commands

```
af-pantry                  # the full pantry
af-pantry --brief          # one line, for the ROUTE block
af-pantry --json           # everything, machine-readable
af-pantry advise           # routing advice only
af-pantry refresh          # re-read Codex now (skips the 30 s cache)
af-pantry gate chatgpt     # exit 3 if empty (what the lanes call)
af-pantry install-statusline [--chain "old command"]
```

## What it reads and writes

- **Reads:**
  - your Codex session files (only the `token_count` events);
  - the status-line payload Claude Code hands it;
  - with `--claude-oauth` only, your Claude Code OAuth token.
- **Writes**, under `~/.claude/astrafabulopus/pantry/`:
  - `claude.json`, the last Claude reading;
  - `codex-cache.json`, a 30-second cache for the status line;
  - `manual.json`, your hand-entered readings.
- **Sends nothing anywhere.** The one exception is the opt-in OAuth poll, which goes to Anthropic's own endpoint, the same one `/usage` calls.
