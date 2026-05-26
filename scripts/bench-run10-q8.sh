#!/usr/bin/env bash
#
# bench-run10-q8.sh — Run 10: full 9-prompt agentic battery, yzma Q8 model
#
# Measures wall latency, agent turn time, tool calls, and response quality for
# each of the standard 9 benchmark prompts using Qwen3.5-0.8B-Q8_0.gguf via the
# persistent llamaserver provider (port 8084, ctx 16384).
#
# Prompt 0 is cold (server cold-start + full system-prompt prefill).
# Prompts 1-8 reuse the warm server; each gets a fresh session key so no
# conversation context bleeds between prompts.
#
# Output:
#   docs/benchmarks/run10/raw/<tag>.log    — raw agent stdout+stderr per prompt
#   docs/benchmarks/run10/timing.tsv       — tab-separated summary for the report
#
# Usage: cd <repo-root> && bash scripts/bench-run10-q8.sh

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BINARY="./build/qclaw"
LOG_DIR="docs/benchmarks/run10/raw"
TSV="docs/benchmarks/run10/timing.tsv"
SERVER_PORT=8084
METRICS_URL="http://127.0.0.1:${SERVER_PORT}/metrics"

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

# Extract a counter from Prometheus-format /metrics text.
# Handles both bare label and {label="..."} forms.
metrics_val() {
    local name="$1" text="$2"
    printf '%s\n' "$text" | grep "^${name}" | grep -v '^#' | awk '{print $NF}' | head -1
}

# ── Pre-flight ────────────────────────────────────────────────────────────────

if [ ! -x "$BINARY" ]; then
    log "ERROR: $BINARY not found — run 'make build' first"; exit 1
fi

log "Run 10 — Q8 9-prompt agentic battery"
log "Binary : $BINARY"
log "Logs   : $LOG_DIR"
log "Model  : yzma-q8 (Qwen3.5-0.8B-Q8_0.gguf, ctx 16384, port $SERVER_PORT)"
log ""

# Kill any stale Q8 server so prompt 0 is a true cold start.
if pgrep -f "llama-server.*${SERVER_PORT}" > /dev/null 2>&1; then
    log "Killing stale llama-server on port $SERVER_PORT (ensuring cold start)…"
    pkill -f "llama-server.*${SERVER_PORT}" 2>/dev/null || true
    sleep 2
fi

# Clear any session files from this run key prefix.
rm -f ~/.qclaw/workspace/sessions/run10-p* 2>/dev/null || true
log "Sessions cleared"
log ""

# TSV header
printf 'idx\ttag\twall_s\tturn_elapsed\titerations\ttool_calls\ttg_tok_s\tpp_tok_s\tresp_chars\tstatus\n' \
    > "$TSV"

# ── Main loop ─────────────────────────────────────────────────────────────────

