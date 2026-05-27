#!/usr/bin/env bash
#
# bench-run14-resume.sh — Resume run 14 from prompt 6 (mpu_vs_mcu),
# appending to the existing TSV. Server expected warm on port 8083.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BINARY="./build/qclaw"
LOG_DIR="docs/benchmarks/run14/raw"
TSV="docs/benchmarks/run14/timing.tsv"
SERVER_PORT=8083
API="http://127.0.0.1:${SERVER_PORT}/v1/chat/completions"

TAGS=(mpu_vs_mcu led_matrix compile_blink)
PROMPTS[0]="What is the difference between the MPU and the MCU on the Uno Q?"
PROMPTS[1]="Scroll 'QClaw' across the Uno Q LED matrix and upload it to the board."
PROMPTS[2]="Write a sketch that blinks the built-in LED once per second, then compile and upload it to the board."
IDXS=(6 7 8)

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG_DIR/../run.log"; }
strip_ansi() { sed 's/\x1b\[[0-9;?]*[mKHJ]//g; s/\r//g'; }

probe_timing() {
    local result
    result=$(curl -sf --max-time 120 -X POST "$API" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "local",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "List three PWM pins on the Arduino Uno Q."}
            ],
            "max_tokens": 30,
            "stream": false,
            "temperature": 0.0
        }' 2>/dev/null) || true

    if [ -n "$result" ]; then
        printf '%s\n' "$result" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)
    t = r.get('timings', {})
    pp = t.get('prompt_per_second', 0)
    tg = t.get('predicted_per_second', 0)
    pn = t.get('prompt_n', 0)
    tn = t.get('predicted_n', 0)
    print(f'{pp:.2f}\t{tg:.2f}\t{pn}\t{tn}')
except Exception as e:
    print(f'n/a\tn/a\t0\t0')
" 2>/dev/null || printf 'n/a\tn/a\t0\t0'
    else
        printf 'n/a\tn/a\t0\t0'
    fi
}

if [ ! -x "$BINARY" ]; then
    log "ERROR: $BINARY not found"; exit 1
fi

log "Run 14 RESUME — prompts 6-8 (mpu_vs_mcu, led_matrix, compile_blink)"
log "Server: warm on port $SERVER_PORT (PID $(pgrep -f "llama-server.*${SERVER_PORT}" | head -1))"
log ""

for i in "${!TAGS[@]}"; do
    TAG="${TAGS[$i]}"
    PROMPT="${PROMPTS[$i]}"
    IDX="${IDXS[$i]}"
    SESSION="run14-p${IDX}"
    LOGFILE="$LOG_DIR/${TAG}.log"
    : > "$LOGFILE"

    log "=== Prompt $IDX: $TAG  [warm server] ==="
    log "  Prompt: $PROMPT"

    START_TS=$(date +%s)
    set +e
    { time "$BINARY" agent -m "$PROMPT" --session "$SESSION"; } > "$LOGFILE" 2>&1
    EXIT_CODE=$?
    set -e
    END_TS=$(date +%s)
    WALL_S=$(( END_TS - START_TS ))
    WALL_FMT="$(( WALL_S / 60 ))m$(( WALL_S % 60 ))s"

    CLEAN=$(strings "$LOGFILE" | strip_ansi)

    ITERATIONS=$(printf '%s\n' "$CLEAN" \
        | grep -oP '(?<=iterations=)\d+' | head -1 || true)
    ITERATIONS=${ITERATIONS:-0}

    TOOL_CALLS=$(printf '%s\n' "$CLEAN" \
        | grep -cP '\[iter \d+\]' 2>/dev/null || true)
    TOOL_CALLS=${TOOL_CALLS:-0}

    RESPONSE=$(printf '%s\n' "$CLEAN" \
        | grep -oP '(?<=QClaw: ).+' | head -1 || true)
    RESP_CHARS=${#RESPONSE}

    if [ "$EXIT_CODE" -ne 0 ]; then
        STATUS="error(${EXIT_CODE})"
    elif printf '%s\n' "$CLEAN" | grep -q "no response to give"; then
        STATUS="empty_response"
    elif printf '%s\n' "$CLEAN" | grep -qiE "exceeds.*context|context.*exceed"; then
        STATUS="ctx_overflow"
    else
        STATUS="ok"
    fi

    log "  Running timing probe…"
    PROBE=$(probe_timing)
    PP_TOK_S=$(printf '%s' "$PROBE" | cut -f1)
    TG_TOK_S=$(printf '%s' "$PROBE" | cut -f2)
    PROBE_PP_N=$(printf '%s' "$PROBE" | cut -f3)
    PROBE_TG_N=$(printf '%s' "$PROBE" | cut -f4)

    log "  Wall: ${WALL_S}s (${WALL_FMT}) | Iters: ${ITERATIONS} | Tools: ${TOOL_CALLS} | PP: ${PP_TOK_S} t/s (${PROBE_PP_N} tok) | TG: ${TG_TOK_S} t/s (${PROBE_TG_N} tok) | Status: $STATUS"
    log "  Response (${RESP_CHARS} chars): ${RESPONSE:0:140}"
    log ""

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$IDX" "$TAG" "$WALL_S" "$WALL_FMT" \
        "$ITERATIONS" "$TOOL_CALLS" \
        "$PP_TOK_S" "$TG_TOK_S" \
        "$PROBE_PP_N" "$PROBE_TG_N" \
        "$RESP_CHARS" "$STATUS" \
        >> "$TSV"
done

log "=== Run 14 resume complete ==="
log ""
log "$(column -t -s $'\t' "$TSV")"
