# Ensto BLE to MQTT Bridge

> [!NOTE]
> **Project Status: Alpha / Experimental**
> This project is currently in early development. Features and configuration methods may change. Use with caution.

Python script to read sensor data from Ensto BLE thermostats (ECO16BT, ELTE6-BT) and publish it to Home Assistant via MQTT.

## Features

- 🔌 **Connects to Ensto BLE thermostats** (ECO16BT, ELTE6-BT)
- 📡 **Publishes sensor data to MQTT**
- 🏠 **Home Assistant MQTT Discovery support** (auto-configures sensors)
- 🔐 **Persistent Authentication**: Stores Factory Reset IDs to allow connection without pairing mode.
- 🔄 **Automatic reconnection and retry logic**
- 📊 **Reads**: Room temperature, Floor temperature, Target temperature (calibrated*), Relay state
  > *Note: Target temperature calibration is experimental and may require further tuning.*

## Requirements

### Hardware / OS
- **Linux/Raspberry Pi** with BlueZ (macOS is NOT supported due to Core Bluetooth limitations)
- Bluetooth adapter

### Software
- Python 3.8+
- **Home Assistant** with:
    - **MQTT Broker** (e.g., Mosquitto) installed and running.
    - **MQTT User** created in Home Assistant with **Local** and **Admin** rights (required for discovery and state updates).

## Installation

### 1. Clone repository
```bash
git clone https://github.com/jessepesse/ensto-ble-mqtt-bridge.git
cd ensto-ble-mqtt-bridge
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure
Copy the example configuration file:
```bash
cp config.json.example config.json
```

Edit `config.json` with your settings:
```json
{
    "mqtt": {
        "broker": "192.168.1.100",
        "port": 1883,
        "username": "mqtt_user",
        "password": "your_password"
    },
    "poll_interval": 120,
    "devices": [
        "AA:BB:CC:DD:EE:FF"
    ]
}
```
*   **devices**: List of MAC addresses for your thermostats.

## First Run (Pairing)

**Important:** For the very first connection, the thermostat must be in **Pairing Mode** to capture the authentication key.

1.  Put your thermostat in **Pairing Mode** (Blue LED blinking).
2.  Run the script:
    ```bash
    python3 ensto_bridge.py
    ```
3.  The script will:
    - Connect to the device.
    - Capture the `Factory Reset ID`.
    - Save it to `ensto_devices.json`.
    - Perform the handshake and read data.

**Subsequent runs do NOT require pairing mode.** The script will use the stored key from `ensto_devices.json`.

## Running as a Service

To keep the bridge running in the background, you can create a systemd service.

1.  Create service file: `sudo nano /etc/systemd/system/ensto-bridge.service`
    ```ini
    [Unit]
    Description=Ensto BLE MQTT Bridge
    After=network.target bluetooth.target

    [Service]
    ExecStart=/usr/bin/python3 /path/to/ensto-ble-mqtt-bridge/ensto_bridge.py
    WorkingDirectory=/path/to/ensto-ble-mqtt-bridge
    StandardOutput=inherit
    StandardError=inherit
    Restart=always
    User=pi

    [Install]
    WantedBy=multi-user.target
    ```
2.  Enable and start:
    ```bash
    sudo systemctl enable ensto-bridge
    sudo systemctl start ensto-bridge
    ```

## MQTT Topics

### State Topic
```
ensto_bridge/<device_address>/state
```

Example payload:
```json
{
  "target_temperature": 21.5,
  "room_temperature": 20.3,
  "floor_temperature": 22.1,
  "relay_active": true
}
```

### Discovery Topics
Home Assistant will automatically discover:
- `sensor.ensto_<address>_room_temp` - Room temperature
- `sensor.ensto_<address>_floor_temp` - Floor temperature
- `sensor.ensto_<address>_target_temp` - Target temperature
- `binary_sensor.ensto_<address>_relay` - Relay state (heating on/off)

## Troubleshooting

### "Handshake failed"
- Ensure `ensto_devices.json` exists and contains a key for your device.
- If not, delete the entry from `ensto_devices.json` and run the "First Run (Pairing)" steps again.

### "Service Discovery has not been performed yet"
- This is usually a transient Bluetooth error. The script will automatically retry.
- Ensure no other device (phone app) is connected to the thermostat.

## License

MIT License
