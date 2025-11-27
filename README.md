# Ensto BLE to MQTT Bridge

Python script to read sensor data from Ensto BLE thermostats and publish it to Home Assistant via MQTT.

## Features

- 🔌 Connects to Ensto BLE thermostats (ECO16BT, ELTE6-BT)
- 📡 Publishes sensor data to MQTT
- 🏠 Home Assistant MQTT Discovery support (auto-configures sensors)
- 🔄 Automatic reconnection and retry logic
- 📊 Reads: Room temperature, Floor temperature, Target temperature, Relay state

## Requirements

- **Linux/Raspberry Pi** with BlueZ (macOS is NOT supported due to Core Bluetooth limitations)
- Python 3.8+
- Bluetooth adapter
- MQTT broker (e.g., Mosquitto)

## Installation

### 1. Clone repository
```bash
git clone https://github.com/yourusername/ensto_bridge.git
cd ensto_bridge
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure
Edit `ensto_bridge.py` and set:
- `MQTT_BROKER` - Your MQTT broker IP address
- `MQTT_PORT` - MQTT broker port (default: 1883)
- `MQTT_USER` - MQTT username
- `MQTT_PASSWORD` - MQTT password
- `DEVICES` - List of thermostat names (e.g., `["ECO16BT 535550"]`)
- `POLL_INTERVAL` - Polling interval in seconds (default: 120)

### 4. Run
```bash
python3 ensto_bridge.py
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

## Debugging Tools

### scan.py
Scan for nearby BLE devices:
```bash
python3 scan.py
```

### ble_inspect.py
Inspect GATT services and characteristics:
```bash
python3 ble_inspect.py
```

## Troubleshooting

### "Device not found"
- Ensure the thermostat is powered on and within Bluetooth range
- Make sure no other device (phone, Home Assistant) is connected to it
- Try running `scan.py` to verify the device is visible

### "Handshake failed" or "Service Discovery has not been performed yet"
- **On macOS**: This script requires Linux/Raspberry Pi with BlueZ. macOS Core Bluetooth does not support the vendor-specific UUIDs used by Ensto thermostats.
- **On Linux**: Ensure BlueZ version is >= 5.55

### MQTT Connection Issues
- Verify MQTT broker is running and accessible
- Check username/password credentials
- Test connection with `mosquitto_pub`:
  ```bash
  mosquitto_pub -h <broker_ip> -u <user> -P <password> -t test -m "hello"
  ```

## Limitations

- ❌ **macOS is not supported** - Core Bluetooth limitations prevent reading vendor-specific UUIDs
- ✅ **Linux/Raspberry Pi** - Fully supported with BlueZ
- ⏱️ Poll-based (reads data every 2 minutes by default) - not real-time

## Credits

Based on research from the [hass_ensto_ble](https://github.com/ExMacro/hass_ensto_ble) Home Assistant integration.

## License

MIT License
