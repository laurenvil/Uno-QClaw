---
name: led-matrix
description: Arduino Uno Q built-in 12x8 LED matrix — scroll text, draw frames, play animations using Arduino_LED_Matrix + ArduinoGraphics libraries (bundled with arduino:zephyr core). Read this before writing any sketch that mentions the LED matrix, scrolling text, or drawing pixels.
---

# LED Matrix (Uno Q)

The Arduino Uno Q has a built-in **13-column × 8-row monochrome blue LED matrix** (104 pixels, designators `D27001..D27104`) driven by the STM32U585 MCU. It is exposed through the `Arduino_LED_Matrix` library, which is included with the `arduino:zephyr` core — **no `lib install` step is needed**. Scrolling text additionally uses `ArduinoGraphics`, which is also bundled.

The LEDs are blue and monochrome; the color argument passed to `beginText()` does not change the hue — any non-zero color simply lights the pixel. During the first 20-30 seconds after power-on the boot logo owns the matrix; sketches that try to draw before Linux finishes booting may briefly compete with it.

## When to use

- Display short text (1–20 characters) that scrolls across the matrix.
- Show a static 12×8 frame (icon, bar graph, custom pattern).
- Play a pre-recorded animation sequence.

## Quick rules

1. **Includes go in this order:** `ArduinoGraphics.h` **first**, then `Arduino_LED_Matrix.h`. Reversing them breaks compilation.
2. **Construct the matrix object globally:** `Arduino_LED_Matrix matrix;` at file scope.
3. **Call `matrix.begin()` in `setup()`** before any draw call. Forgetting this leaves the matrix dark.
4. **Wrap text in spaces:** `"   QClaw   "` — without leading/trailing spaces the scroll starts and ends mid-character. The matrix is only 13 columns wide, so a 6-character word at Font_5x7 (~30 columns of pixels) already overflows; the scroll is the point.
5. **`textScrollSpeed()` is in milliseconds per pixel-shift.** 50 ms = fast, 100 ms = comfortable, 200 ms = slow.
6. **Always call `matrix.endText(SCROLL_LEFT)` to terminate a text block.** Without `endText`, nothing draws.

## Reference files

- `references/scroll-text.md` — Canonical template for scrolling text across the matrix (the "QClaw" demo).

## Compile and upload — call the `arduino` tool

When the user asks you to **upload** a sketch (or "run it on the board", "flash it", "put it on the Uno Q"), you **must call the `arduino` tool with `action="upload"`** and the complete sketch source in the `sketch` parameter. Do not just print the sketch in a chat reply — the user wants the LEDs to actually change.

The tool takes care of the FQBN, the port, and the flashing path automatically. You do not need to detect the board, write the sketch to disk first, or read any other files — call `arduino` directly with the sketch you wrote.

**Example tool call** (this is what your `tool_calls` JSON should look like for this skill):

```json
{
  "name": "arduino",
  "arguments": {
    "action": "upload",
    "sketch": "#include \"ArduinoGraphics.h\"\n#include \"Arduino_LED_Matrix.h\"\n\nArduino_LED_Matrix matrix;\n\nvoid setup() {\n    matrix.begin();\n    matrix.textFont(Font_5x7);\n    matrix.textScrollSpeed(100);\n    matrix.clear();\n}\n\nvoid loop() {\n    matrix.beginText(0, 0, 127, 0, 0);\n    matrix.print(\"      QClaw      \");\n    matrix.endText(SCROLL_LEFT);\n    delay(1000);\n}\n"
  }
}
```

A successful upload returns `"Sketch compiled and flashed to the board."` — at which point the LEDs are live. A failed upload returns the compiler errors verbatim; fix the sketch and call `arduino` again. Do not call `read_file` or `list_dir` first — the tool is self-contained.
