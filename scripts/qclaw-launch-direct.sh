#!/usr/bin/env bash
# qclaw-launch-direct.sh — Launch QClaw in Direct mode (single-turn, no tools).
#
# Direct mode uses the same pre-router and skills as agentic mode, but 
# skips the tool loop for faster Q&A.
set -euo pipefail

QCLAW_HOME="${QCLAW_HOME:-$HOME/.qclaw}"
QCLAW_MODEL="${QCLAW_MODEL:-$HOME/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf}"
LLAMA_CLI="${LLAMA_CLI:-./engines/llamacli/mpu/llama-cli}"
BINARY="${BINARY:-./build/qclaw}"

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
    exit 1
fi

export LLAMA_CLI QCLAW_MODEL

# ── Terminal Chat (Direct) ───────────────────────────────────────────────────

echo ""
echo "  ┌───────────────────────────────────────────┐"
echo "  │  🧘  Q  C  L  A  W  (DIRECT)             │"
echo "  │      Arduino AI Assistant                  │"
echo "  │      (Single-turn, no tools)               │"
echo "  │                                            │"
echo "  │  Type your question at 'Direct You:'       │"
echo "  │  QClaw responds in a few seconds.          │"
echo "  │  Type 'exit' or Ctrl+C to quit.            │"
echo "  └───────────────────────────────────────────┘"
echo ""

"$BINARY" direct
