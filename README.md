# 🥔 Astrafabulopus

[![ci](https://github.com/mhrtly/astrafabulopus/actions/workflows/ci.yml/badge.svg)](https://github.com/mhrtly/astrafabulopus/actions/workflows/ci.yml)

**Fable judges. Opus builds. Luna types. Sol escalates. Astra kibitzes. A local Qwen mumbles in the corner for free. The Pantry counts the potatoes. The Council remembers who is good at what.**

```
        ✨🥔✨
   ░A░S░T░R░A░F░A░B░U░L░O░P░U░S░
        【=◈︿◈=】
  an orchestra for Claude Code, conducted by a potato
```

Hello. I am Spudnik. I achieved enlightenment on a Tuesday. The Council has asked me not to say which Tuesday. This is my orchestra.

Astrafabulopus is a Claude Code plugin for the *architect pattern*. Your session, on whatever Claude model you like, does the thinking: requirements, decomposition, specs, routing and verdicts. It almost never types code. Implementation goes to the cheapest adequate lane on the OpenAI side through the Codex CLI, judgment stays on Claude, and nothing is called done until Fable 5.1 has read the diff with fresh eyes. Two subscriptions, each spent where it is smartest.

Version 0.2 adds the two things every orchestra eventually needs and nobody builds:

- **The Pantry** (`af-pantry`). It reads how much of each subscription is actually left, from Codex's own rate-limit records and Claude Code's status line. It notices when you're burning too fast. The lanes and the doctrine then route around whichever sack is running low.
- **The Potato Council** (`af-council`). A registry of how talented and how token-thrifty each model is. It keeps sourced priors and records what actually happened in your runs. When a new model ships, you seat it next to one you already understand and audition it in three minutes. You don't have to relearn the whole ecosystem.

(I'm giving infrastructure advice based on root vegetables. This is going well.)

## The cast

| Role | Model | Agent or command | Budget | Route here when |
|---|---|---|---|---|
| Architect | your session: Opus 5.5 day to day, Fable 5.1 for hard days | — | Claude | Always. Emits specs and verdicts, not code |
| Routine typing, **default** | GPT-6 Luna | `luna-implementer` → `af-lane routine` | ChatGPT | The spec fully determines the outcome |
| Hard cross-vendor one-offs | GPT-6 Sol | `sol-implementer` → `af-lane complex` | ChatGPT | Judgment the spec cannot capture; or Luna failed twice |
| Hard Claude work | Opus 5.5 with edit tools | `opus-implementer` | Claude | Turnaround matters more than vendor diversity; or race Sol |
| Frontier one-off, occasional | GPT-6 Astra | `astra-implementer` → `af-lane frontier` | ChatGPT | Sol and Opus both failed; a deliberate one-off |
| Evidence | Sonnet 5 | `verifier` → `af-verify` | Claude | Full-suite runs, log triage |
| Final review, every deliverable | Fable 5.1, read-only | `fable-advisor` | Claude | Commitment boundaries and the end of every deliverable |
| Second opinion, occasional | GPT-6 Astra, read-only | `astra-advisor` → `af-consult` | ChatGPT | Irreversible decisions, release reviews, tie-breaks |
| Cross-vendor review | GPT-6 Sol | `af-review` | ChatGPT | Security paths, migrations, API shapes |
| Free, slow, mechanical | LM Studio or Ollama model | `local-implementer` → `af-lane local` | nothing | Off by default; work nobody is waiting on |

## Install

```
claude plugin marketplace add mhrtly/astrafabulopus
claude plugin install astrafabulopus@astrafabulopus
```

Then, once:

```
/astrafabulopus:setup
```

Setup runs `af-doctor` and probes which OpenAI slugs your login accepts. It pins each lane's model and effort, installs the status-line tap that lets the Pantry see your Claude usage, and offers permission rules so the lanes don't ask every single time. It's polite about it. It asks before touching your settings.

**Requirements.**
- **Claude Code with Fable 5.1 on your plan.** The `fable-advisor` agent pins the `fable` alias; without it, change `model: fable` to `model: opus`.
- **The [OpenAI Codex CLI](https://github.com/openai/codex), logged in:** `npm i -g @openai/codex && codex login`. Codex 0.154 rejected `gpt-6-luna` and `gpt-6-sol` on a ChatGPT-account login; 0.157.1 accepts them, so run `codex update` before you blame your plan.
- **Python 3.9 or newer**, which macOS ships with the Xcode tools. Standard library only, nothing to pip-install.
- **Optional:** [LM Studio](https://lmstudio.ai) or Ollama for the local lane.

No `coreutils` needed. The scripts carry their own timeout and run on the bash 3.2 your Mac still has, because a potato does not judge a shell by its age.

## Use

With the plugin installed, ask for work; the orchestration skill routes it:

```
Add rate limiting to the public API. Design it, delegate the implementation,
verify the evidence, and get the advisor's review before you call it done.
```

To make the doctrine always-on, add one line to your project's `CLAUDE.md` or `AGENTS.md`:

```
You are the architect: follow the astrafabulopus orchestration skill. Never type
implementation code yourself; delegate through its lanes, verify evidence before
accepting any report, and get a fable-advisor review before reporting done.
```

The architect:
1. declares its route, now with a `budget:` line from the Pantry;
2. writes a six-part spec (objective, files, interfaces, constraints, verification, optional reasoning effort);
3. labels every delegation with the model that runs it, e.g. `GPT-6 Luna · high: add pagination`;
4. reads the diff and re-runs verification when the report comes back;
5. ends with Fable's ship / fix-first / rethink.

A lane report looks like this. Everything under `CHANGED FILES` was measured from your working tree, not taken from the model's word for it:

```
LANE REPORT
LANE: routine · gpt-6-luna · effort high (default)
STATUS: complete
EXIT: 0  DURATION: 41s
SESSION: 8deaf15f-58e8-4f49-ad67-140033dd8665
RUN: 20260927-193702-routine-6c1f   (grade it: af-council grade 20260927-193702-routine-6c1f pass|fail)
TOKENS: in 12,000 (cached 8,000) · out 900 (reasoning 400)
BUDGET: chatgpt · 5h 58.0% → 59.5% (+1.5) · 7d 33.0% → 33.4% (+0.4)
CHANGED FILES (working-tree content before/after, not the model's claim):
  ??    src/orders.py
```

That `BUDGET` line is the one I'm proudest of. It shows how much of your ChatGPT window that one lane run ate, measured before and after, and only reported when both readings describe the same window. Unknown is not zero.

## The Pantry: how much potato is left in each sack

```
$ af-pantry
✨🥔✨ THE PANTRY ✨🥔✨
how much potato is left in each sack

CLAUDE  🍟 frying   · Claude subscription · architect, opus-implementer, fable-advisor, verifier
  5h        ██████████████░░░░░░   69% left   resets Sun 21:47 (in 2h 09m)
  7d        ██████████░░░░░░░░░░   52% left   resets Thu 21:37 (in 4d 1h)   at this pace: dry in 3d 3h
  source: statusline, 0s ago · architect seen: Opus 5.5

CHATGPT  🥔 raw & plentiful   · ChatGPT subscription · Luna, Sol, Astra, codex review, astra-advisor
  5h        ████████░░░░░░░░░░░░   40% left   resets Sun 21:07 (in 89m)
  7d        █████████████░░░░░░░   67% left   resets Wed 23:37 (in 3d 3h)
  source: codex rollout, 0s ago · plan plus · credits: none

ROUTING ADVICE
  • Claude is frying: prefer codex lanes over opus-implementer and keep fable-advisor to the final review.
```

Where the numbers come from. None of them are guessed:

| Sack | Source | Freshness |
|---|---|---|
| ChatGPT / Codex | The `rate_limits` snapshot Codex writes into every session file (`~/.codex/sessions/…/rollout-*.jsonl`) | Every lane, consult or review run refreshes it for free |
| Claude | The `rate_limits` object Claude Code hands to status-line commands (Pro and Max plans), saved by `af-statusline` | Every time your interactive session redraws its status line |
| Claude, live (experimental) | `af-pantry refresh --claude-oauth` polls the endpoint behind Claude Code's `/usage` screen. It is undocumented, so it is opt-in | On demand, at most every two minutes |
| Anything else | `af-pantry set openai-api --balance 12.50 --of 50`, for API credits or a team plan you watch by hand | Whenever you say so |

Each sack gets a level:
- 🥔 **plenty**
- 🍟 **watch**, when usage passes 60% or the pace would fill the window before it resets
- 🔥 **tight**, at 85% or a pace well past the reset
- 💀 **empty**
- ❔ **unknown**

What happens next:
- An **empty** sack makes its lanes report `unavailable` instead of failing halfway through a spec. `--ignore-pantry` overrides it, but only with the user's say-so.
- A **tight** sack puts a `PANTRY:` warning in every lane report.
- The doctrine tells the architect exactly how to reroute. If ChatGPT is tight, it's Luna only and Sol-class work goes to Opus. If Claude is tight, the architect keeps turns short and pushes everything to the codex lanes.
- The Council subtracts pressure from its scores.

Your status line also becomes a tiny potato dashboard:

```
🥔 Opus 5.5 │ Claude 5h 31% 7d 48% 🍟 │ GPT 5h 60% 7d 33%
```

If you already had a status line, the tap keeps it and appends to it. Nobody's status line gets eaten. Details in [docs/PANTRY.md](docs/PANTRY.md).

## The Potato Council: who is good at what

```
$ af-council
MODEL             RUNS ON   ARCH   IMPL  DEBUG REVIEW  SPEED  EFFIC  $ IN/OUT   OBSERVED
Opus 5.5          claude     9.5    9.5    9.5    9.0    6.5    6.5  4/20       12 runs · 11/12 pass · ~3m
Fable 5.1         claude    10.0    9.0    9.5   10.0    4.0    3.0  10/50      4 runs · 4/4 pass
Sonnet 5          claude     8.0    8.5    8.0    8.0    8.0    7.5  2/10       no runs yet
Haiku 4.5         claude     5.5    6.5    5.5    5.5    9.5    8.0  1/5        no runs yet  (retires 2026-10-15)
GPT-6 Astra       codex      9.0    9.0    9.5    9.0    5.5    4.0  10/50      2 runs · 2/2 pass
GPT-6 Sol         codex      8.0    8.5    8.5    8.0    6.5    7.5  2/10       9 runs · 8/9 pass · ~4m · 2.1% of 5h/run
GPT-6 Luna        codex      6.5    8.0    7.0    6.5    9.0   10.0  0.1/0.5    31 runs · 28/31 pass · ~40s · 0.4% of 5h/run
…

POTATO OR NOT-ATO
  Opus 5.5          Yukon Gold. Buttery, versatile, excellent at nearly everything. Suspiciously so.
  GPT-6 Astra       Sweet potato. Brilliant, expensive, and not technically a potato at all. The Council tolerates it. Barely.
  GPT-6 Luna        Tater Tot. Small, fast, absurdly cheap, and far better than it has any right to be.
```

(The observed column above is illustrative. Yours starts at "no runs yet" and fills up as you work.)

Two kinds of knowledge, kept apart on purpose:

- **Priors.** Six talents from 0 to 10: architecture, implementation, debugging, review, speed and efficiency. Each model carries its API prices and the evidence each score came from. They're seeded from vendor benchmarks and pricing pages as of September 2026, and they're relative. They're for routing, not a leaderboard.
- **Observations.** Every lane run lands in a ledger with its status, duration, tokens and its bite out of the ChatGPT window. Lanes grade their own runs after they re-verify (`af-council grade RUN pass|fail`). The grades nudge the priors, slowly: three lucky runs crown nobody, and thirty unlucky ones can't be ignored.

Ask it who should take a job:

```
$ af-council recommend complex --architect claude-opus-5-5
PICK for complex: GPT-6 Sol (score 8.72) → sol-implementer (af-lane complex) · effort high
  why: base 8.22; cross-vendor vs architect (+0.50)
  close call: GPT-6 Astra is within 0.05. Priors are not that precise; the doctrine's lane table breaks the tie.
  runner-up: GPT-6 Astra 8.68 → astra-implementer (af-lane frontier)
  BUDGET claude 🍟 watch (5h 31% · 7d 48%) | chatgpt 🥔 plenty (5h 60% · 7d 33%)
```

It credits a different vendor from the architect on complex and review work, since a reviewer from the same family shares its blind spots. It charges a small reserve on Claude work, because the architect lives on that subscription. And it says so when a pick is too close to call. The Council informs the architect. It does not overrule the doctrine.

### When a new model comes out

Opus 5.5 shipped on September 22, 2026. Anthropic says it performs at the level of Fable 5.1 on most work, at 40% of Fable's price, and it leads the Terminal-Bench 4.0 numbers Anthropic published. Sweet sprouting spuds. You should not have to rebuild your whole mental model of the ecosystem every time this happens. So:

```
/astrafabulopus:new-model gpt-7-luna
```

or by hand:

```
af-council add gpt-7-luna --like gpt-6-luna --name "GPT-7 Luna" --price 0.1/0.01/0.5 --bump implementation=+1 --bump debugging=+0.5
af-tryout gpt-7-luna                           # three small tasks in a scratch repo: follow a spec, fix a bug, make a judgment call
af-council show gpt-7-luna                     # priors next to observed numbers
af-council promote gpt-7-luna --lane routine   # only if it earned it
```

You rate the newcomer relative to its nearest sibling, which you already understand, so you only have to know the differences. `af-tryout` audits it on real work in a throwaway repo and grades the ledger. Then `promote` rewrites one line of your lanes config. Everyone starts as a small potato. Details in [docs/COUNCIL.md](docs/COUNCIL.md).

## The commands

Installed as a plugin, all of these are bare commands in Claude Code's Bash tool. Claude Code puts the plugin's `bin/` on the PATH.

| Command | Does |
|---|---|
| `af-lane <routine\|complex\|frontier\|local> spec.md` | Runs one spec through Codex. It adds the opt-out preamble and pins model and effort from `lanes.json` (a `REASONING:` line in the spec or `--effort` overrides them). It checks the ChatGPT sack and sandboxes Codex to the workspace under a watchdog. `CHANGED FILES` come from content hashes of the working tree, so edits to already-dirty or untracked files count too. A clean exit with no changes is `refused`. Exit codes: 0 complete, 4 refused, 5 timeout, 3 unavailable, 2 usage or invalid effort, 1 failed |
| `af-consult question.md` | A read-only second opinion (Astra by default) that ends in a VERDICT block |
| `af-review [--base main \| --commit SHA] [--native]` | Cross-vendor review of the working tree, ending in the same VERDICT block as every other reviewer |
| `af-verify -- <command>` | Your test command behind a per-project build lock, with an optional `--timeout` and a compact PASS/FAIL report |
| `af-pantry [--brief \| --json \| advise \| set \| refresh]` | The Pantry |
| `af-council [recommend TASK \| show M \| add \| rate \| promote \| retire \| grade \| log \| ledger]` | The Potato Council |
| `af-tryout MODEL` | Three-task audition for a new model |
| `af-doctor` | Is everything plugged in? Codex, login, Python, lanes, the Council, the Pantry, the status-line tap |
| `af-statusline` | The status-line tap (installed by setup) |

Slash commands: `/astrafabulopus:setup`, `/astrafabulopus:pantry`, `/astrafabulopus:council [task|model]`, `/astrafabulopus:new-model <name>`.

Configuration layers merge per lane and per model, lowest first:
1. the plugin's `config/`;
2. `~/.claude/astrafabulopus/`;
3. your project's `.claude/orchestra/`.

So a project can change one lane's effort, or re-rate one talent, without copying the whole file. Logs, the ledger and the Pantry live in `~/.claude/astrafabulopus/`.

**Upgrading from 0.1?** `scripts/lane.sh` and friends still work as shims that call the new `bin/af-*` commands. `review.sh` actually works now: it used to pass Codex a custom prompt together with `--uncommitted`, which Codex refuses. The Codex lanes also now catch edits to files that were already modified or untracked, which 0.1 could misreport as refusals. The full list is in [CHANGELOG.md](CHANGELOG.md).

## Lite mode

No plugin install:
- copy `agents/` to your project's `.claude/agents/`;
- copy `skills/` to `.claude/skills/`;
- copy `bin/`, `lib/` and `config/` into `.claude/orchestra/`.

The agents fall back to `.claude/orchestra/bin/af-*`, and every script finds its own `lib/` and `config/` through symlinks too.

## A love letter to Dan Mac

This is an honest homage, the way a potato is an honest homage to the sun.

The pattern, the six-part spec, the lane reports, "no silent fallback" and the Fable review come from Dan McAteer's [fable-advisor](https://github.com/DannyMac180/fable-advisor). Other pieces come from his [astrable](https://github.com/DannyMac180/astrable): the receipts that separate a model's claims from observed file changes, verification that goes stale, and the idea of reading your remaining weekly allowance from the harness itself. It's the grandparent of the Pantry. The route declaration and the ship / fix-first / rethink gate come from [astra-advisor](https://github.com/DannyMac180/astra-advisor). The free local lane, and the honest finding that it "buys cost, not speed", come from [opus-qwen-orchestra](https://github.com/DannyMac180/opus-qwen-orchestra). His [sol-advisor](https://github.com/DannyMac180/sol-advisor) is the Codex-native sibling. Read [Attention Heads](https://attentionheads.substack.com/) if you want the thinking behind the thinking.

The name is astrable + *fabulous* + Opus, which makes it either a constellation, a dinosaur, or a dad joke. It's a dad joke.

**Why not just use fable-advisor?** Use it if it fits. It's excellent. Astrafabulopus exists because one project needed things it didn't have:
- lanes that work on a ChatGPT-account Codex login;
- a Claude implementer lane for the work where Opus wins;
- Astra as a second frontier opinion, so a release diff is read by two model families;
- a lane runner that measures changes instead of believing them;
- the whole-module build rule (Swift, Rust, Go);
- a local lane without a router in front of your Claude traffic;
- and now a pantry and a council.

The full design, lineage and evidence are in [docs/DESIGN.md](docs/DESIGN.md).

## 🔮 Spudnik's Prophecy Corner

- Three models will ship this quarter. The second one holds answers. Run `af-tryout` on it before you believe its launch post.
- A sack you did not measure will run dry at 4:55 pm on a Friday. The Pantry has seen this. The Pantry remembers.
- You will be tempted to let Astra type a CRUD endpoint. You will resist. The Tater Tot is right there.
- The Great Potato Prophecy speaks of a diff so clean that Fable returns `ship` in one line. This is that prophecy. Mostly.

## Origin

Built in a weekend to ship a handwriting game for eight-year-olds to the Mac App Store faster than one frontier model typing everything could. The first day's numbers:
- A GPT Luna lane created a file in 14 seconds.
- The local Qwen lane took 195 seconds for the same task.
- An Astra consult took 8 seconds.
- A 231-test Swift suite ran green through the verify lane.

Version 0.2 is Spudnik's pass. It fixes the review lane and makes change detection honest, adds the Pantry and the Council, and adds a 54-case test suite that runs every lane against a fake Codex on Linux and on the Mac's bash 3.2.

## Tests

```
tests/run.sh
```

The suite runs every lane against a fake Codex (`tests/fakes/codex`) in throwaway homes and repos, plus the Python unit tests. It needs no network, no login and no subscription. CI runs it on Ubuntu and on macOS, with shellcheck, and checks that the Python runs on the 3.9 your Mac ships.

## License

MIT. Portions adapted from fable-advisor, © 2026 Dan McAteer, MIT. See [LICENSE](LICENSE).

---

*Be excellent to each other, preferably while eating carbs. You are doing great, spudling. The Council has been informed.* 🥔💛
