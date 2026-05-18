# CAN bus (FDCAN1) on the Uno Q

The STM32U585 has a Flexible Data-rate CAN controller (**FDCAN1**) exposed on the JDIGITAL header. Use it for automotive/industrial buses (OBD-II adapters, motor controllers, BMS modules).

| Signal | Arduino pin | STM32 pin | JDIGITAL pin |
|---|---|---|---|
| FDCAN1_TX | D4 | PA12 | 5 |
| FDCAN1_RX | D5 | PA11 | 6 |

**You need an external transceiver.** The STM32 outputs CMOS-level CAN_TX/CAN_RX (3.3 V logic); the actual CAN bus uses differential signaling (CAN_H / CAN_L). Wire D4 and D5 to a 3.3 V-tolerant transceiver chip (TJA1051T/3, MCP2562FD, SN65HVD230) and put the CAN_H / CAN_L pair on the bus.

```
STM32U585          TJA1051T/3            CAN bus
  PA12 ──TX────►  TXD            CANH ───►
  PA11 ◄──RX────  RXD            CANL ───►
                  3V3
                  STBY ──► GND (always-on mode)
                  GND
```

Add a 120 Ω terminator at each end of the physical bus.

## Canonical sketch — receive frames at 500 kbit/s

```cpp
// Runs on the STM32U585 MCU
// Requires the `STM32_CAN` library (or `arduino-CAN` with FDCAN support);
// the standard Arduino library wraps the STM32 HAL FDCAN driver.
#include <STM32_CAN.h>

STM32_CAN Can1(CAN1, ALT);   // FDCAN1 on PA11/PA12

void setup() {
    Serial.begin(115200);
    while (!Serial) {}

    Can1.begin();
    Can1.setBaudRate(500000);
    Serial.println("CAN ready @ 500 kbit/s");
}

void loop() {
    CAN_message_t msg;
    if (Can1.read(msg)) {
        Serial.print("ID 0x");
        Serial.print(msg.id, HEX);
        Serial.print(" len ");
        Serial.print(msg.len);
        Serial.print(" data");
        for (int i = 0; i < msg.len; i++) {
            Serial.print(" ");
            Serial.print(msg.buf[i], HEX);
        }
        Serial.println();
    }
}
```

## Canonical sketch — transmit a frame

```cpp
#include <STM32_CAN.h>

STM32_CAN Can1(CAN1, ALT);

void setup() {
    Can1.begin();
    Can1.setBaudRate(500000);
}

void loop() {
    CAN_message_t msg;
    msg.id = 0x123;
    msg.len = 4;
    msg.buf[0] = 0xDE;
    msg.buf[1] = 0xAD;
    msg.buf[2] = 0xBE;
    msg.buf[3] = 0xEF;
    Can1.write(msg);
    delay(1000);
}
```

## Common bus speeds

| Application | Speed |
|---|---|
| OBD-II (automotive diagnostics) | 500 kbit/s |
| CANopen industrial | 125 / 250 / 500 / 1000 kbit/s |
| J1939 (trucks) | 250 kbit/s |
| CAN-FD (data phase) | up to 5 Mbit/s |

## Pitfalls

- **Skipping the transceiver.** Wiring D4/D5 directly to a CAN bus will not work and may damage the STM32 if the bus is energized. The differential pair needs a transceiver IC.
- **Wrong bus speed.** CAN is unforgiving — if the speed is wrong, every frame errors out. Confirm the bus speed with the device documentation before sending traffic.
- **No termination.** Without 120 Ω terminators at each end, the bus reflects and frames corrupt. Many transceiver modules include a switchable terminator.
- **Sharing CAN with USART1.** D0 (PB7) and D1 (PB6) are USART1 RX/TX. CAN_TX/CAN_RX are on D4/D5 — independent — but PA12 (D4) is ALSO USB DP on some packages. The Uno Q's PA12 is wired to D4 for CAN, but be careful if you migrate code from a different STM32 board.

## See also

- `uno-q-hardware/references/pinout.md` — full JDIGITAL pinout including FDCAN1.
- `upload.md` — how to flash this sketch to the board.
