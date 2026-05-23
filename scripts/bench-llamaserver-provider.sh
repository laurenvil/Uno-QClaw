#!/usr/bin/env bash
#
# bench-llamaserver-provider.sh — Benchmark the new persistent llama-server provider (V2)
# Replicates the "Yzama pattern" and tests both CPU and GPU paths.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL="${QCLAW_MODEL:-$HOME/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf}"
OUT="$REPO/docs/GPU/benchmark-raw-v2.txt"

# Binaries to test
SERVER_CPU="/home/arduino/ArduinoApps/yzma/lib/llama-server"
SERVER_GPU="$REPO/engines/llamacli/mpu/llama-server"

mkdir -p "$(dirname "$OUT")"
: > "$OUT"

note()  { printf '\n=== %s ===\n' "$*" | tee -a "$OUT"; }
emit()  { printf '%s\n' "$*"        | tee -a "$OUT"; }

note "V2 Environment"
emit "date: $(date -u --iso-8601=seconds)"
emit "cpu_server: $SERVER_CPU"
emit "gpu_server: $SERVER_GPU"

run_bench() {
    local label="$1" bin="$2" ngl="$3"
    note "$label (ngl=$ngl)"
    
    # Start server
    "$bin" -m "$MODEL" -ngl "$ngl" -t 4 -c 2048 --log-disable > /tmp/bench-server.log 2>&1 &
    local pid=$!
    
    # Wait for ready (max 60s)
    local ready=0
    for i in {1..60}; do
        if curl -s http://localhost:8080/health | grep -q '{"status":"ok"}'; then
            ready=1
            break
        fi
        sleep 1
    done
    
    if [ $ready -eq 0 ]; then
        emit "Error: Server failed to start"
        kill $pid || true
        return
    fi
    
    # Run request and measure
    local t0 t1 wall_s
    t0=$(date +%s.%N)
    local resp=$(curl -s -X POST http://localhost:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -d '{
        "messages": [{"role": "user", "content": "Reply with pong"}],
        "max_tokens": 64,
        "temperature": 0.0
      }')
    t1=$(date +%s.%N)
    wall_s=$(awk "BEGIN{printf \"%.2f\", $t1 - $t0}")
    
    emit "Wall time: $wall_s s"
    echo "$resp" | jq -r '.timings | "Prompt: \(.prompt_per_second) t/s | Generation: \(.predicted_per_second) t/s"' | tee -a "$OUT"
    
    # Cleanup
    kill $pid
    wait $pid || true
}

run_bench "V2.1 Persistent CPU (Yzama)" "$SERVER_CPU" 0
run_bench "V2.2 Persistent GPU (Vulkan)" "$SERVER_GPU" 99

note "Done"
