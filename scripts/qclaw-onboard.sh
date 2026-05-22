#!/usr/bin/env bash
# qclaw-onboard.sh — First-run setup for QClaw on Arduino Uno Q.
# Patches only the QClaw-relevant fields in config.json (token, allow_from).
# Never calls 'qclaw onboard' — that would overwrite our tuned config.
set -euo pipefail

QCLAW_HOME="${QCLAW_HOME:-$HOME/.qclaw}"
CONFIG="$QCLAW_HOME/config.json"
QCLAW_MODEL="${QCLAW_MODEL:-$HOME/models/Qwen_Qwen3.5-0.8B-Q4_0.gguf}"
LLAMA_CLI="${LLAMA_CLI:-./engines/llamacli/mpu/llama-cli}"

# Colours (safe — only used when stdout is a terminal)
if [ -t 1 ]; then
    BOLD="\033[1m"
    DIM="\033[2m"
    GREEN="\033[32m"
    YELLOW="\033[33m"
    CYAN="\033[36m"
    RESET="\033[0m"
else
    BOLD="" DIM="" GREEN="" YELLOW="" CYAN="" RESET=""
fi

hr() { printf '%s\n' "────────────────────────────────────────────────────"; }

echo ""
echo -e "${BOLD}  QClaw — Arduino AI Assistant  ${RESET}"
echo -e "${DIM}  First-run setup for Arduino Uno Q${RESET}"
hr
echo ""

# ── Check config exists (qclaw-setup must have run first) ────────────────────

if [ ! -f "$CONFIG" ]; then
    echo -e "${YELLOW}Config not found. Running qclaw-setup first...${RESET}"
    make qclaw-setup
    echo ""
fi

# ── Model check ───────────────────────────────────────────────────────────────

echo -e "${BOLD}[1/4] Checking model...${RESET}"
if [ -f "$QCLAW_MODEL" ]; then
    SIZE=$(du -sh "$QCLAW_MODEL" 2>/dev/null | cut -f1)
    echo -e "  ${GREEN}Found:${RESET} $(basename "$QCLAW_MODEL") (${SIZE})"
else
    echo -e "  ${YELLOW}Model not found at: $QCLAW_MODEL${RESET}"
    echo ""
    echo "  Download it now with:"
    echo -e "  ${CYAN}  mkdir -p ~/models"
    echo -e "  ${CYAN}  wget -O $QCLAW_MODEL \\"
    echo -e "  ${CYAN}    'https://huggingface.co/Qwen/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_0.gguf'${RESET}"
    echo ""
    echo "  (You can still continue setup — download the model before running 'make qclaw')"
fi
echo ""

# ── llama-cli check ───────────────────────────────────────────────────────────

echo -e "${BOLD}[2/4] Checking llama-cli (inference engine)...${RESET}"
if [ -x "$LLAMA_CLI" ]; then
    echo -e "  ${GREEN}Found:${RESET} $LLAMA_CLI"
else
    echo -e "  ${YELLOW}llama-cli not found at: $LLAMA_CLI${RESET}"
    echo ""
    echo "  Initialize the engines/llamacli submodule:"
    echo -e "  ${CYAN}  git submodule update --init --recursive engines/llamacli${RESET}"
    echo ""
    echo "  (You can still continue setup — fetch the submodule before running 'make qclaw')"
fi
echo ""

# ── arduino-cli check ─────────────────────────────────────────────────────────

echo -e "${BOLD}[3/4] Checking arduino-cli...${RESET}"
ARDUINO_CLI_PATH=""
if command -v arduino-cli > /dev/null 2>&1; then
    ARDUINO_CLI_PATH="$(command -v arduino-cli)"
elif [ -x "$HOME/.local/bin/arduino-cli" ]; then
    ARDUINO_CLI_PATH="$HOME/.local/bin/arduino-cli"
fi

if [ -n "$ARDUINO_CLI_PATH" ]; then
    CLI_VER=$("$ARDUINO_CLI_PATH" version 2>/dev/null | head -1 || echo "unknown")
    echo -e "  ${GREEN}Found:${RESET} $ARDUINO_CLI_PATH"
    echo -e "  ${DIM}$CLI_VER${RESET}"
    # Check for the Uno Q core
    if "$ARDUINO_CLI_PATH" core list 2>/dev/null | grep -q "^arduino:zephyr"; then
        CORE_VER=$("$ARDUINO_CLI_PATH" core list 2>/dev/null | grep "^arduino:zephyr" | awk '{print $2}')
        echo -e "  ${GREEN}Core installed:${RESET} arduino:zephyr @ ${CORE_VER}"
    else
        echo -e "  ${YELLOW}arduino:zephyr core not installed${RESET}"
        echo -e "  Run: ${CYAN}make qclaw-arduino-setup${RESET}"
    fi
