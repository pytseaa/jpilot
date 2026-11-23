#!/usr/bin/env bash
# Measures what one small TACC submission costs. Run it in WSL (Ubuntu):
#   bash eval/tacc_probe/probe.sh
# It submits eval/tacc_probe/client (1 CPU, at most 5 minutes, no GPU, no Qwen calls),
# polls the job every POLL seconds, and writes events and a summary to out/<timestamp>/.
# TCLOUD   path of the tcloud program (default: tcloud, then ~/bin/tcloud).
# JOB_ID   set it to skip the job-id parse if the script cannot find it in the submit output.
set -u
POLL=${POLL:-5}
MAX_WAIT=${MAX_WAIT:-900}
if [ -z "${TCLOUD:-}" ]; then
    if command -v tcloud >/dev/null 2>&1; then TCLOUD=$(command -v tcloud); else TCLOUD="$HOME/bin/tcloud"; fi
fi
[ -x "$TCLOUD" ] || { echo "tcloud not found (set TCLOUD=/path/to/tcloud)" >&2; exit 1; }
tc() { "$TCLOUD" "$@"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${OUT_DIR:-$HERE/out}/$STAMP"
RUN="$(mktemp -d /tmp/jp_probe.XXXXXX)"
mkdir -p "$OUT"
EVENTS="$OUT/events.tsv"

ev() {
    printf '%s\t%s\t%s\n' "$(date -u +%FT%T.%3NZ)" "$1" "${2:-}" >> "$EVENTS"
    printf '[%s] %s %s\n' "$(date -u +%T)" "$1" "${2:-}"
}
secs() { awk -v a="$1" -v b="$2" 'BEGIN { printf "%.1f", b - a }'; }

for f in main.py job.sh tuxiv.conf; do
    [ -s "$HERE/client/$f" ] || { echo "missing client file: $HERE/client/$f" >&2; exit 1; }
done
# Strip carriage returns on copy: a Windows checkout can add them, and bash and YAML on TACC reject them.
for f in main.py job.sh tuxiv.conf; do tr -d '\015' < "$HERE/client/$f" > "$RUN/$f"; done
NONCE="probe-$STAMP-$RANDOM"
printf '{"nonce": "%s"}\n' "$NONCE" > "$RUN/input.json"
echo "$NONCE" > "$OUT/nonce.txt"

ev SUBMIT_BEGIN
T0=$(date +%s.%N)
( cd "$RUN" && tc submit ) > "$OUT/submit.txt" 2>&1
RC=$?
T1=$(date +%s.%N)
ev SUBMIT_END "rc=$RC seconds=$(secs "$T0" "$T1")"
echo "---- tcloud submit printed:"
tr -d '\000' < "$OUT/submit.txt"
echo "----"
if [ "$RC" -ne 0 ]; then
    echo "tcloud submit failed (exit $RC), so nothing is being measured. Stopping." >&2
    echo "Check with: $TCLOUD ps" >&2
    rm -rf "$RUN"
    exit 1
fi

JOB="${JOB_ID:-}"
if [ -z "$JOB" ]; then
    # tcloud prints NUL bytes into its output, which makes grep treat the file as binary, so strip them first.
    # Only "Submitted batch job N" counts: other numbers in the output are dates or versions.
    JOB=$(tr -d '\000' < "$OUT/submit.txt" | grep -ioE 'submitted batch job [0-9]+' | grep -oE '[0-9]+' | head -1)
fi
if [ -z "$JOB" ]; then
    echo "Could not find a job id (submit output saved to $OUT/submit.txt)." >&2
    echo "The job may still be running. Find its number with '$TCLOUD ps' and re-run with JOB_ID=<number>." >&2
    exit 1
fi
ev JOB_ID "$JOB"

LOG="slurm_log/jobpilot-probe-$JOB.log"
LAST=""
SEEN_LIVE=0
GONE=0
CAT_BEATS_MAX=0
START=$(date +%s)
while [ $(( $(date +%s) - START )) -lt "$MAX_WAIT" ]; do
    P0=$(date +%s.%N)
    PS=$(tc ps -j "$JOB" 2>&1)
    P1=$(date +%s.%N)
    STATE=$(printf '%s\n' "$PS" | awk -v j="$JOB" '$1 == j { print $5; exit }')
    if [ -z "$STATE" ]; then
        GONE=$(( GONE + 1 ))
        STATE=GONE
    else
        GONE=0
        SEEN_LIVE=1
    fi
    if [ "$STATE" != "$LAST" ]; then
        ev STATE "$STATE ps_call_seconds=$(secs "$P0" "$P1")"
        LAST=$STATE
    fi
    if [ "$STATE" = R ]; then
        C0=$(date +%s.%N)
        CAT=$(tc cat "$LOG" 2>&1)
        C1=$(date +%s.%N)
        BEATS=$(printf '%s\n' "$CAT" | grep -c ' BEAT ')
        if [ "$BEATS" -gt "$CAT_BEATS_MAX" ]; then
            CAT_BEATS_MAX=$BEATS
            ev CAT_WHILE_RUNNING "beat_lines=$BEATS cat_call_seconds=$(secs "$C0" "$C1")"
        fi
    fi
    # Two empty polls in a row after the job was seen, or six if it was never seen.
    if [ "$STATE" = GONE ] && { [ "$GONE" -ge 6 ] || { [ "$SEEN_LIVE" = 1 ] && [ "$GONE" -ge 2 ]; }; }; then
        break
    fi
    sleep "$POLL"
done
ev POLL_END "last_state=$LAST"

D0=$(date +%s.%N)
tc download "CSIT6000V-project-results/probe-$JOB.json" "$OUT/result.json" > "$OUT/download-result.txt" 2>&1
tc download "$LOG" "$OUT/client.log" > "$OUT/download-log.txt" 2>&1
D1=$(date +%s.%N)
ev DOWNLOAD_END "two_downloads_seconds=$(secs "$D0" "$D1")"

tc ls CSIT6000V-project-results > "$OUT/ls-results.txt" 2>&1
if tr -d '\000' < "$OUT/ls-results.txt" | grep -q "probe-$JOB-delete-me.txt"; then
    ev USERDIR_FILE_STILL_LISTED "probe-$JOB-delete-me.txt"
else
    ev USERDIR_FILE_NOT_LISTED "probe-$JOB-delete-me.txt"
fi

python3 "$HERE/summarize.py" "$OUT" "$JOB"
rm -rf "$RUN"
echo "Files are in $OUT"
