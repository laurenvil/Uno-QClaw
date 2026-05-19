#!/usr/bin/env python3
"""QClaw Direct-Server interactive REPL — pre-router + direct API, no agent loop, no tools.

Mirrors the Direct evaluation architecture (eval_v8_direct_preroute.py) but in
an interactive chat form for deployment use.

Pre-router coverage (23 rules across 15 skills, kept in sync with
pkg/agent/skill_preload.go):
  Sketch-side (MCU):
    - sketch-patterns: breathe, blink, button, pot, servo, sketch/setup()/loop(),
      compile/upload, CAN bus, DAC, OpAmp
    - led-matrix: scroll text / draw frames on the 13×8 blue matrix
  Hardware reference:
    - uno-q-hardware: pinout, voltage safety, connectors, power
  Dual-chip workflow:
    - bridge: Python (MPU) ↔ sketch (MCU) RPC
    - arduino-app-lab: App + Brick workflow
  Linux-side capabilities:
    - wireless: Wi-Fi / Bluetooth / Bridge-to-network pattern
    - vision: MIPI-CSI-2 camera, V4L2, GStreamer, OpenCV
    - audio: Mic2 / Headphone / LineOut, ALSA, voice recognition
    - linux-led: sysfs LED control (MPU-side RGB LEDs from Python)
  Plug-and-play sensors:
    - modulino: Qwiic-attached Modulino sensors

Use this path when:
  - The user is asking factual / conceptual questions
    ("Which pins on the Uno Q can do PWM?", "Can I connect a 5V sensor to A0?",
     "How does Bridge work?", "What is a Modulino?")
  - You want fast responses (~5–12 min on 0.8B for full sketch, ~5 min for short answers)
  - You don't need to perform actions (compile/upload, camera capture, LED control,
    I²C scan) from inside the chat

For compile / upload / camera / LED / I²C workflows, use the agentic path
instead: `make qclaw` (or `make qclaw-agentic`), which exposes 8 narrow tools
(read_file, write_file, list_dir, arduino, camera, sysfs_led, network,
i2cdetect).

Reads SOUL.md from the workspace and applies the same pre-router rules as the
Go agent loop (pkg/agent/skill_preload.go) to inject relevant skill content
into the system prompt before each call. No tools, no multi-iteration loop —
each user message is a single LLM call that returns the final answer.

Requires llama-server running at 127.0.0.1:8080 (started automatically by
scripts/qclaw-launch-direct.sh).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ----- config -----

QCLAW_HOME = Path(os.environ.get("QCLAW_HOME", str(Path.home() / ".qclaw")))
WORKSPACE = QCLAW_HOME / "workspace"
SOUL_PATH = WORKSPACE / "SOUL.md"
SKILLS_DIR = WORKSPACE / "skills"

LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"
LLAMA_MODELS = "http://127.0.0.1:8080/v1/models"

DEFAULT_TEMP = float(os.environ.get("QCLAW_TEMP", "0.3"))
MAX_TOKENS = int(os.environ.get("QCLAW_MAX_TOKENS", "2048"))
REQUEST_TIMEOUT_SECS = int(os.environ.get("QCLAW_REQUEST_TIMEOUT", "1800"))

# ----- pre-router (ports pkg/agent/skill_preload.go rules) -----

PRELOAD_RULES = [
    (re.compile(r"\b(breathe|breathing|breath|fade|fading|fades|dim|dimming)\b", re.I),
     "sketch-patterns", ["breathing.md"]),
    (re.compile(r"\b(blink|blinks|blinking|flash|flashes|flashing)\b", re.I),
     "sketch-patterns", ["blink.md"]),
    (re.compile(r"\b(button|buttons|switch|switches|press|pressed|pressing|INPUT_PULLUP)\b", re.I),
     "sketch-patterns", ["button.md"]),
    (re.compile(r"(\b(pot|potentiometer|dial|knob|analogRead)\b|Serial\s*Monitor|Serial\.print)", re.I),
     "sketch-patterns", ["potentiometer.md"]),
    (re.compile(r"\b(servo|servos|sweep|sweeping)\b", re.I),
     "sketch-patterns", ["servo.md"]),
    (re.compile(r"(\bpin\b|\bpins\b|\b[DA]\d{1,2}\b|\bPWM\b|\banalogWrite\b|\bpinMode\b|\bdigitalWrite\b|\bdigitalRead\b)", re.I),
     "uno-q-hardware", ["pinout.md"]),
    (re.compile(r"\b(3\.?3\s?V|5\s?V|voltage|ADC|safe to connect|safe to use|damage|damages|fry|fries|burn|burns|short)\b", re.I),
     "uno-q-hardware", ["voltage-safety.md"]),
    (re.compile(r"\b(MPU|MCU|Linux\s+side|Arduino\s+side|STM32|STM32U585|Cortex-A53|Cortex-M33|QRB2210|RPC\s+Bridge|two\s+processors)\b", re.I),
     "uno-q-hardware", []),
    (re.compile(r"(\b(sketch|sketches|\.ino|setup\(\)|loop\(\)|Zephyr|FQBN)\b|write a (program|sketch))", re.I),
     "sketch-patterns", []),
    (re.compile(
        r"(\b(LED[\s-]?matrix|LED_Matrix|Arduino_LED_Matrix|ArduinoGraphics)\b|"
        r"\b(scroll|scrolls|scrolling|marquee)\b|"
        r"\bmatrix\b.*\b(text|display|show|scroll|draw)\b|"
        r"\b(text|display|show|scroll|draw)\b.*\bmatrix\b)", re.I),
     "led-matrix", ["scroll-text.md"]),
    (re.compile(
        r"\b(compile|compiles|compiling|upload|uploads|uploading|flash|flashes|flashing|"
        r"build the sketch|run it on the board|put it on the board|arduino-cli|"
        r"run on (the )?(uno q|board))\b", re.I),
     "sketch-patterns", ["upload.md"]),
]


def load_skill(name: str) -> str | None:
    p = SKILLS_DIR / name / "SKILL.md"
    return p.read_text() if p.is_file() else None


def load_reference(name: str, ref: str) -> str | None:
    p = SKILLS_DIR / name / "references" / ref
    return p.read_text() if p.is_file() else None


def preload_for_message(message: str) -> tuple[str, list[str]]:
    if not message.strip():
        return "", []
    loaded_skill: set[str] = set()
    loaded_ref: set[str] = set()
    sections: list[str] = []
    fired: list[str] = []
    for pattern, skill, refs in PRELOAD_RULES:
        if not pattern.search(message):
            continue
        if skill not in loaded_skill:
            content = load_skill(skill)
            if content is not None:
                sections.append(f"## {skill}/SKILL.md\n\n{content.strip()}")
                loaded_skill.add(skill)
                fired.append(skill)
        for ref in refs:
            key = f"{skill}/{ref}"
            if key in loaded_ref:
                continue
            content = load_reference(skill, ref)
            if content is not None:
                sections.append(f"## {skill}/references/{ref}\n\n{content.strip()}")
                loaded_ref.add(key)
                fired.append(key)
    if not sections:
        return "", []
    loaded_paths = [f"skills/{f}" if "/" in f else f"skills/{f}/SKILL.md" for f in fired]
    preamble = (
        "# Auto-loaded References (DO NOT call read_file on these)\n\n"
        "The full content of the following files is already shown verbatim below. "
        "They have already been read for you:\n\n"
    )
    for p in loaded_paths:
        preamble += f"  - `{p}`\n"
    preamble += (
        "\nSTOP — do not invoke `read_file` for any path in the list above. "
        "Use the content shown below directly. When a canonical sketch template appears, "
        "copy it byte-for-byte and change only the pin number / value the user requested."
    )
    return preamble + "\n\n" + "\n\n---\n\n".join(sections), fired


def build_system_prompt(prompt: str) -> tuple[str, list[str]]:
    soul = SOUL_PATH.read_text() if SOUL_PATH.is_file() else ""
    preload_block, fired = preload_for_message(prompt)
    if preload_block:
        return f"{soul}\n\n---\n\n{preload_block}", fired
    return soul, fired


# ----- llama-server call -----

def server_model_id() -> str | None:
    try:
        with urllib.request.urlopen(LLAMA_MODELS, timeout=3) as r:
            data = json.loads(r.read().decode())
        for m in data.get("data", []):
            return m.get("id")
    except Exception:
        return None
    return None


def post_completion(model: str, system_prompt: str, user_message: str) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": DEFAULT_TEMP,
        "max_tokens": MAX_TOKENS,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        LLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECS) as resp:
        return json.loads(resp.read().decode())


# ----- REPL -----

BANNER = """
  ┌───────────────────────────────────────────────┐
  │  🧘  S E N S A I — Direct Server               │
  │      Arduino Q&A Assistant (fast path)         │
  │                                                │
  │  Pre-router + direct API · no tools · no loop  │
  │  Best for: pinouts, voltage, concepts,         │
  │            short sketches you'll flash by hand │
  │                                                │
  │  For 'compile and upload' workflows, exit and  │
  │  run `make qclaw-agentic` instead.            │
  │                                                │
  │  Type 'exit' or Ctrl+C to quit.                │
  └───────────────────────────────────────────────┘
