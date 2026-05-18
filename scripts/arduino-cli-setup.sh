#!/usr/bin/env bash
# arduino-cli-setup.sh — Install arduino-cli and the Arduino Uno Q board core.
# Idempotent: safe to run multiple times. Skips steps already done.
set -euo pipefail

ARDUINO_CLI_VERSION="${ARDUINO_CLI_VERSION:-latest}"
INSTALL_DIR="${HOME}/.local/bin"
ARDUINO_CLI_BIN="${INSTALL_DIR}/arduino-cli"
UNO_Q_CORE="arduino:zephyr"
UNO_Q_FQBN="arduino:zephyr:unoq"

# Colours (safe — only used when stdout is a terminal)
if [ -t 1 ]; then
    BOLD="\033[1m"
    DIM="\033[2m"
    GREEN="\033[32m"
    YELLOW="\033[33m"
    CYAN="\033[36m"
    RED="\033[31m"
    RESET="\033[0m"
else
    BOLD="" DIM="" GREEN="" YELLOW="" CYAN="" RED="" RESET=""
fi

hr() { printf '%s\n' "────────────────────────────────────────────────────"; }

echo ""
echo -e "${BOLD}  Arduino CLI Setup${RESET}"
echo -e "${DIM}  Compile and upload sketches from QClaw${RESET}"
hr
echo ""

# ── Guard: Linux only ─────────────────────────────────────────────────────────

if [ "$(uname -s)" != "Linux" ]; then
    echo -e "${YELLOW}Skipping arduino-cli setup — only needed on the Arduino Uno Q (Linux).${RESET}"
    echo ""
    exit 0
fi

# ── Step 1: Check / install arduino-cli ──────────────────────────────────────

echo -e "${BOLD}[1/3] arduino-cli${RESET}"

ARDUINO_CLI_PATH=""
if command -v arduino-cli > /dev/null 2>&1; then
    ARDUINO_CLI_PATH="$(command -v arduino-cli)"
elif [ -x "$ARDUINO_CLI_BIN" ]; then
    ARDUINO_CLI_PATH="$ARDUINO_CLI_BIN"
fi

if [ -n "$ARDUINO_CLI_PATH" ]; then
    CLI_VER=$("$ARDUINO_CLI_PATH" version 2>/dev/null | head -1 || echo "unknown")
    echo -e "  ${GREEN}Found:${RESET} $ARDUINO_CLI_PATH"
    echo -e "  ${DIM}$CLI_VER${RESET}"
else
    echo "  Not found — downloading arduino-cli..."
    mkdir -p "$INSTALL_DIR"

    if command -v curl > /dev/null 2>&1; then
        curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
            | BINDIR="$INSTALL_DIR" sh
    elif command -v wget > /dev/null 2>&1; then
        wget -qO- https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
            | BINDIR="$INSTALL_DIR" sh
    else
        echo -e "  ${RED}Error: neither curl nor wget is available.${RESET}"
        echo "  Install one and re-run: make qclaw-arduino-setup"
        exit 1
    fi

    ARDUINO_CLI_PATH="$ARDUINO_CLI_BIN"

    # Ensure install dir is in PATH for subsequent commands in this session
    export PATH="$INSTALL_DIR:$PATH"

    CLI_VER=$("$ARDUINO_CLI_PATH" version 2>/dev/null | head -1 || echo "unknown")
    echo -e "  ${GREEN}Installed:${RESET} $ARDUINO_CLI_PATH"
    echo -e "  ${DIM}$CLI_VER${RESET}"

    # Persist to shell profile if not already there
    for PROFILE in "$HOME/.bashrc" "$HOME/.profile"; do
        if [ -f "$PROFILE" ] && ! grep -q "$INSTALL_DIR" "$PROFILE" 2>/dev/null; then
            echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$PROFILE"
            echo -e "  ${DIM}Added $INSTALL_DIR to PATH in $PROFILE${RESET}"
        fi
    done
fi
echo ""

# ── Step 2: Update core index ─────────────────────────────────────────────────

echo -e "${BOLD}[2/3] Updating board core index${RESET}"
"$ARDUINO_CLI_PATH" core update-index 2>&1 | tail -3 | sed 's/^/  /'
echo ""

# ── Step 3: Install arduino:zephyr core ───────────────────────────────────────

echo -e "${BOLD}[3/3] Arduino Uno Q board core (${UNO_Q_CORE})${RESET}"

if "$ARDUINO_CLI_PATH" core list 2>/dev/null | grep -q "^${UNO_Q_CORE}"; then
    CORE_VER=$("$ARDUINO_CLI_PATH" core list 2>/dev/null | grep "^${UNO_Q_CORE}" | awk '{print $2}')
    echo -e "  ${GREEN}Installed:${RESET} ${UNO_Q_CORE} @ ${CORE_VER}"
else
    echo "  Installing ${UNO_Q_CORE} core..."
    "$ARDUINO_CLI_PATH" core install "$UNO_Q_CORE" 2>&1 | tail -5 | sed 's/^/  /'
    echo -e "  ${GREEN}Done.${RESET}"
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────

hr
echo ""
echo -e "${GREEN}${BOLD}Arduino CLI ready.${RESET}"
echo ""
echo -e "  Board FQBN:  ${CYAN}${UNO_Q_FQBN}${RESET}"
echo "  Detect boards with:  arduino-cli board list"
echo "  QClaw will compile and upload sketches automatically."
echo ""
echo -e "${DIM}  If 'arduino-cli' is not found in a new terminal, run:${RESET}"
echo -e "  ${DIM}  source ~/.bashrc${RESET}"
echo ""
