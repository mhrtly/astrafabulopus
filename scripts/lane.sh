#!/bin/bash
# astrafabulopus implementation lane: runs ONE delegated spec through the Codex CLI.
#
#   lane.sh <routine|complex|frontier|local> <spec-file> [--effort RUNG] [--model SLUG] [--root DIR] [--config PATH]
#
# Lane models and default efforts come from the lanes config (project .claude/orchestra/lanes.json,
# then ~/.claude/astrafabulopus/lanes.json, then the plugin's config/lanes.json). A `REASONING: <rung>`
# line in the spec, or --effort, overrides the default. CHANGED FILES come from git status before and
# after the run, never from the model's own claims.
# Exit codes: 0 complete (pending your verification), 4 refused (clean exit, no file changes),
# 5 timeout, 3 unavailable (no codex/login/server or lane disabled), 1 failed, 2 usage.
#
# Adapted from Dan McAteer's fable-advisor lanes (MIT, github.com/DannyMac180/fable-advisor).
set -uo pipefail
. "$(cd "$(dirname "$0")" && pwd)/_common.sh"
ROOT="$PWD"; LANE="${1:-}"; SPEC="${2:-}"; CONFIG=""
if [ -z "$LANE" ] || [ -z "$SPEC" ]; then sed -n '2,12p' "$0"; exit 2; fi
shift 2
EFFORT_OVERRIDE=""; MODEL_OVERRIDE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --effort) EFFORT_OVERRIDE="$2"; shift 2 ;;
    --model)  MODEL_OVERRIDE="$2";  shift 2 ;;
    --root)   ROOT="$(cd "$2" && pwd)"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    *) echo "lane: unknown option $1" >&2; exit 2 ;;
  esac
done
[ -f "$SPEC" ] || { echo "lane: spec file not found: $SPEC" >&2; exit 2; }
CONFIG="$(af_resolve_config "$CONFIG" "$ROOT")"
LOGDIR="$(af_home)/logs"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/$(date +%Y%m%d-%H%M%S)-$LANE.log"
MODEL="?"; EFFORT="?"; EFFORT_SOURCE="?"
report() { printf 'LANE REPORT\nLANE: %s · %s · effort %s (%s)\nSTATUS: %s\nREASON: %s\nCONFIG: %s\nLOG: %s\n' "$LANE" "$MODEL" "$EFFORT" "$EFFORT_SOURCE" "$1" "$2" "$CONFIG" "$LOG"; }

CFG="$(af_lane_cfg "$CONFIG" "$LANE")"
if [ "${CFG%% *}" != "OK" ]; then report unavailable "$CFG"; exit 3; fi
set -- $CFG
PROVIDER="$2"; MODEL="${MODEL_OVERRIDE:-$3}"; EFFORT="$4"; TIMEOUT="$5"; ENABLED="$6"; BASE_URL="$7"
EFFORT_SOURCE="default"
SPEC_EFFORT="$(grep -m1 -E '^REASONING:' "$SPEC" | sed -E 's/^REASONING:[[:space:]]*//; s/[[:space:]].*$//')"
if [ -n "$EFFORT_OVERRIDE" ]; then EFFORT="$EFFORT_OVERRIDE"; EFFORT_SOURCE="flag"
elif [ -n "$SPEC_EFFORT" ]; then EFFORT="$SPEC_EFFORT"; EFFORT_SOURCE="spec"; fi
[ "$ENABLED" = "true" ] || { report unavailable "lane '$LANE' is disabled in $CONFIG"; exit 3; }
if ! MSG="$(af_preflight "$PROVIDER" "$BASE_URL")"; then report unavailable "$MSG"; exit 3; fi