"""


def main() -> int:
    if not SOUL_PATH.is_file():
        print(f"Error: SOUL.md not found at {SOUL_PATH}", file=sys.stderr)
        print("Run: make qclaw-setup", file=sys.stderr)
        return 2
    model = server_model_id()
    if model is None:
        print("Error: llama-server not reachable at 127.0.0.1:8080", file=sys.stderr)
        print("Start it with: make qclaw-direct  (or start qclaw-launch-direct.sh)", file=sys.stderr)
        return 2

    print(BANNER)
    print(f"QClaw is ready — model: {model}  (temp={DEFAULT_TEMP})")
    print(f"Pre-router: 11 rules · workspace: {WORKSPACE}")
    print()

    while True:
        try:
            line = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0
        if not line:
            continue
        if line.lower() in {"exit", "quit", ":q"}:
            print("Bye.")
            return 0

        system_prompt, fired = build_system_prompt(line)
        t0 = time.time()
        if fired:
            print(f"  [pre-router fired: {', '.join(fired)}]", flush=True)
        print("  Thinking...", end="", flush=True)
        try:
            resp = post_completion(model, system_prompt, line)
        except urllib.error.URLError as exc:
            print(f"\nError: {exc}", file=sys.stderr)
            continue
        wall = time.time() - t0
        choice = resp.get("choices", [{}])[0]
        msg = choice.get("message", {})
        finish = choice.get("finish_reason", "")
        content = msg.get("content") or ""
        print(f" done ({wall:.1f}s, finish={finish})\n")
        print(f"QClaw: {content}\n")


if __name__ == "__main__":
    sys.exit(main())