else
    echo -e "  ${YELLOW}arduino-cli not found${RESET}"
    echo -e "  Run: ${CYAN}make qclaw-arduino-setup${RESET} to install it"
    echo "  (QClaw will still work — sketch compilation/upload will not be available)"
fi
echo ""

# ── Telegram token ────────────────────────────────────────────────────────────

echo -e "${BOLD}[4/4] Telegram bot setup (optional — press Enter to skip)${RESET}"
echo ""
echo -e "  QClaw works as a ${BOLD}terminal chat assistant${RESET} without Telegram."
echo "  Add a bot token to also reach QClaw from any phone via Telegram."
echo ""
echo -e "  To get a token: message ${CYAN}@BotFather${RESET} on Telegram → /newbot"
echo ""

# Read current token from config
CURRENT_TOKEN=$(python3 -c "
import json, sys
try:
    c = json.load(open('$CONFIG'))
    print(c.get('channels', {}).get('telegram', {}).get('token', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")

if [ -n "$CURRENT_TOKEN" ] && [ "$CURRENT_TOKEN" != "YOUR_TELEGRAM_BOT_TOKEN" ]; then
    echo -e "  Current token: ${DIM}${CURRENT_TOKEN:0:8}...${RESET} (already set)"
    printf "  Enter new token to replace, or press Enter to keep it: "
else
    printf "  Telegram bot token [press Enter to skip and use terminal only]: "
fi

read -r TOKEN_INPUT
TOKEN_INPUT=$(echo "$TOKEN_INPUT" | tr -d '[:space:]')

if [ -n "$TOKEN_INPUT" ]; then
    echo ""
    echo "  Who can message this bot?"
    echo "  Enter Telegram user IDs separated by commas (e.g. 123456789,987654321)"
    echo -e "  Or press Enter to ${BOLD}allow anyone${RESET} (fine for a deployment on a local network)"
    printf "  Allow from: "
    read -r ALLOW_INPUT
    ALLOW_INPUT=$(echo "$ALLOW_INPUT" | tr -d '[:space:]')

    # Build the allow_from JSON array
    if [ -z "$ALLOW_INPUT" ]; then
        ALLOW_JSON="[]"
    else
        # Convert comma-separated IDs to JSON array of strings
        ALLOW_JSON=$(python3 -c "
import sys
ids = [x.strip() for x in '$ALLOW_INPUT'.split(',') if x.strip()]
print('[' + ', '.join('\"' + i + '\"' for i in ids) + ']')
")
    fi

    # Patch token and allow_from into config.json
    python3 - <<PYEOF
import json, os, sys

path = '$CONFIG'
with open(path) as f:
    cfg = json.load(f)

cfg.setdefault('channels', {}).setdefault('telegram', {})
cfg['channels']['telegram']['token'] = '$TOKEN_INPUT'
cfg['channels']['telegram']['enabled'] = True
cfg['channels']['telegram']['allow_from'] = json.loads('$ALLOW_JSON')

with open(path, 'w') as f:
    json.dump(cfg, f, indent=2)

print("  Config updated: " + path)
PYEOF

    echo -e "  ${GREEN}Telegram configured.${RESET}"
else
    echo -e "  ${DIM}Skipped — QClaw will run as terminal-only.${RESET}"
    echo "  Run 'make qclaw-onboard' at any time to add Telegram later."
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
hr
echo ""
echo -e "${GREEN}${BOLD}QClaw is ready.${RESET}"
echo ""
echo "  Start QClaw:     make qclaw"
if [ -x "$LLAMA_CLI" ] && [ ! -f "$QCLAW_MODEL" ]; then
    echo -e "  ${YELLOW}Remember to download the model before launching.${RESET}"
fi
if [ -z "$ARDUINO_CLI_PATH" ]; then
    echo -e "  ${YELLOW}arduino-cli not installed — run: make qclaw-arduino-setup${RESET}"
fi
echo ""
