#!/usr/bin/env bash
# qclaw-launch-direct.sh — Start llama-server (background) and drop into the
# Direct-Server REPL: 23-rule pre-router + direct API, no agent loop, no tools.
#
# Use this path for fast Q&A across the full 15-skill pre-router surface
# (sketch-patterns, led-matrix, uno-q-hardware, bridge, wireless, vision, audio,
# arduino-app-lab, modulino, linux-led + general skills). Sketches and code
# come back as text for the user to copy.
#
# The agent loop and the 8 tools (arduino, camera, sysfs_led, network,
# i2cdetect, read_file, write_file, list_dir) are NOT available here — for
# compile/upload/camera/LED/I²C workflows use `make qclaw-agentic` instead.
set -euo pipefail

PICOCLAW_HOME="${PICOCLAW_HOME:-$HOME/.picoclaw}"
QCLAW_MODEL="${QCLAW_MODEL:-$HOME/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf}"
LLAMA_SERVER="${LLAMA_SERVER:-./yzma/lib/llama-server}"
LLAMA_PORT="${LLAMA_PORT:-8080}"
LLAMA_LOG="$PICOCLAW_HOME/llama-server.log"
LLAMA_PID_FILE="$PICOCLAW_HOME/llama-server.pid"
DIRECT_CHAT="${DIRECT_CHAT:-./scripts/qclaw-direct-chat.py}"

# ── Prerequisites ─────────────────────────────────────────────────────────────

if [ ! -f "$LLAMA_SERVER" ]; then
    echo "Error: llama-server not found at $LLAMA_SERVER"
    echo "Run: cd yzma && make download-llama.cpp"
    exit 1
fi

if [ ! -f "$QCLAW_MODEL" ]; then
    echo "Error: model not found at $QCLAW_MODEL"
    echo "Download with:"
    echo "  mkdir -p ~/models"
    echo "  wget -O $QCLAW_MODEL \\"
    echo "    'https://huggingface.co/Qwen/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_0.gguf'"
    exit 1
fi

if [ ! -f "$PICOCLAW_HOME/workspace/SOUL.md" ]; then
    echo "Error: SOUL.md not found at $PICOCLAW_HOME/workspace/SOUL.md"
    echo "Run: make qclaw-setup"
    exit 1
fi

if [ ! -f "$DIRECT_CHAT" ]; then
    echo "Error: direct-chat script not found at $DIRECT_CHAT"
    exit 1
fi

# ── Cleanup ───────────────────────────────────────────────────────────────────

cleanup() {
    echo ""
    echo "Stopping QClaw (direct mode)..."
    if [ -f "$LLAMA_PID_FILE" ]; then
        kill "$(cat "$LLAMA_PID_FILE")" 2>/dev/null || true
        rm -f "$LLAMA_PID_FILE"
        echo "  Stopped llama-server"
    fi
    echo "  Done. See you next time!"
}
trap cleanup EXIT INT TERM

# Kill any stale llama-server from a previous run
if [ -f "$LLAMA_PID_FILE" ]; then
    kill "$(cat "$LLAMA_PID_FILE")" 2>/dev/null || true
    rm -f "$LLAMA_PID_FILE"
fi

# ── llama-server ──────────────────────────────────────────────────────────────

# Skip start if already serving the requested model
if curl -sf "http://127.0.0.1:${LLAMA_PORT}/v1/models" > /dev/null 2>&1; then
    echo "  llama-server already running on port $LLAMA_PORT — reusing"
else
    echo "Starting llama-server (model: $(basename "$QCLAW_MODEL"))..."
    "$LLAMA_SERVER" \
        -m "$QCLAW_MODEL" \
        --host 127.0.0.1 \
        --port "$LLAMA_PORT" \
        --ctx-size 8192 \
        --parallel 1 \
        -t 4 \
        --flash-attn on \
        --mlock \
        --cache-type-k q8_0 \
        --cache-type-v q8_0 \
        --reasoning-budget 800 \
        >> "$LLAMA_LOG" 2>&1 &
    echo $! > "$LLAMA_PID_FILE"

    echo "Waiting for llama-server to be ready..."
    READY=0
    for i in $(seq 1 30); do
        if curl -sf "http://127.0.0.1:${LLAMA_PORT}/v1/models" > /dev/null 2>&1; then
            READY=1
            echo "  Ready after ${i}s"
            break
        fi
        sleep 2
    done

    if [ "$READY" -eq 0 ]; then
        echo "Error: llama-server did not start within 60 seconds."
        echo "Check the log: $LLAMA_LOG"
        exit 1
    fi
fi

# ── Direct REPL ───────────────────────────────────────────────────────────────

exec python3 "$DIRECT_CHAT"
