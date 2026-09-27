# Design notes

*In which a potato explains its architecture, with receipts.*

## Lineage

| Borrowed from | What |
|---|---|
| [fable-advisor](https://github.com/DannyMac180/fable-advisor) | The architect pattern, the six-part spec, the Codex lane wrappers on Sonnet, the verbatim opt-out preamble, structured lane reports, "no silent fallback", the Fable 5.1 end-of-deliverable review, per-lane default efforts, delegation labels, `lanes.json` with setup-time probing |
| [astrable](https://github.com/DannyMac180/astrable) | Bounded assignments; receipts that separate a model's claims from independently observed file changes; verification that goes stale when files change; reading the remaining weekly allowance from the harness itself instead of guessing it, which is the grandparent of the Pantry |
| [astra-advisor](https://github.com/DannyMac180/astra-advisor) | The route declaration before the first delegation, the ship / fix-first / rethink gate, "requested is not observed", "unknown is not zero", API-equivalent cost receipts |
| [opus-qwen-orchestra](https://github.com/DannyMac180/opus-qwen-orchestra) | A free local implementer lane, and the honest finding that it buys cost, not speed |
| [sol-advisor](https://github.com/DannyMac180/sol-advisor) | Reading Codex's own session files as evidence of what actually ran |

## What 0.1 added

- **Deterministic lane runner.** `af-lane` (née `lane.sh`) does what each of Dan's Sonnet wrappers re-derived in Bash every run:
  - unique prompt files and the preamble;
  - the effort pin;
  - a watchdog timeout with no `coreutils` dependency;
  - changed files measured from the working tree before and after the run.

  A clean exit with no changes is `refused`, never `complete`. The wrappers become thin and cannot drift.
- **Config, not constants.** Models and efforts live in `lanes.json`, with project, user and plugin layers. That was Dan's own TODO ("per-project overrides").
- **A Claude implementer lane.** `opus-implementer` runs Opus 5.5 with edit tools, for the work where Claude's judgment or turnaround wins.
- **Astra as an occasional lane and a second advisor.** `astra-implementer` is the last rung. `astra-advisor` gives a read-only GPT Astra verdict, so a release diff can be read by two frontier families.
- **A local lane without a router.** Codex's built-in LM Studio and Ollama providers drive the local model, so nothing sits in front of Claude traffic.
- **Whole-module rule.** Swift, Rust and Go builds cannot overlap in one output directory, and a half-edited file breaks every lane's build. The doctrine serializes implementation lanes, and `af-verify` takes a per-project lock.

## What 0.2 adds (Spudnik's pass)

- **Commands on the PATH.** Claude Code puts a plugin's `bin/` on the Bash tool's PATH, so the lanes are bare commands (`af-lane routine spec.md`). 0.1 relied on `${CLAUDE_PLUGIN_ROOT:-.claude/orchestra}` being set in a subagent's shell. Claude Code documents that variable for hooks, MCP servers and plugin content rather than the Bash tool's environment, and when it is missing the fallback points at a directory a plugin install never creates. A bare command needs no variable at all. Every script resolves its own `lib/` and `config/` through symlinks. The 0.1 `scripts/*.sh` paths remain as shims.
- **A review lane that runs.** Codex refuses a custom prompt together with `--uncommitted`, `--base` or `--commit` (`error: the argument '--uncommitted' cannot be used with '[PROMPT]'`). 0.1 always passed both. `af-review` now describes the scope inside the prompt and passes it on stdin (`codex exec … review -`), so it ends in the same VERDICT block as every other reviewer. `--native` uses Codex's built-in scope review instead. Its exit code now reflects Codex's, and it runs under the same watchdog as the other lanes.
- **Honest change detection.** 0.1 compared `git status` lines plus a hash of `git diff`. That missed a lane editing a file that was already untracked (and one already staged): the status line doesn't change and `git diff` doesn't cover it, so real work was reported as `refused`. 0.2 hashes the content of every dirty or untracked file before and after the run. Outside git it compares sizes and modification times, skipping build and dependency directories.
- **The repo root.** Lanes now run at the git top level even when invoked from a subdirectory. Before, a project's `.claude/orchestra/lanes.json` was silently ignored when you were in a subfolder.
- **Layered config.** `lanes.json` and `models.json` merge per lane, per model and per talent, so an override states only what it changes.
- **Effort checks.** A rung Codex does not know (`--effort turbo`) is rejected before the run. A rung the Council has not seen a model accept gets a `WARN:` line and runs anyway, because Codex has the final word.
- **The Pantry** (`af-pantry`, `af-statusline`). See [PANTRY.md](PANTRY.md).
- **The Potato Council** (`af-council`, `af-tryout`, the ledger). See [COUNCIL.md](COUNCIL.md).
- **`af-doctor`.** Everything setup and debugging start with, on one screen.
- **Small mercies.**
  - a flag without a value is a usage error, not a crash under `set -u`;
  - temporary files are cleaned up;
  - `af-verify --timeout`;
  - `shasum` or `sha1sum`, whichever the OS has.
- **A test suite.** `tests/run.sh` runs 50 cases against a fake Codex that mimics 0.157.1: the exec header, `--output-last-message`, rollout files with `token_count` and `rate_limits`, `login status`, and clap's review-argument conflict, so the review bug cannot come back quietly. CI runs it on Ubuntu (bash 5, GNU tools) and macOS (`/bin/bash` 3.2, BSD tools), with shellcheck, and checks that the Python runs on 3.9.

## Day-one evidence (September 26–27, 2026, Apple Silicon laptop)

| Check | Result |
|---|---|
| GPT-5.6 Luna lane, create one file in a scratch repo | complete in 14 s |
| Local LM Studio lane (Qwen 3.6 27B MLX), same task | complete in 195 s |
| GPT-6 Astra read-only consult, trivial question | 8 s |
| Codex `workspace-write` sandbox running Apple Vision test suites | 19 of 19 passed |
| Full Swift suite through the verify lane on a quiet machine | 231 tests, 0 failures |
| GPT-6 Luna / Sol on Codex CLI 0.154 with a ChatGPT login | rejected; accepted after `codex update` to 0.157.1 |

One release run failed a single Vision test while LM Studio was loading a 29 GB model; the test passed alone. That's where the "no local model during builds" rule comes from.

## 0.2 evidence (September 27, 2026)

| Check | Result |
|---|---|
| `tests/run.sh` on Linux, bash 5 | 50 shell cases + 21 Python unit tests, all passing |
| Every Codex invocation the lanes make, parsed by the real Codex CLI 0.157.1 (no login) | `exec … -`, `exec --oss --local-provider …` and `exec … review -` all parse; the 0.1 review form fails with the conflict error above |
| Codex rollout format | Read from the real 0.157.1 CLI: the file is named after the `session id:` printed in the exec header; `token_count` events carry `rate_limits` |
| shellcheck 0.11 on all bash | clean |
| `vermin` minimum Python | 3.7 (target: the 3.9 macOS ships) |

Not verified here: a live Codex run against a real ChatGPT login (this was built in a sandbox without one), a real Claude status-line payload on a Max plan, and the experimental OAuth usage endpoint. The formats come from the Codex source and the Claude Code docs and changelog. The first real lane run on your machine is the proof, and `af-doctor` will tell you if anything is missing.

## Known limits

- **Requested settings are not observed settings.** The lane report shows what was passed to Codex; Codex's own session log is the record of what ran.
- **Subagent frontmatter pins a Claude model alias.** If the account lacks it, Claude Code falls back to the session model silently. Check `/plugin` and your plan if advisor verdicts feel unremarkable.
- **Claude-side runs aren't attributed.** The Pantry sees Claude's windows through the status line, but the Claude lanes (`opus-implementer`, `fable-advisor`) can't attribute their own share of it the way the Codex lanes do.
- **`BUDGET:` deltas are an upper bound.** Anything else using the same ChatGPT account during a run is counted too.
- **Talent priors are judgment, not measurement.** Grades and tryouts correct them over time; overlays let you disagree.
- **The least exercised paths:** the local lane and `af-review --native`.
