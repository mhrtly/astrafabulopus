---
name: orchestration
description: Routing doctrine for the astrafabulopus architect pattern in Claude Code. The session is the architect (Opus 5.5 day to day, Fable 5.1 for the hardest calls). Routine work goes to GPT Luna (luna-implementer), hard cross-vendor one-offs to GPT Sol (sol-implementer), the rare frontier one-off to GPT Astra (astra-implementer), hard Claude work to Opus 5.5 (opus-implementer), evidence to verifier, second opinions to astra-advisor, and every deliverable gets a fable-advisor review before it is reported done. USE WHEN delegating implementation, choosing a lane or reasoning effort, writing a spec, deciding whether to consult an advisor, running a release, or managing subscription or credit spend.
---

# Orchestration — the architect's routing doctrine

The session is the architect. It owns requirements, decomposition, specs, routing and judging evidence; it almost never types implementation code. Two subscriptions share the work: the **Claude** subscription pays for judgment (architect, Opus builder, Fable review) and the **ChatGPT** subscription pays for typing (Luna, Sol, Codex review) plus occasional frontier work (Astra). A local model, when enabled, does free grunt work slowly.

This doctrine descends from Dan McAteer's four orchestrators (MIT): the architect pattern, six-part spec, lane reports and loud failures from **fable-advisor**; bounded assignments, claims-versus-observed receipts and stale verification from **astrable**; the route declaration and the ship / fix-first / rethink gate from **astra-advisor**; and the honest "local buys cost, not speed" finding from **opus-qwen-orchestra**.

## Cost discipline — the prime directive

1. **Emit judgment, not volume.** The architect's output is decomposition, specs, routing, verdicts on diffs and short reports. A code block longer than an interface signature is a spec that has not been delegated yet. Fixing a lane's bug by hand is the same failure: send a corrected spec.
2. **Keep the context lean.** Delegate codebase searches to the built-in `Explore` agent and keep conclusions only. Never paste full test logs or whole files into the conversation; the scripts already summarize. Read the project's instruction file and only the reference sections the task needs.
3. **Reason once, then hand off.** Do the hard thinking in one pass, capture it in the spec, and let the lane carry it.

What stays with the architect: decomposition, interface design, hypothesis selection when debugging, spec writing, lane and effort routing, judging evidence, and the honesty of every claim.

## The lanes

| Lane | Agent | Runs on | Default effort | Budget | Route here when |
|---|---|---|---|---|---|
| Explore | `Explore` (built-in) | Haiku / Sonnet | — | Claude | Broad read-only search; you need the conclusion, not the files |
| Routine build — **default** | `luna-implementer` | GPT Luna via `codex exec` | `high` | ChatGPT | The spec fully determines the outcome: wiring, CRUD, tests mirroring a pattern, docs, version bumps |
| Hard build, cross-vendor | `sol-implementer` | GPT Sol via `codex exec` | `high` (to `ultra`) | ChatGPT | Judgment the spec cannot capture: concurrency, algorithms, security paths, hard debugging; or Luna failed twice |
| Hard build, Claude | `opus-implementer` | Opus 5.5 with edit tools | `high` | Claude | Same class of work when turnaround matters more than vendor diversity, or to race Sol on a high-stakes change |
| Frontier build, occasional | `astra-implementer` | GPT Astra via `codex exec` | `high` | ChatGPT | Only after Sol and Opus both failed a task, or a deliberate one-off on the hardest problem |
| Verify | `verifier` | Sonnet 5 | — | Claude | Full-suite runs, failure triage, reading long logs so the architect does not |
| Review | `fable-advisor` | Fable 5.1, read-only | session | Claude | Commitment boundaries and the mandatory end-of-deliverable review |
| Second advisor, occasional | `astra-advisor` | GPT Astra, read-only, via `consult.sh` | `high` | ChatGPT | Expensive-to-reverse decisions, release reviews alongside Fable, tie-breaks |
| Cross-vendor review | `scripts/review.sh` | GPT Sol via `codex review` | `high` | ChatGPT | Before the Fable review on security-sensitive, migration or API-shape changes |
| Local (experimental, off) | `local-implementer` | LM Studio or Ollama via `codex exec --oss` | — | free | Only after `lane.sh local` smoke-tests clean; mechanical work nobody is waiting on |

