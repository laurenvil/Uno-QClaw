#!/usr/bin/env bash
#
# bench-llamacli-provider.sh — Benchmark the new llama-cli provider
# (QClaw-Client branch) against the assix-bundled mpu/llama-cli + Qwen Q4_0.
#
# Three phases:
#   A) Direct binary runs at varying decode lengths (capture native t/s line)
#   B) Cold-start cost (model load + grammar compile, no generation)
#   C) Go provider end-to-end via the existing integration tests
#
# Run from the qclaw repo root on the Uno Q.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$REPO/engines/llamacli/mpu/llama-cli"
MODEL="${QCLAW_MODEL:-$HOME/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf}"
OUT="$REPO/docs/GPU/benchmark-raw.txt"
mkdir -p "$(dirname "$OUT")"
: > "$OUT"

note()  { printf '\n=== %s ===\n' "$*" | tee -a "$OUT"; }
emit()  { printf '%s\n' "$*"        | tee -a "$OUT"; }

note "Environment"
emit "date: $(date -u --iso-8601=seconds)"
emit "uname: $(uname -r)"
emit "cpu_features: $(grep -m1 '^Features' /proc/cpuinfo | sed 's/^Features\s*:\s*//')"
emit "cores: $(nproc)"
emit "mem_MB_avail: $(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)"
emit "binary: $BIN ($(stat -c '%s' "$BIN") bytes)"
emit "model:  $MODEL ($(stat -c '%s' "$MODEL") bytes)"

#
# A) Direct binary — vary decode length, capture native [Prompt | Generation] line
#

run_direct() {
    local label="$1" n="$2" prompt="$3"
    note "$label  (n=$n tokens, t=4, ctx=2048)"
    local t0 t1 wall_s
    t0=$(date +%s.%N)
    "$BIN" -m "$MODEL" -st --reasoning off -c 2048 -t 4 -n "$n" --temp 0.0 \
        -p "$prompt" 2>&1 |
        grep -E "Prompt: .* t/s|Generation: .* t/s|drop unsupported|FD702|OpenCL" |
        tee -a "$OUT"
    t1=$(date +%s.%N)
    wall_s=$(awk "BEGIN{printf \"%.2f\", $t1 - $t0}")
    emit "wall_s: $wall_s"
}

run_direct "A.1 short prompt, 16-tok decode" 16   "Reply with one word: pong"
run_direct "A.2 short prompt, 64-tok decode" 64   "Reply with one word: pong"
run_direct "A.3 short prompt, 128-tok decode" 128 "Reply with one sentence about the Arduino Uno Q."

#
# B) Cold-start cost — load model + compile a small grammar, generate 0 tokens
#

note "B.1 Cold start (model load + grammar compile, n=1)"
t0=$(date +%s.%N)
"$BIN" -m "$MODEL" -st --reasoning off \
    --grammar 'root ::= "x"' \
    -c 2048 -t 4 -n 1 --temp 0.0 -p 'x' 2>&1 |
    grep -E "Prompt: .* t/s|Generation: .* t/s|drop unsupported|FD702" |
    tee -a "$OUT"
t1=$(date +%s.%N)
emit "cold_wall_s: $(awk "BEGIN{printf \"%.2f\", $t1 - $t0}")"

#
# C) Go provider end-to-end (text + tool-call)
#

note "C.1 Go provider — TestIntegration_LlamaCLIText"
GOTOOLCHAIN=auto go test -tags=integration -run TestIntegration_LlamaCLIText \
    -v -count=1 -timeout 10m ./pkg/providers/llamacli/ 2>&1 |
    grep -E "PASS|FAIL|response:|^=== RUN|^--- |^ok\s" | tee -a "$OUT"

note "C.2 Go provider — TestIntegration_LlamaCLIToolCall"
GOTOOLCHAIN=auto go test -tags=integration -run TestIntegration_LlamaCLIToolCall \
    -v -count=1 -timeout 10m ./pkg/providers/llamacli/ 2>&1 |
    grep -E "PASS|FAIL|response:|^=== RUN|^--- |^ok\s" | tee -a "$OUT"

note "Done"
emit "Raw output: $OUT"
