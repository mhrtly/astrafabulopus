#!/bin/bash
# Project verification behind a build lock, with a compact report.
#
#   verify.sh [--name LABEL] [--no-lock] [--config PATH] -- <command…>
#   verify.sh                      # runs verify.command from the lanes config
#
# One lock per project root: whole-module languages (Swift, Rust, Go) cannot build twice at once in the
# same output directory, so overlapping runs queue (up to 40 minutes) instead of corrupting each other.
set -uo pipefail
. "$(cd "$(dirname "$0")" && pwd)/_common.sh"
ROOT="$PWD"; CONFIG=""; NAME=""; LOCKING=1
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --no-lock) LOCKING=0; shift ;;
    --config) CONFIG="$2"; shift 2 ;;
    --) shift; break ;;
    *) echo "verify: unknown option $1" >&2; sed -n '2,6p' "$0"; exit 2 ;;
  esac
done
CONFIG="$(af_resolve_config "$CONFIG" "$ROOT")"
if [ $# -eq 0 ]; then
  CMDSTR="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("verify",{}).get("command",""))' "$CONFIG" 2>/dev/null)"
  [ -n "$CMDSTR" ] || { echo "verify: no command given and no verify.command in $CONFIG"; exit 2; }
  set -- bash -lc "$CMDSTR"
fi
LOGDIR="$(af_home)/logs"; mkdir -p "$LOGDIR" "$(af_home)/locks"
LOCK="$(af_home)/locks/$(printf '%s' "$ROOT" | shasum | cut -c1-12).lock"; WAITED=0
if [ "$LOCKING" -eq 1 ]; then
  while ! mkdir "$LOCK" 2>/dev/null; do
    OWNER="$(cat "$LOCK/pid" 2>/dev/null || true)"
    if [ -n "$OWNER" ] && ! kill -0 "$OWNER" 2>/dev/null; then rm -rf "$LOCK"; continue; fi
    [ "$WAITED" -eq 0 ] && echo "verify: another build holds $LOCK (pid ${OWNER:-?}); waiting…"
    sleep 10; WAITED=$((WAITED+10))
    if [ "$WAITED" -ge 2400 ]; then echo "verify: gave up waiting for the build lock after 40 min"; exit 6; fi
  done
  echo $$ > "$LOCK/pid"; trap 'rm -rf "$LOCK"' EXIT
fi
LOG="$LOGDIR/$(date +%Y%m%d-%H%M%S)-verify${NAME:+-$NAME}.log"; START=$(date +%s)
{ echo "# $(date) verify root=$ROOT cmd: $*"; } > "$LOG"
( cd "$ROOT" && "$@" ) >> "$LOG" 2>&1; RESULT=$?
DURATION=$(( $(date +%s) - START ))
echo "VERIFY REPORT"
echo "COMMAND: $*"
echo "EXIT: $RESULT  DURATION: ${DURATION}s"
SUMMARY="$(grep -E -i "^[[:space:]]*(Executed [0-9]+ tests?|[0-9]+ passed|[0-9]+ (tests?|specs?) (passed|failed)|Tests?:|test result:|ok[[:space:]]+[0-9]+ tests?|PASS|FAIL)" "$LOG" | tail -3)"
[ -n "$SUMMARY" ] && { echo "SUMMARY:"; printf '%s\n' "$SUMMARY" | sed 's/^/  /'; }
if [ "$RESULT" -ne 0 ]; then
  echo "FAILURES:"; grep -E "error:|error\[|FAIL|failed|panicked|Exception|AssertionError|Traceback" "$LOG" | grep -v -i "warning" | head -12 | sed 's/^/  /'
fi
echo "LOG: $LOG"
if [ "$RESULT" -eq 0 ]; then echo "VERDICT: PASS"; else echo "VERDICT: FAIL ($RESULT)"; fi
exit $RESULT
