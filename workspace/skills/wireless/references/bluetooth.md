# Bluetooth on the Uno Q

The WCN3980 module exposes **Bluetooth 5.1** to the Linux MPU side. Bluetooth on the Uno Q is a Linux feature — same as Wi-Fi, the MCU has no Bluetooth radio. All Bluetooth I/O happens in Python (or other Linux programs) and reaches the sketch through Bridge.

## Bluetooth Classic vs BLE

| | Bluetooth Classic | Bluetooth Low Energy (BLE) |
|---|---|---|
| Use case | Audio, file transfer, serial-port profile | Sensors, beacons, phone connectivity |
| Throughput | Higher (~2 Mbps) | Lower (~1 Mbps practical) |
| Power | Higher | Much lower |
| Standard on phones | Yes | Yes |
| Recommended for user projects | Rarely | Usually |

For most "phone talks to board" use cases, use BLE.

## Software stack

Linux uses **BlueZ** (the Debian default Bluetooth stack). Python wrappers:

- **`bleak`** — BLE client (your script connects to a peripheral)
- **`bless`** — BLE GATT server (the board acts as a peripheral that phones connect to)
- **`dbus-python`** — low-level access if you need PIN pairing, Classic SPP, etc.

Install with pip:

```bash
pip install bleak bless
```

## Bring up Bluetooth on Linux

```bash
sudo systemctl start bluetooth         # start the bluetoothd daemon
bluetoothctl power on                  # turn the radio on
bluetoothctl discoverable on           # make the board visible
bluetoothctl agent on                  # accept pairing requests
```

After this the board appears in phone/laptop "Available devices" lists.

## BLE GATT server example (board exposes a sensor to phones)

The pattern: a Python BLE server runs on Linux and exposes a "sensor reading" characteristic. The MCU sketch pushes new readings via Bridge; the server updates the characteristic; subscribed phones receive notifications.

**MCU sketch** (same as the wireless `bridge-tcp.md` example):

```cpp
#include <Arduino.h>
#include <Bridge.h>

unsigned long lastMs = 0;

void setup() { Bridge.begin(); }

void loop() {
    if (millis() - lastMs >= 1000) {
        lastMs = millis();
        Bridge.notify("sensor_reading", analogRead(A0));
    }
    Bridge.poll();
}
```

**Python BLE server:**

```python
import asyncio
from bless import BlessServer, BlessGATTCharacteristic, GATTCharacteristicProperties, GATTAttributePermissions
from arduino import Bridge

SERVICE_UUID = "0000A000-0000-1000-8000-00805F9B34FB"
CHAR_UUID    = "0000A001-0000-1000-8000-00805F9B34FB"

bridge = Bridge(); bridge.begin()

async def main():
    server = BlessServer(name="Uno Q Sensor")
    await server.add_new_service(SERVICE_UUID)
    await server.add_new_characteristic(
        SERVICE_UUID, CHAR_UUID,
        GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify,
        bytearray([0]),
        GATTAttributePermissions.readable,
    )
    await server.start()
    print("BLE server started — connect from a phone using the nRF Connect app.")

    def on_reading(value):
        server.get_characteristic(CHAR_UUID).value = value.to_bytes(2, "big")
        asyncio.run_coroutine_threadsafe(
            server.notify(server.get_characteristic(CHAR_UUID)),
            loop,
        )

    bridge.subscribe("sensor_reading", on_reading)

    await asyncio.Future()   # run forever

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
```

Use the **nRF Connect** app (free on iOS/Android) to test: scan, connect to "Uno Q Sensor", enable notifications on the characteristic, watch the values update.

## BLE client example (board connects to a fitness tracker)

The pattern: Python scans for a known BLE device, connects, subscribes to its heart-rate characteristic, and pushes readings to the MCU sketch.

```python
import asyncio
from bleak import BleakScanner, BleakClient
from arduino import Bridge

bridge = Bridge(); bridge.begin()

DEVICE_NAME = "Polar H10"
HEART_RATE_UUID = "00002A37-0000-1000-8000-00805F9B34FB"

async def main():
    devices = await BleakScanner.discover()
    target = next((d for d in devices if d.name == DEVICE_NAME), None)
    if target is None:
        print(f"{DEVICE_NAME} not found")
        return

    async with BleakClient(target) as client:
        def hr_handler(_sender, data):
            bpm = data[1]
            bridge.call("set_led_brightness", brightness=min(255, bpm))

        await client.start_notify(HEART_RATE_UUID, hr_handler)
        await asyncio.Future()   # run until interrupted

asyncio.run(main())
```

The MCU sketch needs a service for `set_led_brightness` (see `bridge/references/mcu-side.md`).

## Pitfalls

- **Confusing Classic SPP with BLE.** Older "Bluetooth serial" tutorials use Bluetooth Classic SPP (port over RFCOMM). On the Uno Q this works through BlueZ but most phones have dropped Classic SPP support — use BLE instead.
- **Pairing required for some characteristics.** Some BLE peripherals (smartwatches especially) require pairing before they expose characteristics. Use `bluetoothctl pair <MAC>` once, then `bleak` connects without re-pairing.
- **Antenna sharing with Wi-Fi.** The WCN3980 has one PCB antenna shared between Wi-Fi and Bluetooth. Heavy Wi-Fi traffic can cause BLE link drops. If both must run continuously, prefer 5 GHz Wi-Fi (different channel than BT's 2.4 GHz band).
- **Bluetooth on first boot.** `bluetoothd` is enabled by default, but `discoverable` is OFF by default. Either enable it via `systemd` for production or call `bluetoothctl discoverable on` in the Python startup.

## See also

- `wifi-setup.md` for the Wi-Fi sibling.
- `bridge/references/python-side.md` for `bridge.subscribe` patterns used in the BLE server example.