for i in "${!TAGS[@]}"; do
    TAG="${TAGS[$i]}"
    PROMPT="${PROMPTS[$i]}"
    SESSION="run10-p${i}"
    LOGFILE="$LOG_DIR/${TAG}.log"
    : > "$LOGFILE"

    if [ "$i" -eq 0 ]; then
        log "=== Prompt $i: $TAG  [COLD — server will start now] ==="
    else
        log "=== Prompt $i: $TAG  [warm server] ==="
    fi
    log "  Prompt: $PROMPT"

    # Snapshot metrics before (best-effort; server may not be up yet for i=0)
    BEFORE_M=""
    curl -sf --max-time 2 "$METRICS_URL" > /tmp/r10_before.txt 2>/dev/null \
        && BEFORE_M=$(cat /tmp/r10_before.txt) || true

    # Timed run
    START_TS=$(date +%s)
    set +e
    { time "$BINARY" agent -m "$PROMPT" --session "$SESSION"; } \
        > "$LOGFILE" 2>&1
    EXIT_CODE=$?
    set -e
    END_TS=$(date +%s)
    WALL_S=$(( END_TS - START_TS ))

    # Snapshot metrics after
    AFTER_M=""
    curl -sf --max-time 2 "$METRICS_URL" > /tmp/r10_after.txt 2>/dev/null \
        && AFTER_M=$(cat /tmp/r10_after.txt) || true

    # ── Parse log ────────────────────────────────────────────────────────────

    CLEAN=$(strings "$LOGFILE" | strip_ansi)

    # Agent turn elapsed from the ⏱ summary line, e.g. "  ⏱  12m3.5s"
    TURN_ELAPSED=$(printf '%s\n' "$CLEAN" \
        | grep -oP '(?<=⏱  )\d+m[\d.]+s|\d+[\d.]+s' | head -1 || true)

    # Total agentic iterations from loop structured log
    ITERATIONS=$(printf '%s\n' "$CLEAN" \
        | grep -oP '(?<=iterations=)\d+' | head -1 || true)
    ITERATIONS=${ITERATIONS:-0}

    # Tool calls fired: count "🔧 [iter N]" or "[iter N]" marker lines
    TOOL_CALLS=$(printf '%s\n' "$CLEAN" \
        | grep -cP '\[iter \d+\]' 2>/dev/null || true)
    TOOL_CALLS=${TOOL_CALLS:-0}

    # Response text (first QClaw: line)
    RESPONSE=$(printf '%s\n' "$CLEAN" \
        | grep -oP '(?<=QClaw: ).+' | head -1 || true)
    RESP_CHARS=${#RESPONSE}

    # TG and PP t/s from metrics delta (best-effort)
    TG_TOK_S="n/a"
    PP_TOK_S="n/a"
    if [ -n "$BEFORE_M" ] && [ -n "$AFTER_M" ]; then
        # Try common counter name patterns across llama-server builds
        for PRED_NAME in \
            "llamacpp:tokens_predicted_total" \
            "llamacpp:generation_tokens_total" \
            "llamacpp:n_predict_total"; do
            BP=$(metrics_val "$PRED_NAME" "$BEFORE_M")
            AP=$(metrics_val "$PRED_NAME" "$AFTER_M")
            [ -n "$AP" ] && break
        done
        for PRED_S_NAME in \
            "llamacpp:tokens_seconds_total" \
            "llamacpp:generation_seconds_total" \
            "llamacpp:t_token_total"; do
            BS=$(metrics_val "$PRED_S_NAME" "$BEFORE_M")
            AS=$(metrics_val "$PRED_S_NAME" "$AFTER_M")
            [ -n "$AS" ] && break
        done
        for PP_NAME in \
            "llamacpp:tokens_evaluated_total" \
            "llamacpp:prompt_tokens_total" \
            "llamacpp:n_prompt_tokens_processed_total"; do
            BPP=$(metrics_val "$PP_NAME" "$BEFORE_M")
            APP=$(metrics_val "$PP_NAME" "$AFTER_M")
            [ -n "$APP" ] && break
        done
        for PP_S_NAME in \
            "llamacpp:prompt_processing_seconds_total" \
            "llamacpp:t_prompt_processing_total"; do
            BPPS=$(metrics_val "$PP_S_NAME" "$BEFORE_M")
            APPS=$(metrics_val "$PP_S_NAME" "$AFTER_M")
            [ -n "$APPS" ] && break
        done

        if [ -n "${AP:-}" ] && [ -n "${BP:-}" ] && [ -n "${AS:-}" ] && [ -n "${BS:-}" ]; then
            TG_TOK_S=$(awk \
                -v bp="${BP:-0}" -v ap="${AP:-0}" \
                -v bs="${BS:-0}" -v as_="${AS:-0}" \
                'BEGIN{ dt=ap-bp; ds=as_-bs; if(ds>0) printf "%.2f", dt/ds; else print "n/a" }')
        fi
        if [ -n "${APP:-}" ] && [ -n "${BPP:-}" ] && [ -n "${APPS:-}" ] && [ -n "${BPPS:-}" ]; then
            PP_TOK_S=$(awk \
                -v bp="${BPP:-0}" -v ap="${APP:-0}" \
                -v bs="${BPPS:-0}" -v as_="${APPS:-0}" \
                'BEGIN{ dt=ap-bp; ds=as_-bs; if(ds>0) printf "%.2f", dt/ds; else print "n/a" }')
        fi
    fi

    # Determine status
    if [ "$EXIT_CODE" -ne 0 ]; then
        STATUS="error(${EXIT_CODE})"
    elif printf '%s\n' "$CLEAN" | grep -q "no response to give"; then
        STATUS="empty_response"
    else
        STATUS="ok"
    fi

    log "  Wall: ${WALL_S}s | Turn: ${TURN_ELAPSED:-—} | Iters: ${ITERATIONS} | Tools: ${TOOL_CALLS} | TG: ${TG_TOK_S} t/s | PP: ${PP_TOK_S} t/s | Status: $STATUS"
    log "  Response (${RESP_CHARS} chars): ${RESPONSE:0:140}"
    log ""

    # Append TSV row
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$i" "$TAG" "$WALL_S" "${TURN_ELAPSED:-}" \
        "$ITERATIONS" "$TOOL_CALLS" "$TG_TOK_S" "$PP_TOK_S" \
        "$RESP_CHARS" "$STATUS" \
        >> "$TSV"
done

# ── Final summary ─────────────────────────────────────────────────────────────

log "=== Run 10 complete ==="
log "TSV summary: $TSV"
log ""
column -t -s $'\t' "$TSV"
