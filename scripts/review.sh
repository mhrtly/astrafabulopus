#!/bin/bash
# Cross-vendor code review of the current repository through the Codex CLI (the `review` lane).
#
#   review.sh [--base BRANCH | --commit SHA] [--model SLUG] [--effort RUNG] [--config PATH] [extra instructions…]
#
# Default scope is the uncommitted working tree. Read-only: it never edits or commits. Feed its
# VERDICT/FINDINGS to fable-advisor as context for the final review.
set -uo pipefail
. "$(cd "$(dirname "$0")" && pwd)/_common.sh"
ROOT="$PWD"; CONFIG=""; MODEL_OVERRIDE=""; EFFORT_OVERRIDE=""; SCOPE=(--uncommitted); EXTRA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base)   SCOPE=(--base "$2"); shift 2 ;;
    --commit) SCOPE=(--commit "$2"); shift 2 ;;
    --model)  MODEL_OVERRIDE="$2"; shift 2 ;;
    --effort) EFFORT_OVERRIDE="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) EXTRA="$EXTRA $1"; shift ;;
  esac
done
CONFIG="$(af_resolve_config "$CONFIG" "$ROOT")"
CFG="$(af_lane_cfg "$CONFIG" review)"
if [ "${CFG%% *}" = "OK" ]; then set -- $CFG; MODEL="${MODEL_OVERRIDE:-$3}"; EFFORT="${EFFORT_OVERRIDE:-$4}"; else MODEL="${MODEL_OVERRIDE:-gpt-5.6-sol}"; EFFORT="${EFFORT_OVERRIDE:-high}"; fi
if ! MSG="$(af_preflight codex -)"; then echo "REVIEW: unavailable — $MSG"; exit 3; fi
LOGDIR="$(af_home)/logs"; mkdir -p "$LOGDIR"; LOG="$LOGDIR/$(date +%Y%m%d-%H%M%S)-review.log"
read -r -d '' PROMPT <<'P' || true
Review these changes against the project's own contracts (its AGENTS.md or CLAUDE.md), then for correctness,
concurrency and state hazards, security-sensitive paths, and whether any docs or comments claim more than the
verification evidence supports. Do not edit files. Return exactly:
VERDICT: ship | fix-first | rethink
REASON: <evidence-based>
FINDINGS: <file:line — precise fix, or none>
RESIDUAL RISK: <one line or none>
P
cd "$ROOT"
echo "# $(date) codex review model=$MODEL effort=$EFFORT scope=${SCOPE[*]} config=$CONFIG" > "$LOG"
codex review -c "model=\"$MODEL\"" -c "model_reasoning_effort=$EFFORT" "${SCOPE[@]}" "$PROMPT$EXTRA" 2>&1 | tee -a "$LOG" | grep -v -E '^(provider|approval|sandbox|reasoning|session id|--------|user)' | tail -60
echo "LOG: $LOG"
