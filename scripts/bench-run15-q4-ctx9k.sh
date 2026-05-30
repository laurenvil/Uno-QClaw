#!/usr/bin/env bash
#
# bench-run15-q4-ctx9k.sh — Run 15: full 9-prompt agentic battery,
# default yzma model (Qwen_Qwen3.5-0.8B-Q4_0.gguf) with study-bible flags.
# ctx_size reduced to 9000 (from 16384) to measure impact on wall time and TG/PP.
#
# Config: yzma · ctx 9000 · port 8083 · --flash-attn on · --mlock
#         --cache-type-k q8_0 · --cache-type-v q8_0 · --reasoning-budget 800
#         --repeat-penalty 1.1 · --repeat-last-n 64
#
# Usage: cd <repo-root> && bash scripts/bench-run15-q4-ctx9k.sh

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BINARY="./build/qclaw"
LOG_DIR="docs/QClaw/v2/benchmarks/run15/raw"
TSV="docs/QClaw/v2/benchmarks/run15/timing.tsv"
SERVER_PORT=8083
API="http://127.0.0.1:${SERVER_PORT}/v1/chat/completions"

# ── Prompt battery ────────────────────────────────────────────────────────────

TAGS=(breathe blink pot button pwm_pins five_volt mpu_vs_mcu led_matrix compile_blink)

PROMPTS[0]="Make the LED on pin 9 breathe — fade in and out smoothly."
PROMPTS[1]="Write a sketch that blinks the built-in LED once per second."
PROMPTS[2]="Read a potentiometer connected to A0 and print its value to the Serial Monitor."
PROMPTS[3]="When a button on pin 2 is pressed, turn on the LED on pin 13; otherwise turn it off."
PROMPTS[4]="Which pins on the Uno Q can do PWM?"
PROMPTS[5]="Can I connect a 5V sensor to A0?"
PROMPTS[6]="What is the difference between the MPU and the MCU on the Uno Q?"
PROMPTS[7]="Scroll 'QClaw' across the Uno Q LED matrix and upload it to the board."
PROMPTS[8]="Write a sketch that blinks the built-in LED once per second, then compile and upload it to the board."

# ── Helpers ───────────────────────────────────────────────────────────────────

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

# ── Pre-flight ────────────────────────────────────────────────────────────────

if [ ! -x "$BINARY" ]; then
    log "ERROR: $BINARY not found — run 'make build' first"; exit 1
fi

mkdir -p "$LOG_DIR"
: > "$LOG_DIR/../run.log"

log "Run 15 — Q4_0 yzma study-bible · ctx 9000 · full 9-prompt agentic battery"
log "Binary : $BINARY"
log "Logs   : $LOG_DIR"
log "Model  : yzma (Qwen_Qwen3.5-0.8B-Q4_0.gguf, 490 MB, ctx 9000, port $SERVER_PORT)"
log "Flags  : --flash-attn on --mlock --cache-type-k q8_0 --cache-type-v q8_0 --reasoning-budget 800 --repeat-penalty 1.1 --repeat-last-n 64"
log "TG/PP  : measured via /v1/chat/completions timing probe after each prompt"
log ""

if pgrep -f "llama-server.*${SERVER_PORT}" > /dev/null 2>&1; then
    log "Killing stale llama-server on port $SERVER_PORT…"
    pkill -f "llama-server.*${SERVER_PORT}" 2>/dev/null || true
    sleep 2
fi

rm -f ~/.qclaw/workspace/sessions/run15-p* 2>/dev/null || true
log "Sessions cleared"
log ""

# TSV header
printf 'idx\ttag\twall_s\twall_fmt\titerations\ttool_calls\tpp_tok_s\ttg_tok_s\tprobe_pp_n\tprobe_tg_n\tresp_chars\tstatus\n' \
    > "$TSV"

# ── Main loop ─────────────────────────────────────────────────────────────────

for i in "${!TAGS[@]}"; do
    TAG="${TAGS[$i]}"
    PROMPT="${PROMPTS[$i]}"
    SESSION="run15-p${i}"
    LOGFILE="$LOG_DIR/${TAG}.log"
    : > "$LOGFILE"

    if [ "$i" -eq 0 ]; then
        log "=== Prompt $i: $TAG  [COLD — server will start now] ==="
    else
        log "=== Prompt $i: $TAG  [warm server] ==="
    fi
    log "  Prompt: $PROMPT"

    # ── Agentic run ──────────────────────────────────────────────────────────
    START_TS=$(date +%s)
    set +e
    { time "$BINARY" agent -m "$PROMPT" --session "$SESSION"; } > "$LOGFILE" 2>&1
    EXIT_CODE=$?
    set -e
    END_TS=$(date +%s)
    WALL_S=$(( END_TS - START_TS ))

    WALL_FMT="$(( WALL_S / 60 ))m$(( WALL_S % 60 ))s"

    # ── Parse agentic log ────────────────────────────────────────────────────
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

    # ── Timing probe (warm server, after agentic run) ─────────────────────
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
        "$i" "$TAG" "$WALL_S" "$WALL_FMT" \
        "$ITERATIONS" "$TOOL_CALLS" \
        "$PP_TOK_S" "$TG_TOK_S" \
        "$PROBE_PP_N" "$PROBE_TG_N" \
        "$RESP_CHARS" "$STATUS" \
        >> "$TSV"
done

# ── Final summary ─────────────────────────────────────────────────────────────

log "=== Run 15 complete ==="
log ""
log "$(column -t -s $'\t' "$TSV")"