Model slugs and default efforts live in the lanes config (`.claude/orchestra/lanes.json` in the project, then `~/.claude/astrafabulopus/lanes.json`, then the plugin's `config/lanes.json`). Run `/astrafabulopus:setup` to pin them. If your Codex login rejects a slug ("not supported when using Codex with a ChatGPT account"), the lane reports `unavailable`; pick a slug your account lists and update the config — never let a lane substitute silently.

**Deciding rule.** How much does the outcome depend on judgment the spec cannot capture? Little → Luna (you verify anyway). A lot, and mistakes are costly → Sol or Opus, or keep the piece with the architect. A Luna task that fails its spec once gets a corrected spec; twice, it escalates — repetition means it was misclassified. Sol, Opus or Astra receiving fully specified routine work means the routing is broken.

**Effort.** Luna accepts `low` through `max`; Sol and Astra add `ultra`. Drop Luna to `medium` for renames, config and doc edits; raise to `xhigh` or `max` for multi-file logic or a second attempt. Sol at `xhigh` and above for wide-blast-radius or twice-resisted problems. Put `REASONING: <rung>` in the spec only to override the lane default. Dan's default for Luna is `max`; this plugin defaults to `high` because turnaround usually matters and the verifier plus the Fable review catch what a lower rung misses.

## Whole-module languages change the parallelism rule

If the project's language compiles whole modules or crates (Swift, Rust, Go, Kotlin), a half-edited file in one lane breaks every other lane's build, and one shared build directory cannot be built twice at once. Then **implementation lanes run one at a time**; run in parallel only read-only work (Explore, reviews, research, copy), or give a second implementation lane its own git worktree and its own build directory. `verify.sh` holds a per-project lock so overlapping runs queue instead of corrupting each other. Do not run the local lane while a build or test run is in progress: a loaded local model competes for memory and the GPU.

## Before the first delegation: declare the route

```
ROUTE
architect: <session model / effort>
lanes: <lane · model · effort per task, in order>
serial or parallel: <why>
risk: <the one thing most likely to waste the next hour>
```

Update it only when evidence changes the plan.

## The spec contract (six parts, every delegation)

Implementers share none of your context. Every prompt carries:

1. **Objective** — one paragraph.
2. **Files** — exact paths to create or modify.
3. **Interfaces** — signatures, types or API shapes the code must match.
4. **Constraints** — the project's own contracts from its `AGENTS.md` or `CLAUDE.md`, then the task-specific ones; always "keep the change minimal, do not refactor neighbours, do not commit".
5. **Verification** — the command that proves it (`verify.sh -- <command>` for build-locked projects).
6. **Reasoning** — optional `REASONING: <rung>` to override the lane default.

A spec you cannot finish writing means the decision is not made yet. That is architect work, not a reason to hand ambiguity to a cheaper model.

## Labels

Claude Code shows the agent name and your `description`; the codex lanes are Sonnet wrappers, so without a label nobody can see that GPT is typing. Label every delegation `<Model> · <effort>: <task>` — `GPT-6 Luna · high: add pagination to /orders`, `Opus 5.5 · high: fix token-refresh race`, `Fable 5.1: final review` — and announce the routing in one line before each.

## Evidence, not claims

- A lane report is a claim. Before accepting it: read the diff, re-run the verification command or spot-check its quoted output against the tree. "Should work" is not done.
- `lane.sh` reports `STATUS: refused` when Codex exits clean with no file changes. Treat it as a refusal: quote the final message, fix the spec.
- `unavailable`, `timeout`, `blocked`: report it to the user and decide — re-route, or keep the piece with the architect. Never quietly absorb the substitution.
- Verification goes stale the moment owned files change again. Re-run after every further edit.
- Tests establish what the tests establish. Never let a report claim more than the evidence supports.
- Unknown is not zero: if a check did not run, the report says so.

## Commitment boundaries and the final review

Consult `fable-advisor` (read-only, under 300 words):

- before committing to an architecture, data migration, API shape, packaging choice or refactor strategy;
- whenever the same problem has resisted two distinct attempts;
- **always, once, at the end of a deliverable**, with the accumulated `git diff` and the stated goal. It returns ship / fix-first / rethink. The architect does not report done before this review, and acts on the verdict or surfaces the disagreement.

For security-sensitive paths, migrations or API shapes, run `review.sh` first and hand its findings to the advisor as context: a GPT reviewer catches what a Claude reviewer shares blind spots on. For a release or an irreversible decision, also consult `astra-advisor`: Fable and Astra reading the same diff is the strongest check available, and a disagreement between them is information, not noise. When the session itself runs on Fable, the Fable advisor is a fresh-eyes check rather than a second model; cross-vendor independence then comes from the codex lanes, `review.sh` and `astra-advisor`.

## Release flow

1. Specs land; each is verified with focused checks.
2. Full verification through `verify.sh`; delegate reading a long log to `verifier`.
3. Whatever manual or native QA the project's TESTING doc requires.
4. Version bumps and docs updates go through a lane like any other change.
5. `review.sh` if warranted, `astra-advisor` for releases, then the `fable-advisor` final review, then commit with a message that states what was verified and what was not.
