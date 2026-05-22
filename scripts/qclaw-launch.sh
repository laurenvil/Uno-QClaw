#!/usr/bin/env bash
# qclaw-launch.sh — Sanity-check the llama-cli provider's prerequisites,
# (optionally) start the Telegram gateway, then drop into QClaw terminal chat.
#
# Under the llama-cli provider (QClaw-Client branch) there is no long-running
# llama-server: the Go provider in pkg/providers/llamacli spawns the
# precompiled mpu/llama-cli as a one-shot subprocess per Chat() call. This
# script no longer manages a server PID/log file.
set -euo pipefail

QCLAW_HOME="${QCLAW_HOME:-$HOME/.qclaw}"
QCLAW_MODEL="${QCLAW_MODEL:-$HOME/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf}"
LLAMA_CLI="${LLAMA_CLI:-./engines/llamacli/mpu/llama-cli}"
BINARY="${BINARY:-./build/qclaw}"
GATEWAY_LOG="$QCLAW_HOME/gateway.log"
GATEWAY_PID_FILE="$QCLAW_HOME/gateway.pid"

# ── Prerequisites ─────────────────────────────────────────────────────────────

if [ ! -f "$BINARY" ]; then
    echo "Error: QClaw binary not found at $BINARY"
    echo "Run: make build"
    exit 1
fi

if [ ! -x "$LLAMA_CLI" ]; then
    echo "Error: llama-cli not found at $LLAMA_CLI"
    echo "Run: git submodule update --init --recursive engines/llamacli"
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

if [ ! -f "$QCLAW_HOME/config.json" ]; then
    echo "Error: config not found at $QCLAW_HOME/config.json"
    echo "Run: make qclaw-setup"
    exit 1
fi

export LLAMA_CLI QCLAW_MODEL

# ── Cleanup ───────────────────────────────────────────────────────────────────

cleanup() {
    echo ""
    echo "Stopping QClaw..."
    if [ -f "$GATEWAY_PID_FILE" ]; then
        kill "$(cat "$GATEWAY_PID_FILE")" 2>/dev/null || true
        rm -f "$GATEWAY_PID_FILE"
        echo "  Stopped gateway"
    fi
    echo "  Done. See you next time!"
}
trap cleanup EXIT INT TERM

# Kill any stale gateway from a previous run
if [ -f "$GATEWAY_PID_FILE" ]; then
    kill "$(cat "$GATEWAY_PID_FILE")" 2>/dev/null || true
    rm -f "$GATEWAY_PID_FILE"
fi

# ── Gateway (Telegram) ────────────────────────────────────────────────────────

if grep -q '"token"' "$QCLAW_HOME/config.json" && \
   ! grep -q 'YOUR_TELEGRAM_BOT_TOKEN' "$QCLAW_HOME/config.json"; then
    echo "Starting QClaw gateway (Telegram)..."
    "$BINARY" gateway >> "$GATEWAY_LOG" 2>&1 &
    echo $! > "$GATEWAY_PID_FILE"
    sleep 1
    echo "  Gateway running — message your bot from Telegram"
else
    echo "  Telegram not configured — skipping gateway"
    echo "  (Set token in $QCLAW_HOME/config.json to enable)"
fi

# ── Terminal Chat ─────────────────────────────────────────────────────────────

echo ""
echo "  ┌───────────────────────────────────────────┐"
echo "  │  🧘  Q  C  L  A  W                        │"
echo "  │      Arduino AI Assistant                  │"
echo "  │      (llama-cli provider, on-device)       │"
echo "  │                                            │"
echo "  │  Type your question at 'You:' and press    │"
echo "  │  Enter. QClaw responds in a few seconds.   │"
echo "  │  Type 'exit' or Ctrl+C to quit.            │"
echo "  └───────────────────────────────────────────┘"
echo ""

"$BINARY" agent
