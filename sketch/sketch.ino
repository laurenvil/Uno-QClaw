/*
 * QClaw — Arduino App Lab Bridge Sketch (v2.1.2)
 *
 * Runs on the Uno Q's STM32U585 MCU. Provides three Bridge services that
 * the Python side calls via arduino.app_utils.Bridge.call():
 *
 *   ping()              → returns 1   (health check)
 *   flash_led(times)    → flashes the built-in LED `times` times
 *   scroll(text)        → scrolls text across the 12x8 LED matrix
 *
 * LED behaviour: the Uno Q's built-in LED is active-low — digitalWrite(LOW)
 * turns it ON, digitalWrite(HIGH) turns it OFF.
 *
 * The real on-device AI work happens in python/main.py via the qclaw
 * gateway subprocess; this sketch is the bridge between the agent and
 * any sketch-side hardware it needs to drive.
 */
#include <Arduino.h>
#include "Arduino_RouterBridge.h"
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;

// ── Bridge providers ────────────────────────────────────────────────────────

int ping() {
    return 1;
}

int flash_led(int times) {
    if (times < 1) times = 1;
    if (times > 100) times = 100;
    for (int i = 0; i < times; i++) {
        digitalWrite(LED_BUILTIN, LOW);   // active-low: LOW = ON
        delay(150);
        digitalWrite(LED_BUILTIN, HIGH);  // HIGH = OFF
        delay(150);
    }
    return times;
}

int scroll(String text) {
    String padded = String("   ") + text + String("   ");
    matrix.textFont(Font_5x7);
    matrix.textScrollSpeed(80);
    matrix.beginText(0, 0, 127, 0, 0);
    matrix.print(padded.c_str());
    matrix.endText(SCROLL_LEFT);
    return text.length();
}

// ── Setup & loop ────────────────────────────────────────────────────────────

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);  // start with LED off

    matrix.begin();
    scroll(String("QClaw"));

    Bridge.begin();
    Bridge.provide("ping", ping);
    Bridge.provide("flash_led", flash_led);
    Bridge.provide("scroll", scroll);

    flash_led(3);   // boot signature: 3 LED flashes
}

void loop() {
    // Bridge providers run on a dedicated thread; loop() stays empty.
}
