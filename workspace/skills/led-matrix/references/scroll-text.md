# Scrolling Text on the Uno Q LED Matrix

This is the canonical template, copied from the `Arduino_LED_Matrix/examples/Basic/Basic.ino` example bundled with `arduino:zephyr` 0.54.1 and adapted to a custom string. Copy it byte-for-byte and change only the string between the double-quotes in `matrix.print(...)`.

## Template

```cpp
#include "ArduinoGraphics.h"
#include "Arduino_LED_Matrix.h"

Arduino_LED_Matrix matrix;

void setup() {
    matrix.begin();
    matrix.textFont(Font_5x7);
    matrix.textScrollSpeed(100);
    matrix.clear();
}

void loop() {
    matrix.beginText(0, 0, 127, 0, 0);   // x, y, R, G, B — five-arg form (the matrix is monochrome blue; any non-zero color works, but the bundled example uses 127, 0, 0)
    matrix.print("      QClaw      ");
    matrix.endText(SCROLL_LEFT);
    delay(1000);
}
```

## What each line does

| Line | Purpose |
|---|---|
| `#include "ArduinoGraphics.h"` | Provides `print()`, `beginText()`, `endText()` on top of any framebuffer. **Must come before** `Arduino_LED_Matrix.h`. |
| `#include "Arduino_LED_Matrix.h"` | The 12×8 matrix driver itself. |
| `Arduino_LED_Matrix matrix;` | Global instance — there is only one matrix per board. |
| `matrix.begin()` | Initializes the hardware. Forgetting this leaves the matrix dark. |
| `matrix.textFont(Font_5x7)` | Selects the 5×7 pixel font. The only built-in font that fits 8 rows. |
| `matrix.textScrollSpeed(100)` | Milliseconds between pixel-shifts. 50 = fast, 100 = comfortable, 200 = slow. |
| `matrix.beginText(0, 0, 127, 0, 0)` | Start a text block at column 0, row 0, with color R=127, G=0, B=0. Five-arg form. The matrix is monochrome blue — the RGB values do not change the hue, but the bundled `Basic.ino` example uses these values and matches the library's reference behaviour. |
| `matrix.print("      QClaw      ")` | The text. **Pad with spaces** — without them the scroll starts and ends mid-character. The matrix is 13 columns wide and `QClaw` is ~30 columns of pixels at Font_5x7, so padding is what makes the scroll readable. |
| `matrix.endText(SCROLL_LEFT)` | Terminates the text block and triggers the scroll-left animation. Other options: `SCROLL_RIGHT`, `NO_SCROLL`. |
| `delay(500)` | Pause between scrolls (half a second). |

## Pitfalls

- **Wrong include order** → `'ArduinoLEDMatrix' was not declared` compile error. Put `ArduinoGraphics.h` first.
- **Missing `matrix.begin()`** → sketch compiles, board boots, matrix stays dark.
- **Missing `endText()`** → text never draws; loop runs forever doing nothing.
- **No padding spaces** → first/last letter appears clipped at the edges.
- **`Font_4x6` for short strings** is tempting but renders unreadable on the 8-row matrix. Stick with `Font_5x7`.

## FQBN and upload

The sketch compiles for `arduino:zephyr:unoq`. To upload from the Uno Q itself, the `arduino` tool's `upload` action handles compile + flash in one step. Internally it compiles with `--export-binaries` and then invokes OpenOCD via linuxgpiod at the canonical sketch partition address (`0x8100000`) — no SSH, no network credentials. Plain compile errors come back verbatim; flash errors include the OpenOCD log.

## Common mistake — flashing the wrong address

The pre-installed `/usr/local/bin/arduino-flash` wrapper hardcodes `0x80F0000`, which lands in a reserved area near the end of bank 1 and **never runs**. Do not invoke `arduino-flash` directly for sketches — let the `arduino` tool handle it, which uses the correct `0x8100000` address from the board's `boards.txt`.
