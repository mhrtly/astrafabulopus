# Design notes

## Lineage

| Borrowed from | What |
|---|---|
| [fable-advisor](https://github.com/DannyMac180/fable-advisor) | The architect pattern, the six-part spec, the Codex lane wrappers on Sonnet, the verbatim opt-out preamble, structured lane reports, "no silent fallback", the Fable 5.1 end-of-deliverable review, per-lane default efforts, delegation labels |
| [astrable](https://github.com/DannyMac180/astrable) | Bounded assignments, receipts that separate a model's claims from independently observed file changes, verification that goes stale when files change |
| [astra-advisor](https://github.com/DannyMac180/astra-advisor) | The route declaration before the first delegation, the ship / fix-first / rethink gate, "requested is not observed", "unknown is not zero" |
| [opus-qwen-orchestra](https://github.com/DannyMac180/opus-qwen-orchestra) | A free local implementer lane, and the honest finding that it buys cost, not speed |

## What this adds

- **Deterministic lane runner.** `scripts/lane.sh` does what each of Dan's Sonnet wrappers re-derived in Bash every run: unique prompt files, the preamble, the effort pin, a watchdog timeout with no `coreutils` dependency, and CHANGED FILES computed from `git status` before and after. A clean exit with no changes is `refused`, never `complete`. Wrappers become thin and cannot drift.
- **Config, not constants.** Models and efforts live in `lanes.json` with project → user → plugin resolution, which is Dan's own TODO ("per-project overrides"). The `_candidates` list lets `/astrafabulopus:setup` probe which slugs a login accepts.
- **A Claude implementer lane.** `opus-implementer` runs Opus 5.5 with edit tools for the work where Claude's judgment or turnaround wins; Dan's TODO listed it.
- **Astra as an occasional lane and a second advisor.** `astra-implementer` is the last rung; `astra-advisor` gives a read-only GPT Astra verdict through `consult.sh`, so a release diff can be read by two frontier families.
- **A local lane without a router.** Codex's built-in LM Studio and Ollama providers drive the local model, so nothing sits in front of Claude traffic; the single-point-of-failure router is gone.
- **Whole-module rule.** Swift, Rust and Go builds cannot overlap in one output directory, and a half-edited file breaks every lane's build; the doctrine serializes implementation lanes and `verify.sh` takes a per-project lock.

## Day-one evidence (September 26–27, 2026, Apple Silicon laptop)

| Check | Result |
|---|---|
| GPT-5.6 Luna lane, create one file in a scratch repo | complete in 14 s |
| Local LM Studio lane (Qwen 3.6 27B MLX), same task | complete in 195 s |
| GPT-6 Astra read-only consult, trivial question | 8 s |
| Codex `workspace-write` sandbox running Apple Vision test suites | 19 of 19 passed |
| Full Swift suite through `verify.sh` on a quiet machine | 231 tests, 0 failures |
| GPT-6 Luna / Sol on Codex CLI 0.154 with a ChatGPT login | rejected; accepted after `codex update` to 0.157.1 |

One release run failed a single Vision test while LM Studio was loading a 29 GB model; the test passed alone. That is where the "no local model during builds" rule comes from.

## Known limits

- Requested settings are not observed settings. The lane report shows what was passed to Codex; Codex's own session log is the record of what ran.
- Subagent frontmatter pins a Claude model alias; if the account lacks it, Claude Code falls back to the session model silently. Check `/plugin` and your plan if advisor verdicts feel unremarkable.
- `review.sh` and the local lane are the least exercised paths.