PROMPT="$(mktemp -t codex-spec.XXXXXX)"; FINAL="$(mktemp -t codex-final.XXXXXX)"
{
cat <<'PREAMBLE'
Scope of this run: one implementation task, already planned and delegated by
an orchestrating session. Implement it directly in this run. I explicitly opt
out of starting an orchestration or delegation workflow for it. The model and
reasoning effort for this run are the ones set on the command line.

PREAMBLE
cat "$SPEC"
printf '\n\nRun the verification command and include its actual output in your final message.\n'
} > "$PROMPT"

in_git() { git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; }
snapshot() { if in_git; then git -C "$ROOT" status --porcelain=v1 --untracked-files=all 2>/dev/null | sort; else find "$ROOT" -type f -not -path '*/.git/*' -newer "$PROMPT" 2>/dev/null | sort; fi; }
diffhash() { if in_git; then git -C "$ROOT" diff 2>/dev/null | shasum | cut -c1-12; else echo none; fi; }
BEFORE="$(snapshot)"; HASH_BEFORE="$(diffhash)"

if [ "$PROVIDER" = "codex" ]; then
  CMD=(codex exec -m "$MODEL" -c "model_reasoning_effort=$EFFORT" --sandbox workspace-write --skip-git-repo-check --cd "$ROOT" --output-last-message "$FINAL" -)
else
  CMD=(codex exec --oss --local-provider "$PROVIDER" -m "$MODEL" -c "model_reasoning_effort=$EFFORT" --sandbox workspace-write --skip-git-repo-check --cd "$ROOT" --output-last-message "$FINAL" -)
fi
START=$(date +%s)
{ echo "# $(date) lane=$LANE provider=$PROVIDER model=$MODEL effort=$EFFORT ($EFFORT_SOURCE) root=$ROOT spec=$SPEC config=$CONFIG"; echo "# ${CMD[*]}"; } > "$LOG"
af_run_with_watchdog "$TIMEOUT" "$LOG" "$PROMPT" lane "${CMD[@]}"; RC=$?
DURATION=$(( $(date +%s) - START ))

AFTER="$(snapshot)"; HASH_AFTER="$(diffhash)"
CHANGED="$(comm -13 <(printf '%s\n' "$BEFORE") <(printf '%s\n' "$AFTER") | sed '/^$/d')"
if [ -z "$CHANGED" ] && [ "$HASH_BEFORE" != "$HASH_AFTER" ]; then CHANGED="(files that were already modified changed further; see git diff)"; fi
STATUS="complete"; EXIT=0
if grep -q '^# lane: timeout' "$LOG"; then STATUS="timeout"; EXIT=5
elif [ "$RC" -ne 0 ]; then STATUS="failed"; EXIT=1
elif [ -z "$CHANGED" ]; then STATUS="refused"; EXIT=4; fi

printf 'LANE REPORT\nLANE: %s · %s · effort %s (%s)\nSTATUS: %s\nEXIT: %s  DURATION: %ss\nSESSION: %s\n' \
  "$LANE" "$MODEL" "$EFFORT" "$EFFORT_SOURCE" "$STATUS" "$RC" "$DURATION" "$(grep -m1 -E '^session id:' "$LOG" | sed 's/session id: //')"
echo "CHANGED FILES (git status before/after, not the model's claim):"
if [ -n "$CHANGED" ]; then printf '%s\n' "$CHANGED" | sed 's/^/  /'; else echo "  (none)"; fi
if in_git; then echo "DIFFSTAT:"; git -C "$ROOT" diff --stat 2>/dev/null | tail -8 | sed 's/^/  /'; fi
echo "CONFIG: $CONFIG"; echo "LOG: $LOG"
echo "FINAL MESSAGE:"
if [ -s "$FINAL" ]; then sed 's/^/  /' "$FINAL"; echo; else echo "  (empty)"; grep -E 'ERROR' "$LOG" | tail -5 | sed 's/^/  /'; fi
[ "$STATUS" = "refused" ] && echo "NOTE: a clean exit with no file changes is a refusal, never a success. Quote the final message and re-spec."
exit $EXIT
