#!/usr/bin/env bash
# qclaw-launch-direct.sh — DISABLED in the QClaw-Client branch.
#
# The direct path was a Python HTTP client (qclaw-direct-chat.py) that talked
# to a long-running llama-server. The llama-cli provider this branch uses
# spawns a one-shot mpu/llama-cli subprocess per Chat() instead — there is no
# HTTP endpoint for the Python client to call.
#
# Use the agentic path:
#   make qclaw-agentic
#
# Re-enabling direct mode under the CLI provider would require porting the
# Python pre-router + chat loop to call the same Go provider (or shelling out
# to a small qclaw-direct subcommand). Tracked as a follow-up.
set -euo pipefail

cat >&2 <<'EOF'
qclaw-direct is not available in the QClaw-Client branch.

This branch uses the llama-cli provider (pkg/providers/llamacli), which spawns
mpu/llama-cli per Chat() call instead of running a persistent llama-server.
The direct path was an HTTP client tied to the server, so it has no endpoint
to talk to here.

Run the agentic path instead:
  make qclaw-agentic
EOF
exit 2
