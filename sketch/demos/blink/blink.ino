/*
 * blink — the canonical sanity check.
 *
 * No Bridge, no LED matrix. Just toggles the built-in LED on a fixed
 * cadence so you can prove that compilation and upload work before
 * adding anything more interesting.
 *
 * Note: the Uno Q's built-in LED is active-low — LOW = ON, HIGH = OFF.
 */
#include <Arduino.h>

constexpr unsigned long ON_MS  = 500;
constexpr unsigned long OFF_MS = 500;

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);  // start off
}

void loop() {
    digitalWrite(LED_BUILTIN, LOW);   // active-low: LOW = ON
    delay(ON_MS);
    digitalWrite(LED_BUILTIN, HIGH);  // HIGH = OFF
    delay(OFF_MS);
}
