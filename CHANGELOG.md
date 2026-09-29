# Changelog

## 0.3.0

Version 0.3.0 saves no tokens: it adds a cheap extra call while the architect and Council still decide; savings are only possible after calibration shows Jev's confident answers can be trusted.
Live API smoke test: pending (request_id: pending).

### Added
- Optional TypeSafe Jev quick decisions for lane, effort, and spec completeness, with confidence labels and advisory-only behavior.
- `af-decide`, layered Jev settings and secure key lookup, doctor status, and ledger labels for later calibration.
- Jev setup and calibration guidance in [docs/JEV.md](docs/JEV.md).

## 0.2.1 — 2026-09-28

### Fixed
- Base-scoped and uncommitted reviews now inspect staged, unstaged and untracked changes.
- `af-verify` preserves project verification report lines in `DETAIL`, so agent evidence retains release-gate results.

Found by a GPT-6 Sol review of the Scribal Warfare port.

## 0.2.0 — 2026-09-27 · "The Pantry and the Council"

*Spudnik's pass. Holy hash browns and gravy, there was a lot in the sack.*

### Fixed
- **`review.sh` never ran.** Codex refuses a custom prompt together with `--uncommitted`, `--base` or `--commit`, and 0.1 always passed both. `af-review` now puts the scope in the prompt (`codex exec … review -`), with `--native` for Codex's built-in review. It also propagates Codex's exit code (0.1 always exited 0) and runs under the watchdog.
- **Real work reported as `refused`.** A lane that edited a file that was already untracked or staged left `git status` and `git diff` unchanged. Change detection now hashes file contents before and after.
- **Project config ignored from subfolders.** Lanes now resolve the git top level, so `.claude/orchestra/lanes.json` applies anywhere in the repo, and Codex runs at the root.
- **Plugin path resolution.** The lanes are now `bin/af-*` commands, which Claude Code puts on the Bash tool's PATH. The agents no longer depend on `${CLAUDE_PLUGIN_ROOT}` expanding in their shell. The old `scripts/*.sh` paths remain as shims.
- A flag given without its value (`--effort` at the end) is a usage error instead of an unbound-variable crash.
- Temporary prompt and output files are cleaned up.
- `af-verify` works on systems with `sha1sum` but no `shasum`.
- A lane that commits its own work (specs say not to) is reported with the commit and its files, not as `refused`.

### Added
- **The Pantry** (`af-pantry`, `af-statusline`). Live Claude and ChatGPT usage from the vendors' own meters: Codex session files, and Claude Code's status-line `rate_limits`. It adds pace projection ("dry in 3h"), pressure levels, routing advice, and manual entries for API credits. Lanes refuse to start on an empty sack. Lane reports carry `BUDGET:` (this run's share of each window) and `PANTRY:` lines. An experimental, opt-in poll of Claude's usage endpoint is included. See [docs/PANTRY.md](docs/PANTRY.md).
- **The Potato Council** (`af-council`, `config/models.json`). Talent priors for 11 models, with prices and sources, and a ledger of every lane run (tokens, duration, status, window share). It adds grades and a slowly-learning observed nudge, plus budget- and diversity-aware `recommend`, and `add --like`, `rate`, `promote`, `retire`, `log` and `ledger`. See [docs/COUNCIL.md](docs/COUNCIL.md).
- **`af-tryout`.** A three-task audition for a new model in a scratch repo, graded into the ledger.
- **`af-doctor`.** One screen showing whether everything is plugged in.
- **Slash commands** `/astrafabulopus:pantry`, `/astrafabulopus:council` and `/astrafabulopus:new-model`. `/astrafabulopus:setup` now installs the status-line tap and offers permission rules.
- **Effort validation.** A rung Codex does not know is rejected before the run; a rung the Council has not seen a model accept gets a warning.
- **Layered config.** `lanes.json` and `models.json` merge per lane, per model and per talent: plugin, then user, then project.
- `af-verify --timeout`.
- **Tests.** `tests/run.sh` runs 54 cases against a fake Codex, plus Python unit tests. CI covers Ubuntu, macOS with `/bin/bash` 3.2, shellcheck, and Python 3.9 compatibility.
- The orchestration skill gains "Mind the pantry" and "Ask the Council", and a `budget:` line in the ROUTE block.
- Documentation rewritten by a potato.

### Changed
- Lane agents grade their own runs after re-verifying (`af-council grade`); `opus-implementer` logs its runs.
- `lanes.json` is version 2; the fields are unchanged and the layering is additive.

## 0.1.0 — 2026-09-27

- Two-subscription architect pattern for Claude Code. It has a Claude architect, GPT Luna, Sol and Astra lanes through the Codex CLI, an optional LM Studio lane, and a mandatory Fable 5.1 review. It's a homage to Dan McAteer's astrable and fable-advisor.
