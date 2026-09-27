# Astrafabulopus

**Fable judges. Opus builds. Luna types. Sol escalates. Astra kibitzes. A local Qwen mumbles in the corner for free.**

Astrafabulopus is a Claude Code plugin for the *architect pattern*: your session, on whatever Claude model you like, does the thinking — requirements, decomposition, specs, routing, verdicts — and almost never types code. Implementation goes to the cheapest adequate lane on the OpenAI side through the Codex CLI, judgment stays on Claude, and nothing is called done until Fable 5.1 has read the diff in a clean context. Two subscriptions, each spent where it is smartest.

The name is [astrable](https://github.com/DannyMac180/astrable) + *fabulous* + Opus, which makes it either a constellation, a dinosaur, or a dad joke. It is a dad joke, and an honest homage: the pattern, the spec contract, the lane reports and the Fable review come from Dan McAteer's [fable-advisor](https://github.com/DannyMac180/fable-advisor); the receipts, route declaration and the free local lane from his [astrable](https://github.com/DannyMac180/astrable), [astra-advisor](https://github.com/DannyMac180/astra-advisor) and [opus-qwen-orchestra](https://github.com/DannyMac180/opus-qwen-orchestra). What is new is in [docs/DESIGN.md](docs/DESIGN.md). Read Dan's [Attention Heads](https://attentionheads.substack.com/) if you want the thinking behind the thinking.

## The cast

| Role | Model | Agent or script | Budget | Route here when |
|---|---|---|---|---|
| Architect | your session: Opus 5.5 day to day, Fable 5.1 for hard days | — | Claude | Always. Emits specs and verdicts, not code |
| Routine typing, **default** | GPT-6 Luna | `luna-implementer` | ChatGPT | The spec fully determines the outcome |
| Hard cross-vendor one-offs | GPT-6 Sol | `sol-implementer` | ChatGPT | Judgment the spec cannot capture; or Luna failed twice |
| Hard Claude work | Opus 5.5 with edit tools | `opus-implementer` | Claude | Turnaround matters more than vendor diversity; or race Sol |
| Frontier one-off, occasional | GPT-6 Astra | `astra-implementer` | ChatGPT | Sol and Opus both failed; a deliberate one-off |
| Evidence | Sonnet 5 | `verifier` | Claude | Full-suite runs, log triage |
| Final review, every deliverable | Fable 5.1, read-only | `fable-advisor` | Claude | Commitment boundaries and end of every deliverable |
| Second opinion, occasional | GPT-6 Astra, read-only | `astra-advisor` → `consult.sh` | ChatGPT | Irreversible decisions, release reviews, tie-breaks |
| Cross-vendor review | GPT-6 Sol | `review.sh` (`codex review`) | ChatGPT | Security paths, migrations, API shapes |
| Free, slow, mechanical | LM Studio or Ollama model | `local-implementer` | nothing | Off by default; work nobody is waiting on |

## Install

```
claude plugin marketplace add mhrtly/astrafabulopus
claude plugin install astrafabulopus@astrafabulopus
```

Then, once:

```
/astrafabulopus:setup
```

It checks the Codex CLI, probes which OpenAI slugs your login accepts, and saves your lane choices to `~/.claude/astrafabulopus/lanes.json`. A project can override everything with its own `.claude/orchestra/lanes.json`.

**Requirements.** Claude Code with Fable 5.1 on your plan (the `fable-advisor` agent pins the `fable` alias; without it, change `model: fable` to `model: opus`). The [OpenAI Codex CLI](https://github.com/openai/codex), logged in (`npm i -g @openai/codex && codex login`). Codex 0.154 rejected `gpt-6-luna` and `gpt-6-sol` on a ChatGPT-account login with "not supported when using Codex with a ChatGPT account"; 0.157.1 accepts them, so run `codex update` before you blame your plan. Optional: [LM Studio](https://lmstudio.ai) or Ollama for the local lane. No `coreutils` needed; the scripts carry their own timeout.

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

The architect declares its route, writes a six-part spec (objective, files, interfaces, constraints, verification, optional reasoning effort), labels every delegation with the model that runs it (`GPT-6 Luna · high: add pagination`), reads the diff and re-runs verification when the report comes back, and ends with Fable's ship / fix-first / rethink.

## The scripts

Every OpenAI lane runs through one deterministic script, so the Sonnet wrappers stay thin and cannot drift.

| Script | Does |
|---|---|
| `scripts/lane.sh <routine\|complex\|frontier\|local> spec.md` | Prepends the opt-out preamble, pins model and effort from the lanes config (or the spec's `REASONING:` line), runs `codex exec --sandbox workspace-write` under a watchdog, and reports **CHANGED FILES from `git status` before and after**, never from the model. A clean exit with no changes is `refused`. Exit codes: 0 complete, 4 refused, 5 timeout, 3 unavailable, 1 failed |
| `scripts/consult.sh question.md` | Read-only `codex exec` for a second opinion (Astra by default). Returns a VERDICT block |
| `scripts/review.sh [--base main \| --commit SHA]` | `codex review` on the working tree with your project contracts as the rubric |
| `scripts/verify.sh -- <command>` | Runs your test command behind a per-project lock (whole-module languages cannot build twice at once) and prints a compact PASS/FAIL report with the failure lines |

Logs land in `~/.claude/astrafabulopus/logs`.

## Why not just fable-advisor?

Use fable-advisor if it fits; it is excellent. Astrafabulopus exists because one project needed four things it did not have: lanes that work on a ChatGPT-account Codex login, a Claude implementer lane for the work where Opus wins, Astra as an occasional second frontier opinion so a release diff is read by two model families, and a lane runner that measures changes instead of believing them. It also adds the whole-module build rule (Swift, Rust, Go) and a local lane that needs no router in front of your Claude traffic. Details and the day-one numbers: [docs/DESIGN.md](docs/DESIGN.md).

## Lite mode

No plugin install: copy `agents/` to your project's `.claude/agents/`, `skills/` to `.claude/skills/`, `scripts/` to `.claude/orchestra/scripts/` and `config/lanes.json` to `.claude/orchestra/lanes.json`. The agents look for scripts at `${CLAUDE_PLUGIN_ROOT:-.claude/orchestra}/scripts/`, so both layouts work.

## Origin

Built in a weekend to ship a handwriting game for eight-year-olds to the Mac App Store faster than one frontier model typing everything could. The first day's numbers: GPT Luna created a file through the lane in 14 seconds, the local Qwen lane took 195 seconds for the same task, an Astra consult took 8 seconds, and a 231-test Swift suite ran green through `verify.sh`.

## License

MIT. Portions adapted from fable-advisor, © 2026 Dan McAteer, MIT. See [LICENSE](LICENSE).
