#!/bin/bash
# Read-only cross-vendor consult through the Codex CLI (the `consult` lane; GPT Astra by default).
#
#   consult.sh <question-file> [--model SLUG] [--effort RUNG] [--root DIR] [--config PATH]
#
# The question states the decision or goal, the constraints and the options considered, or asks for a
# review of the working tree (the model may run read-only commands such as git diff). Codex runs with
# --sandbox read-only, so nothing can be edited. Exit 3 = unavailable, 5 = timeout, 1 = failed.
set -uo pipefail
. "$(cd "$(dirname "$0")" && pwd)/_common.sh"
ROOT="$PWD"; Q="${1:-}"; CONFIG=""
[ -n "$Q" ] && [ -f "$Q" ] || { sed -n '2,8p' "$0"; exit 2; }; shift
MODEL_OVERRIDE=""; EFFORT_OVERRIDE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL_OVERRIDE="$2"; shift 2 ;;
    --effort) EFFORT_OVERRIDE="$2"; shift 2 ;;
    --root) ROOT="$(cd "$2" && pwd)"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    *) echo "consult: unknown option $1" >&2; exit 2 ;;
  esac
done
CONFIG="$(af_resolve_config "$CONFIG" "$ROOT")"
CFG="$(af_lane_cfg "$CONFIG" consult)"
if [ "${CFG%% *}" != "OK" ]; then echo "CONSULT: unavailable — $CFG"; exit 3; fi
set -- $CFG; MODEL="${MODEL_OVERRIDE:-$3}"; EFFORT="${EFFORT_OVERRIDE:-$4}"; TIMEOUT="$5"
if ! MSG="$(af_preflight codex -)"; then echo "CONSULT: unavailable — $MSG"; exit 3; fi
LOGDIR="$(af_home)/logs"; mkdir -p "$LOGDIR"; LOG="$LOGDIR/$(date +%Y%m%d-%H%M%S)-consult.log"
PROMPT="$(mktemp -t consult.XXXXXX)"; FINAL="$(mktemp -t consult-final.XXXXXX)"
{
cat <<'PREAMBLE'
Scope of this run: one read-only consultation requested by an orchestrating session. Answer it
directly in this run; do not start an orchestration or delegation workflow and do not edit files.
You may run read-only commands (git diff, git log, cat, rg) to look before you opine.

Answer as a second-opinion advisor: give a verdict, not a survey; name the single risk that decides
it; a sound plan gets one line; stay under 300 words. End with exactly:
VERDICT: ship | fix-first | rethink   (or: do X | do Y, for a decision)
REASON: <evidence-based>
FINDINGS: <file:line — precise point, or none>
RESIDUAL RISK: <one line or none>

PREAMBLE
cat "$Q"
} > "$PROMPT"
START=$(date +%s)
echo "# $(date) consult model=$MODEL effort=$EFFORT root=$ROOT question=$Q config=$CONFIG" > "$LOG"
af_run_with_watchdog "$TIMEOUT" "$LOG" "$PROMPT" consult codex exec -m "$MODEL" -c "model_reasoning_effort=$EFFORT" --sandbox read-only --skip-git-repo-check --cd "$ROOT" --output-last-message "$FINAL" -
RC=$?
echo "CONSULT: $MODEL · effort $EFFORT · $(( $(date +%s) - START ))s · exit $RC · session $(grep -m1 -E '^session id:' "$LOG" | sed 's/session id: //')"
if grep -q '^# consult: timeout' "$LOG"; then echo "STATUS: timeout"; echo "LOG: $LOG"; exit 5; fi
if [ "$RC" -ne 0 ] || [ ! -s "$FINAL" ]; then echo "STATUS: failed"; grep -E 'ERROR' "$LOG" | tail -4; echo "LOG: $LOG"; exit 1; fi
echo "ANSWER:"; sed 's/^/  /' "$FINAL"; echo; echo "LOG: $LOG"
