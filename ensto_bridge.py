import asyncio
import logging
import json
import struct
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt

# Configuration
CONFIG_FILE = "config.json"

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Configuration file '{CONFIG_FILE}' not found. Please copy config.json.example to config.json and edit it.")
        exit(1)
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        exit(1)

config = load_config()

MQTT_BROKER = config["mqtt"]["broker"]
MQTT_PORT = config["mqtt"]["port"]
MQTT_USER = config["mqtt"]["username"]
MQTT_PASSWORD = config["mqtt"]["password"]
POLL_INTERVAL = config.get("poll_interval", 120)
DEVICES = config.get("devices", [])

# Constants
MANUFACTURER_ID = 0x2806
FACTORY_RESET_ID_UUID = "f366dddb-ebe2-43ee-83c0-472ded74c8fa"
REAL_TIME_INDICATION_UUID = "66ad3e6b-3135-4ada-bb2b-8b22916b21d4"
STORAGE_FILE = "ensto_devices.json"

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("bleak").setLevel(logging.DEBUG)


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

    def load_device_data(self):
        try:
            with open(STORAGE_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.error(f"Failed to load device data: {e}")
            return {}

    def save_device_data(self, data):
        try:
            with open(STORAGE_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save device data: {e}")

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
        """Finds a device by Name or Address."""
        logger.info(f"Scanning for device '{identifier}'...")
        
        # Check if identifier looks like a MAC address (contains :)
        if ":" in identifier:
             device = await BleakScanner.find_device_by_address(identifier, timeout=10.0)
        else:
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
        
        # Use address string instead of device object to avoid potential stale object issues
        async with BleakClient(device.address, timeout=20.0) as client:
            if not client.is_connected:
                logger.error(f"Failed to connect to {device.address}")
                return
            
            logger.info(f"Connected successfully")
            
            # Longer initial wait for macOS Core Bluetooth to settle
            logger.info("Waiting for services to initialize...")
            await asyncio.sleep(5)
            
            # Warmup reads removed as they cause instability on Linux
            # The connection seems to be ready after the initial wait

            
            # Handshake - required on Linux/Raspberry Pi
            logger.info("Attempting handshake...")
            
            # Check if we have a stored Factory ID
            stored_data = self.load_device_data()
            device_id_hex = stored_data.get(device.address)
            
            factory_id_bytes = None
            
            if device_id_hex:
                logger.info(f"Found stored Factory ID for {device.address}")
                try:
                    factory_id_bytes = bytes.fromhex(device_id_hex)
                except ValueError:
                    logger.error("Invalid stored ID format")
            
            if not factory_id_bytes:
                logger.info("No stored ID found. Attempting to read from device (Requires Pairing Mode)...")
                try:
                    factory_id_bytes = await client.read_gatt_char(FACTORY_RESET_ID_UUID)
                    # Check if valid (not all zeros)
                    if all(b == 0 for b in factory_id_bytes):
                        logger.warning("Read ID is all zeros! Device NOT in pairing mode?")
                        factory_id_bytes = None
                    else:
                        logger.info(f"Read new Factory ID: {factory_id_bytes.hex()}")
                        # Store it
                        stored_data[device.address] = factory_id_bytes.hex()
                        self.save_device_data(stored_data)
                        logger.info("Saved Factory ID to storage")
                except Exception as e:
                    logger.warning(f"Failed to read Factory ID: {e}")

            if factory_id_bytes:
                # Write it back to authenticate
                try:
                    await client.write_gatt_char(FACTORY_RESET_ID_UUID, factory_id_bytes)
                    logger.info("Handshake completed successfully!")
                except Exception as e:
                    logger.error(f"Handshake write failed: {e}")
                    return
            else:
                 logger.error("Handshake failed: Could not obtain Factory ID. Please put device in PAIRING MODE.")
                 return

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
        if len(data) < 10:
            return {}
        
        # Log raw data for debugging
        logger.info(f"Raw data: {data.hex()}")
        
        # Parsing logic based on log analysis
        # Parsing logic based on user calibration
        # Value is 32-bit uint (bytes 0-3)
        # Min (5°C): 13038
        # Max (35°C): 128198
        # Range: 115160
        raw_target = int.from_bytes(data[0:4], byteorder='little')
        
        # Linear interpolation: 5 + (raw - 13038) * (30 / 115160)
        target_temp = 5.0 + (raw_target - 13038) * (30.0 / 115160.0)
        target_temp = round(target_temp, 1)
        
        # Room temp: bytes 4-5 (little endian), scaled by 10
        room_temp = int.from_bytes(data[4:6], byteorder='little', signed=True) / 10.0
        
        # Floor temp: bytes 6-7 (little endian), scaled by 10
        floor_temp = int.from_bytes(data[6:8], byteorder='little', signed=True) / 10.0
        
        # Relay state: byte 13 (index 13)
        relay_active = False
        if len(data) > 13:
            relay_active = bool(data[13])
        
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