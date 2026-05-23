#!/usr/bin/env bash
#
# compare-cpu-implementations.sh — Compare Yzama vs V2 CPU performance
set -euo pipefail

MODEL="${QCLAW_MODEL:-$HOME/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf}"
YZMA_BIN="/home/arduino/ArduinoApps/yzma/lib/llama-server"
V2_BIN="./engines/llamacli/mpu/llama-server"

echo "=== CPU Performance Comparison ==="

run_cpu_bench() {
    local label="$1" bin="$2"
    echo ""
    echo "--- Testing: $label ---"
    
    # Start server
    "$bin" -m "$MODEL" -ngl 0 -t 4 -c 2048 --log-disable > /tmp/compare-server.log 2>&1 &
    local pid=$!
    
    # Wait for ready
    local ready=0
    for i in {1..60}; do
        if curl -s http://localhost:8080/health | grep -q '{"status":"ok"}'; then
            ready=1
            break
        fi
        sleep 1
    done
    
    if [ $ready -eq 0 ]; then
        echo "Error: $label failed to start"
        kill $pid || true
        return
    fi
    
    # Measure
    local resp=$(curl -s -X POST http://localhost:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -d '{
        "messages": [{"role": "user", "content": "Reply with a 50-word story about a robot."}],
        "max_tokens": 100,
        "temperature": 0.0
      }')
    
    echo "$resp" | jq -r '.timings | "  Prompt: \(.prompt_per_second) t/s\n  Generation: \(.predicted_per_second) t/s"'
    
    # Cleanup
    kill $pid
    wait $pid || true
}

run_cpu_bench "Yzama (Main Branch Baseline)" "$YZMA_BIN"
run_cpu_bench "V2 (Persistent Optimized)" "$V2_BIN"

echo ""
echo "=== Done ==="
