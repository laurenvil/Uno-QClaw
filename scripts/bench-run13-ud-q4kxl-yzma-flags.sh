#!/usr/bin/env bash
#
# bench-run13-ud-q4kxl-yzma-flags.sh — Run 13: full 9-prompt agentic battery,
# Qwen3.5-0.8B-UD-Q4_K_XL.gguf with the same flags + ctx as the Run 7
# yzma Q4_0 baseline (ctx 8192, flash-attn, mlock, kv-cache q8_0).
#
# Key differences vs Run 12:
#   - ctx 8192 (run 7 baseline context — may overflow on heavy prompts)
#   - No sampling overrides (temp 0.3 default, no top-p/top-k/min-p/penalty flags)
#   - --reasoning off + --reasoning-budget 0 (run 11 improvement retained)
#   - /no_think in SOUL.md (retained)
#
# Temporarily patches ~/.qclaw/config.json; restores on exit.
#
# Usage: cd <repo-root> && bash scripts/bench-run13-ud-q4kxl-yzma-flags.sh

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BINARY="./build/qclaw"
LOG_DIR="docs/benchmarks/run13/raw"
TSV="docs/benchmarks/run13/timing.tsv"
SERVER_PORT=8084
METRICS_URL="http://127.0.0.1:${SERVER_PORT}/metrics"
CONFIG="${HOME}/.qclaw/config.json"
CONFIG_BAK="${HOME}/.qclaw/config.json.run13.bak"

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
metrics_val() {
    local name="$1" text="$2"
    printf '%s\n' "$text" | grep "^${name}" | grep -v '^#' | awk '{print $NF}' | head -1
}

# ── Config patch / restore ────────────────────────────────────────────────────

restore_config() {
    if [ -f "$CONFIG_BAK" ]; then
        mv "$CONFIG_BAK" "$CONFIG"
        log "Config restored from backup."
    fi
}
trap restore_config EXIT

cp "$CONFIG" "$CONFIG_BAK"
log "Config backed up to $CONFIG_BAK"

python3 - "$CONFIG" <<'PYEOF'
import sys, json

path = sys.argv[1]
with open(path) as f:
    c = json.load(f)

q4kxl_entry = {
    "model_name": "yzma-q4kxl",
    "model": "llama-server/Qwen3.5-0.8B-UD-Q4_K_XL.gguf",
    "api_base": "engines/yzma/lib/llama-server",
    "api_key": "local",
    "request_timeout": 1200,
    "extra_body": {
        "ctx_size": 8192,
        "extra_args": [
            "--flash-attn", "on",
            "--mlock",
            "--cache-type-k", "q8_0",
            "--cache-type-v", "q8_0",
            "--reasoning", "off",
            "--reasoning-budget", "0",
        ],
        "lib_path": "engines/yzma/lib",
        "models_dir": "~/models",
        "parallel": 1,
        "port": 8084,
        "threads": 4
    }
}

c["model_list"] = [m for m in c.get("model_list", []) if m.get("model_name") != "yzma-q4kxl"]
c["model_list"].append(q4kxl_entry)

c.setdefault("agents", {}).setdefault("defaults", {})["model"] = "yzma-q4kxl"
c["agents"]["defaults"]["model_name"] = "yzma-q4kxl"
c["agents"]["defaults"]["temperature"] = 0.3

with open(path, "w") as f:
    json.dump(c, f, indent=2)

print("  Config patched: yzma-q4kxl ctx 8192 + yzma flags.")
PYEOF

# ── Pre-flight ────────────────────────────────────────────────────────────────

if [ ! -x "$BINARY" ]; then
    log "ERROR: $BINARY not found — run 'make build' first"; exit 1
fi

mkdir -p "$LOG_DIR"
: > "$LOG_DIR/../run.log"

log "Run 13 — UD-Q4_K_XL · yzma Q4 flags · ctx 8192"
log "Binary : $BINARY"
log "Logs   : $LOG_DIR"
log "Model  : yzma-q4kxl (Qwen3.5-0.8B-UD-Q4_K_XL.gguf, 559 MB, ctx 8192, port $SERVER_PORT)"
log "Flags  : --flash-attn on --mlock --cache-type-k q8_0 --cache-type-v q8_0 --reasoning off --reasoning-budget 0"
log ""

if pgrep -f "llama-server.*${SERVER_PORT}" > /dev/null 2>&1; then
    log "Killing stale llama-server on port $SERVER_PORT…"
    pkill -f "llama-server.*${SERVER_PORT}" 2>/dev/null || true
    sleep 2
fi

rm -f ~/.qclaw/workspace/sessions/run13-p* 2>/dev/null || true
log "Sessions cleared"
log ""

printf 'idx\ttag\twall_s\tturn_elapsed\titerations\ttool_calls\ttg_tok_s\tpp_tok_s\tresp_chars\tstatus\n' > "$TSV"

# ── Main loop ─────────────────────────────────────────────────────────────────

