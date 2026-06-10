# QClaw Sketch Demos

Standalone Arduino sketches for the Uno Q (STM32U585 MCU). Each demo lives in
its own folder per Arduino convention — the folder name must match the `.ino`
file basename.

Compile and flash from the QClaw agent (`"compile and flash this sketch"`),
the `qclaw` CLI, or the Arduino App Lab sketch tab.

## Demos

| Folder | What it shows |
|---|---|
| `blink/` | Pure MCU `digitalWrite()` blink — no RPC, no Bridge |
| `bridge_echo/` | RPC service that echoes any integer back to Python |
| `matrix_scroll/` | RPC service that scrolls arbitrary text on the LED matrix |

## Compiling

```bash
# Via QClaw CLI (uses arduino-cli underneath):
qclaw agent "compile and upload sketch/demos/blink/blink.ino"

# Or directly:
arduino-cli compile --fqbn arduino:zephyr:unoq sketch/demos/blink
arduino-cli upload  --fqbn arduino:zephyr:unoq --port 192.168.1.168 \
    --protocol network sketch/demos/blink
```

## Symlink behaviour

After `python/main.py` bootstraps once, `~/.qclaw/workspace/sketches/` is a
symlink to this directory. The QClaw agent's `arduino` tool can therefore
edit, compile and flash demos via the workspace path:

```
~/.qclaw/workspace/sketches/demos/blink/blink.ino
```

is the same file as

```
<app>/sketch/demos/blink/blink.ino
```
