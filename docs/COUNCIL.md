# 🥔 The Potato Council

*Who is good at what, what it costs, and what actually happened. The Council meets underground. Literally.*

Models ship every few weeks now. Each launch post claims to be the best at something, and each changes which lane should get which work. The Council keeps two kinds of knowledge side by side, so that adjusting to a new model is a five-minute conversation instead of a weekend of vibes.

## Priors: `config/models.json`

Every model gets six talents from 0 to 10:

| Talent | Means |
|---|---|
| `architecture` | Judgment the spec cannot capture: decomposition, interfaces, trade-offs, knowing what not to build |
| `implementation` | Turning a complete six-part spec into correct, minimal code on the first try |
| `debugging` | Hard bugs: concurrency, algorithms, flaky tests, the ones that resisted a first attempt |
| `review` | Finding the real problem in a diff and giving a calibrated verdict |
| `speed` | Turnaround for a typical lane run |
| `efficiency` | Useful work per unit of budget: price times verbosity. 10 barely dents a window |

Each model also records:
- how it runs (`codex`, `claude` or `local`) and its slug;
- its release and retirement dates and its reasoning-effort rungs;
- its API list price per million tokens. A subscription absorbs the price, but the price still predicts how fast a window drains;
- a one-line `spud` classification (Potato or Not-ato);
- an `evidence` list naming where the numbers came from.

**The scores are relative priors for routing, not a leaderboard.** They were seeded on 2026-09-27 from vendor model pages, pricing pages and the coding benchmarks the vendors published: Terminal-Bench 4.0, DeepSWE, SWE-Bench Pro. They were then judged conservatively. Benchmarks with different versions were never compared directly.

A few things the priors encode, with sources in the file:
- **Opus 5.5** (2026-09-22, $4/$20). Anthropic says it matches Fable 5.1 on most work, 40% cheaper and 30% faster than Opus 5, and it leads Anthropic's published Terminal-Bench 4.0 table at 66.4%. It's the default architect and the Claude build lane. (It was not allowed to vote on its own scores. It tried.)
- **Fable 5.1** ($10/$50). Slower and pricier, and behind Opus 5.5 on those coding benchmarks. It keeps the final review for its clean-context judgment.
- **GPT-6 Luna** ($0.10/$0.50). Within a couple of points of GPT-6 Sol on DeepSWE at about a twentieth of Sol's price and a hundredth of Astra's output price. The Tater Tot is the default for a reason.
- **GPT-6 Astra** ($10/$50). The strongest OpenAI model, and terse, but five times Sol's price. It's the frontier rung and the second advisor, never the default.
- **Haiku 4.5** has an announced retirement "not sooner than" 2026-10-15. The Council warns as the date approaches and after it passes, but only `af-council retire` removes a model.

## Observations: the ledger

Every `af-lane`, `af-consult` and `af-review` run appends one line to `~/.claude/astrafabulopus/ledger.jsonl`:
- lane, model, effort and where the effort came from;
- status and duration;
- files changed;
- tokens, from the Codex session file;
- the share of each ChatGPT window that run consumed.

The lane agents grade their own runs after they re-verify:

```
af-council grade 20260927-193702-routine-6c1f pass
af-council grade last fail --note "missed the empty-list case"
```

`opus-implementer` doesn't go through Codex, so it logs its runs by hand:

```
af-council log --model opus --status complete --verified pass --duration 180
```

`af-council ledger` shows the recent runs. `af-council show <model>` puts observed numbers next to the priors: runs, pass rate, median duration, median output tokens and median share of the 5-hour window per run.

## How a recommendation is scored

For a task class (`af-council tasks` lists them):

```
score = weighted talent (task weights)
      - budget pressure   (plenty 0, unknown 0.25, watch 0.6, tight 1.6; empty = excluded)
      - budget reserve    (0.4 on Claude work: the architect lives on that subscription)
      + diversity bonus   (0.5 for a different vendor than the architect, on complex / frontier / review / consult)
      - retirement        (0.3 within 45 days of an announced retirement, 0.6 after it)
      + observed nudge    (graded pass rate vs the rate the implementation prior predicts, weighted n / (n + 8))
```

The observed nudge is deliberately slow. Three lucky runs move a score by a couple of tenths at most. Twenty straight failures move it by more than two points. When the top two picks are within 0.25, the output says it's a close call and defers to the doctrine's lane table, because the priors are not that precise.

The architect is taken from `--architect`, or else from the model the status-line tap last saw. With an Opus 5.5 architect, the defaults reproduce the doctrine:

| Task | Pick | Why |
|---|---|---|
| routine | GPT-6 Luna | implementation, speed and efficiency; the Tot |
| complex | GPT-6 Sol (Astra close behind) | cross-vendor credit, and a fifth of Astra's price |
| review | GPT-6 Astra by 0.10 over Fable 5.1, flagged as a close call | cross-vendor credit vs Fable's review 10; the tie goes to the doctrine, so `fable-advisor` stays the final review and Astra becomes the release second opinion. Without an architect, Fable wins outright |
| architect | Opus 5.5 | architecture and all-day efficiency |

When budgets tighten, the picks move. On an empty ChatGPT sack, routine work goes to Sonnet 5. On a tight Claude sack, the codex lanes win more often.

## When a new model ships

The workflow the Council was built for. Run `/astrafabulopus:new-model <name>` for the guided version, or by hand:

1. **Find the facts.** Slug, release date, price, efforts and published benchmarks, each with a source.
2. **Seat it next to its nearest sibling.** You already understand the sibling, so you only need the differences:
   ```
   af-council add gpt-7-luna --like gpt-6-luna --name "GPT-7 Luna" --released 2026-11-02 \
     --price 0.1/0.01/0.5 --bump implementation=+1 --bump debugging=+0.5 \
     --spud "Tater Tot, second generation. Crispier."
   ```
   `--like` copies the sibling's talents, run type, efforts and budget. `--set dim=N` pins a talent and `--bump dim=±N` shifts it. For a Claude model, pass `--run claude --slug <alias>`.
3. **Audition it.** `af-tryout gpt-7-luna` runs three small tasks through a real lane in a scratch repo: follow a spec, fix a bug, make a judgment call. It verifies each with its own tests and grades the ledger. It costs three small runs on that model's subscription and never touches your project.
4. **Compare.** Run `af-council show gpt-7-luna` and `af-council recommend routine`.
5. **Promote, if it earned it.** `af-council promote gpt-7-luna --lane routine --effort high` writes one line to `~/.claude/astrafabulopus/lanes.json` (or `--scope project`). `af-council retire gpt-6-luna` thanks the old model for its service and returns it to the soil.

Re-rating an existing model works the same way:

```
af-council rate gpt-6-sol debugging=+0.5 --why "fixed two races Luna could not"
```

## Overrides

`models.json` layers merge per model and per talent, lowest first:
1. the plugin's `config/models.json`;
2. `~/.claude/astrafabulopus/models.json`, where `add`, `rate`, `retire` and `promote` write by default;
3. the project's `.claude/orchestra/models.json` (`--scope project`).

A project that finds Luna brilliant at its Swift code can say so without disagreeing with the whole world:

```json
{ "models": { "gpt-6-luna": { "talent": { "implementation": 8.5 } } } }
```

Task weights, the budget reserve and the diversity bonus live in the same file (`tasks`, `scoring`) and layer the same way. If you disagree with the Council, overrule it. The Council will take note. The Council always takes note.
