import asyncio
import logging
import json
import struct
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt

# Configuration
MQTT_BROKER = "192.168.1.35"
MQTT_PORT = 1883
MQTT_USER = "mqtt_bridge"
MQTT_PASSWORD = "Ensto1234"
POLL_INTERVAL = 120  # seconds

# List of your Ensto thermostat MAC addresses OR Device Names (for macOS)
DEVICES = [
    "ECO16BT 535550", 
]

# Constants
MANUFACTURER_ID = 0x2806
FACTORY_RESET_ID_UUID = "f366dddb-ebe2-43ee-83c0-472ded74c8fa"
REAL_TIME_INDICATION_UUID = "66ad3e6b-3135-4ada-bb2b-8b22916b21d4"

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnstoBridge:
    def __init__(self):
        # Generate a unique client ID to avoid conflicts
        import time
        client_id = f"ensto_bridge_{int(time.time())}"
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        
        if MQTT_USER and MQTT_PASSWORD:
            self.mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Connected to MQTT Broker")
        else:
            logger.error(f"Failed to connect to MQTT Broker, return code {rc}")

    def on_mqtt_disconnect(self, client, userdata, disconnect_flags, rc, properties=None):
        logger.warning(f"Disconnected from MQTT Broker (rc={rc})")

    async def run(self):
        try:
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.mqtt_client.loop_start()
        except Exception as e:
            logger.error(f"Could not connect to MQTT broker: {e}")
            return

        while True:
            for identifier in DEVICES:
                try:
                    await self.process_device(identifier)
                except Exception as e:
                    logger.error(f"Error processing device {identifier}: {e}")
            
            logger.info(f"Sleeping for {POLL_INTERVAL} seconds...")
            await asyncio.sleep(POLL_INTERVAL)

    async def find_device(self, identifier):
        """Finds a device by Name using find_device_by_name."""
        logger.info(f"Scanning for device '{identifier}'...")
        
        # Use find_device_by_name which works better on macOS
        device = await BleakScanner.find_device_by_name(identifier, timeout=10.0)
        
        if device:
            logger.info(f"Found {device.name} at {device.address}")
        return device

    async def process_device(self, identifier):
        device = await self.find_device(identifier)
        if not device:
            logger.error(f"Device '{identifier}' not found during scan")
            return

        logger.info(f"Connecting to {device.name}...")

        async with BleakClient(device, timeout=20.0) as client:
            if not client.is_connected:
                logger.error(f"Failed to connect to {device.address}")
                return
            
            logger.info(f"Connected successfully")
            
            # Longer initial wait for macOS Core Bluetooth to settle
            logger.info("Waiting for services to initialize...")
            await asyncio.sleep(5)
            
            # Warm up the connection by reading some standard characteristics first
            # This forces macOS to resolve all the handles properly
            try:
                logger.info("Warming up connection with standard reads...")
                
                # Read device name (standard UUID)
                device_name_data = await client.read_gatt_char("00002a00-0000-1000-8000-00805f9b34fb")
                logger.info(f"Device name read: {device_name_data[:20]}")
                
                # Small delay
                await asyncio.sleep(1)
                
                # Read manufacturer name (standard UUID)
                mfg_data = await client.read_gatt_char("00002a29-0000-1000-8000-00805f9b34fb")
                logger.info(f"Manufacturer read: {mfg_data}")
                
                # Another delay to let things settle
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.warning(f"Warmup reads failed (non-critical): {e}")
                await asyncio.sleep(3)
            
            # Handshake - required on Linux/Raspberry Pi
            # (macOS Core Bluetooth doesn't support vendor UUID reads without proper bonding)
            logger.info("Attempting handshake...")
            for attempt in range(3):
                try:
                    factory_id_bytes = await client.read_gatt_char(FACTORY_RESET_ID_UUID)
                    logger.info(f"Read factory ID: {len(factory_id_bytes)} bytes")
                    
                    # Write it back
                    await client.write_gatt_char(FACTORY_RESET_ID_UUID, factory_id_bytes)
                    logger.info("Handshake completed successfully!")
                    break
                except Exception as e:
                    logger.warning(f"Handshake attempt {attempt + 1}/3 failed: {e}")
                    if attempt == 2:
                        logger.error("Handshake failed after 3 attempts. Note: This script requires Linux/Raspberry Pi with BlueZ.")
                        return
                    await asyncio.sleep(3)

            # Read Real Time Indication
            try:
                data = await client.read_gatt_char(REAL_TIME_INDICATION_UUID)
                parsed_data = self.parse_real_time_data(data)
                logger.info(f"✅ Data read success: {parsed_data}")
                
                self.publish_data(device.address, parsed_data)
                self.publish_discovery(device.address, device.name)
                
            except Exception as e:
                logger.error(f"Failed to read data: {e}")

    def parse_real_time_data(self, data):
        if len(data) < 20:
            return {}
        
        # Parsing logic based on research
        target_temp = int.from_bytes(data[0:2], byteorder='little') / 10.0
        room_temp = int.from_bytes(data[3:5], byteorder='little', signed=True) / 10.0
        floor_temp = int.from_bytes(data[5:7], byteorder='little', signed=True) / 10.0
        relay_active = bool(data[7])
        
        return {
            "target_temperature": target_temp,
            "room_temperature": room_temp,
            "floor_temperature": floor_temp,
            "relay_active": relay_active
        }

    def publish_data(self, mac, data):
        sanitized_mac = mac.replace(":", "")
        topic = f"ensto_bridge/{sanitized_mac}/state"
        self.mqtt_client.publish(topic, json.dumps(data))

    def publish_discovery(self, mac, device_name=None):
        sanitized_mac = mac.replace(":", "")
        name = device_name if device_name else f"Ensto Thermostat {sanitized_mac}"
        
        device_info = {
            "identifiers": [f"ensto_{sanitized_mac}"],
            "name": name,
            "manufacturer": "Ensto",
            "model": "BLE Thermostat"
        }
        
        # Room Temp
        config_topic = f"homeassistant/sensor/ensto_{sanitized_mac}/room_temp/config"
        payload = {
            "name": "Room Temperature",
            "unique_id": f"ensto_{sanitized_mac}_room_temp",
            "state_topic": f"ensto_bridge/{sanitized_mac}/state",
            "value_template": "{{ value_json.room_temperature }}",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "device": device_info
        }
        self.mqtt_client.publish(config_topic, json.dumps(payload), retain=True)

        # Floor Temp
        config_topic = f"homeassistant/sensor/ensto_{sanitized_mac}/floor_temp/config"
        payload = {
            "name": "Floor Temperature",
            "unique_id": f"ensto_{sanitized_mac}_floor_temp",
            "state_topic": f"ensto_bridge/{sanitized_mac}/state",
            "value_template": "{{ value_json.floor_temperature }}",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "device": device_info
        }
        self.mqtt_client.publish(config_topic, json.dumps(payload), retain=True)
        
        # Target Temp
        config_topic = f"homeassistant/sensor/ensto_{sanitized_mac}/target_temp/config"
        payload = {
            "name": "Target Temperature",
            "unique_id": f"ensto_{sanitized_mac}_target_temp",
            "state_topic": f"ensto_bridge/{sanitized_mac}/state",
            "value_template": "{{ value_json.target_temperature }}",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "device": device_info
        }
        self.mqtt_client.publish(config_topic, json.dumps(payload), retain=True)

        # Relay State
        config_topic = f"homeassistant/binary_sensor/ensto_{sanitized_mac}/relay/config"
        payload = {
            "name": "Relay Active",
            "unique_id": f"ensto_{sanitized_mac}_relay",
            "state_topic": f"ensto_bridge/{sanitized_mac}/state",
            "value_template": "{{ 'ON' if value_json.relay_active else 'OFF' }}",
            "device_class": "power",
            "device": device_info
        }
        self.mqtt_client.publish(config_topic, json.dumps(payload), retain=True)

if __name__ == "__main__":
    bridge = EnstoBridge()
    asyncio.run(bridge.run())