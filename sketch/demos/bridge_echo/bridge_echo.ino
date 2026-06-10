/*
 * bridge_echo — minimal Bridge service.
 *
 * Exposes an "echo" Bridge provider that returns whatever integer Python
 * passed in. Pair it with:
 *
 *     from arduino.app_utils import Bridge
 *     assert Bridge.call("echo", 42) == 42
 *
 * Useful for verifying round-trip latency and the wire protocol after a
 * sketch change.
 *
 * The Uno Q's built-in LED is active-low — LOW = ON, HIGH = OFF.
 */
#include <Arduino.h>
#include "Arduino_RouterBridge.h"

int echo(int value) {
    return value;
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);  // start off

    Bridge.begin();
    Bridge.provide("echo", echo);
}

void loop() {
    // Heartbeat — single short blink every 2 s while waiting for Bridge calls.
    digitalWrite(LED_BUILTIN, LOW);   // ON
    delay(50);
    digitalWrite(LED_BUILTIN, HIGH);  // OFF
    delay(1950);
}
