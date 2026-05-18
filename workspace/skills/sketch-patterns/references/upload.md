# Uploading a Sketch — Call the `arduino` Tool

When the user asks you to **compile**, **upload**, **flash**, **run it on the board**, or **put it on the Uno Q**, you **must call the `arduino` tool** with the complete sketch source. Do not just emit the sketch as a markdown code block — that does nothing visible to the user.

## Tool-call shape

```json
{
  "name": "arduino",
  "arguments": {
    "action": "upload",
    "sketch": "<full .ino source — every line, escaped newlines>"
  }
}
```

The `action` must be one of:

| Action | What it does |
|---|---|
| `"compile"` | Verify the sketch compiles. Returns compiler errors verbatim if it fails. No upload. |
| `"upload"` | Compile **and** flash the board. Returns the OpenOCD flash log. **Use this when the user asks to upload / run / flash.** |
| `"detect"` | List connected boards. No sketch needed. |

## What you do NOT need to do

- **Do not** call `read_file`, `list_dir`, or `write_file` first. The `arduino` tool is self-contained — it writes the sketch to a temp directory and handles compilation and flashing internally.
- **Do not** ask the user for the FQBN, the port, or the board's IP address. These are configured at the tool level.
- **Do not** invent a sketch file path. The sketch text goes in the `sketch` parameter directly.

## Success and failure signals

A successful upload returns: `"Sketch compiled and flashed to the board."` followed by the OpenOCD flash log. At that point the LEDs / Serial / hardware on the board are live with the new code.

A failure returns the compiler output verbatim — usually with a clear file:line error. Fix the sketch and call `arduino` again with the corrected source. Two compile failures in a row almost always means the sketch is using an API the Zephyr core does not support.
