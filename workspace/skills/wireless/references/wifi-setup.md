# Wi-Fi setup on the Uno Q

The Uno Q runs Debian Linux on the MPU side. Wi-Fi is configured with **NetworkManager**, the same tool used on a desktop Debian system. There is no sketch involvement.

## First-time setup (Arduino App Lab)

When the board first boots and an App Lab session is created, you are asked for Wi-Fi credentials as part of the setup wizard. This writes the SSID and password to NetworkManager and the board connects.

After that, the board reconnects automatically on every boot.

## Manual setup from a Linux terminal

Open a terminal on the board (directly, or via SSH after first connection):

### List available networks

```bash
nmcli device wifi list
```

### Connect to a network

```bash
sudo nmcli device wifi connect "YOUR_SSID" password "YOUR_PASSWORD"
```

### Confirm connection

```bash
nmcli connection show --active
ip addr show wlan0     # check the assigned IP
```

The IP address is what users need for SSH access (`ssh arduino@<ip>`) and what Telegram bots / web servers / Bridge-over-network projects bind to.

### Disconnect / forget a network

```bash
nmcli connection down "YOUR_SSID"
nmcli connection delete "YOUR_SSID"
```

## Static IP (deployment deployments)

For consistent SSH access, ask the router admin to reserve a DHCP lease for the board's MAC address. Find the MAC:

```bash
ip link show wlan0    # look for the "link/ether" line
```

Alternative: configure a static IP through NetworkManager:

```bash
sudo nmcli connection modify "YOUR_SSID" \
    ipv4.method manual \
    ipv4.addresses 192.168.1.42/24 \
    ipv4.gateway 192.168.1.1 \
    ipv4.dns "1.1.1.1 8.8.8.8"
sudo nmcli connection up "YOUR_SSID"
```

## What this looks like from a Python program

Once Linux is on Wi-Fi, all standard Python network libraries work:

```python
import requests
r = requests.get("https://api.example.com/status")
print(r.json())
```

The Wi-Fi state is invisible to your code — it Just Works. If the connection drops, `requests` raises a `ConnectionError` you can catch and retry.

## Diagnostics

| Symptom | Check |
|---|---|
| `nmcli device wifi list` is empty | `rfkill list` → may be a soft block; `sudo rfkill unblock wifi` |
| Connects but no internet | `ip route show` → does the default route point to your gateway? |
| Drops every few minutes | Strong neighbouring AP on the same channel; switch to 5 GHz (some routers default to 2.4 GHz only) |
| Slow throughput | `iwconfig wlan0` → check bit rate; antenna may need re-seating (the antenna is internal, but contact pad oxidation is possible on long-aged boards) |

## What the MCU sees

Nothing. The MCU has no Wi-Fi peripheral. If your sketch needs network access, the pattern is:

1. MCU collects data
2. MCU calls `Bridge.notify("data", payload)` or exposes a service Python calls
3. Python on Linux does the HTTP/MQTT/WebSocket call

See `bridge-tcp.md` for the worked example.
