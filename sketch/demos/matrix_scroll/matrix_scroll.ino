/*
 * matrix_scroll — scroll arbitrary text on the LED matrix on demand.
 *
 * Exposes one Bridge provider, `scroll(text)`, that scrolls a string
 * across the 12x8 LED matrix. Returns the length of the string the MCU
 * received so the Python side can confirm the message round-tripped.
 *
 * Python:
 *     from arduino.app_utils import Bridge
 *     Bridge.call("scroll", "Hello from QClaw")
 */
#include <Arduino.h>
#include "Arduino_RouterBridge.h"
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;

int scroll(String text) {
    String padded = String("   ") + text + String("   ");
    matrix.textFont(Font_5x7);
    matrix.textScrollSpeed(80);
    matrix.beginText(0, 0, 127, 0, 0);
    matrix.print(padded.c_str());
    matrix.endText(SCROLL_LEFT);
    return text.length();
}

void setup() {
    matrix.begin();
    scroll(String("Ready"));

    Bridge.begin();
    Bridge.provide("scroll", scroll);
}

void loop() {
    // Bridge providers run on a dedicated thread; loop() stays empty.
}