for i in "${!TAGS[@]}"; do
    TAG="${TAGS[$i]}"
    PROMPT="${PROMPTS[$i]}"
    SESSION="run13-p${i}"
    LOGFILE="$LOG_DIR/${TAG}.log"
    : > "$LOGFILE"

    if [ "$i" -eq 0 ]; then
        log "=== Prompt $i: $TAG  [COLD — server will start now] ==="
    else
        log "=== Prompt $i: $TAG  [warm server] ==="
    fi
    log "  Prompt: $PROMPT"

    BEFORE_M=""
    curl -sf --max-time 2 "$METRICS_URL" > /tmp/r13_before.txt 2>/dev/null \
        && BEFORE_M=$(cat /tmp/r13_before.txt) || true

    START_TS=$(date +%s)
    set +e
    { time "$BINARY" agent -m "$PROMPT" --session "$SESSION"; } > "$LOGFILE" 2>&1
    EXIT_CODE=$?
    set -e
    END_TS=$(date +%s)
    WALL_S=$(( END_TS - START_TS ))

    AFTER_M=""
    curl -sf --max-time 2 "$METRICS_URL" > /tmp/r13_after.txt 2>/dev/null \
        && AFTER_M=$(cat /tmp/r13_after.txt) || true

    CLEAN=$(strings "$LOGFILE" | strip_ansi)

    TURN_ELAPSED=$(printf '%s\n' "$CLEAN" \
        | grep -oP '(?<=⏱  )\d+m[\d.]+s|\d+[\d.]+s' | head -1 || true)
    ITERATIONS=$(printf '%s\n' "$CLEAN" \
        | grep -oP '(?<=iterations=)\d+' | head -1 || true)
    ITERATIONS=${ITERATIONS:-0}
    TOOL_CALLS=$(printf '%s\n' "$CLEAN" \
        | grep -cP '\[iter \d+\]' 2>/dev/null || true)
    TOOL_CALLS=${TOOL_CALLS:-0}
    RESPONSE=$(printf '%s\n' "$CLEAN" \
        | grep -oP '(?<=QClaw: ).+' | head -1 || true)
    RESP_CHARS=${#RESPONSE}

    TG_TOK_S="n/a"; PP_TOK_S="n/a"
    if [ -n "$BEFORE_M" ] && [ -n "$AFTER_M" ]; then
        for PRED_NAME in "llamacpp:tokens_predicted_total" "llamacpp:generation_tokens_total" "llamacpp:n_predict_total"; do
            BP=$(metrics_val "$PRED_NAME" "$BEFORE_M"); AP=$(metrics_val "$PRED_NAME" "$AFTER_M")
            [ -n "$AP" ] && break
        done
        for PRED_S_NAME in "llamacpp:tokens_seconds_total" "llamacpp:generation_seconds_total" "llamacpp:t_token_total"; do
            BS=$(metrics_val "$PRED_S_NAME" "$BEFORE_M"); AS=$(metrics_val "$PRED_S_NAME" "$AFTER_M")
            [ -n "$AS" ] && break
        done
        for PP_NAME in "llamacpp:tokens_evaluated_total" "llamacpp:prompt_tokens_total" "llamacpp:n_prompt_tokens_processed_total"; do
            BPP=$(metrics_val "$PP_NAME" "$BEFORE_M"); APP=$(metrics_val "$PP_NAME" "$AFTER_M")
            [ -n "$APP" ] && break
        done
        for PP_S_NAME in "llamacpp:prompt_processing_seconds_total" "llamacpp:t_prompt_processing_total"; do
            BPPS=$(metrics_val "$PP_S_NAME" "$BEFORE_M"); APPS=$(metrics_val "$PP_S_NAME" "$AFTER_M")
            [ -n "$APPS" ] && break
        done
        if [ -n "${AP:-}" ] && [ -n "${BP:-}" ] && [ -n "${AS:-}" ] && [ -n "${BS:-}" ]; then
            TG_TOK_S=$(awk -v bp="${BP:-0}" -v ap="${AP:-0}" -v bs="${BS:-0}" -v as_="${AS:-0}" \
                'BEGIN{ dt=ap-bp; ds=as_-bs; if(ds>0) printf "%.2f", dt/ds; else print "n/a" }')
        fi
        if [ -n "${APP:-}" ] && [ -n "${BPP:-}" ] && [ -n "${APPS:-}" ] && [ -n "${BPPS:-}" ]; then
            PP_TOK_S=$(awk -v bp="${BPP:-0}" -v ap="${APP:-0}" -v bs="${BPPS:-0}" -v as_="${APPS:-0}" \
                'BEGIN{ dt=ap-bp; ds=as_-bs; if(ds>0) printf "%.2f", dt/ds; else print "n/a" }')
        fi
    fi

    if [ "$EXIT_CODE" -ne 0 ]; then
        STATUS="error(${EXIT_CODE})"
    elif printf '%s\n' "$CLEAN" | grep -q "no response to give"; then
        STATUS="empty_response"
    elif printf '%s\n' "$CLEAN" | grep -qiE "exceeds.*context|context.*exceed"; then
        STATUS="ctx_overflow"
    else
        STATUS="ok"
    fi

    log "  Wall: ${WALL_S}s | Turn: ${TURN_ELAPSED:-—} | Iters: ${ITERATIONS} | Tools: ${TOOL_CALLS} | TG: ${TG_TOK_S} t/s | PP: ${PP_TOK_S} t/s | Status: $STATUS"
    log "  Response (${RESP_CHARS} chars): ${RESPONSE:0:140}"
    log ""

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$i" "$TAG" "$WALL_S" "${TURN_ELAPSED:-}" \
        "$ITERATIONS" "$TOOL_CALLS" "$TG_TOK_S" "$PP_TOK_S" \
        "$RESP_CHARS" "$STATUS" >> "$TSV"
done

log "=== Run 13 complete ==="
log "TSV summary: $TSV"
log ""
column -t -s $'\t' "$TSV"
