import asyncio
from bleak import BleakScanner, BleakClient

TARGET_NAME = "ECO16BT 535550"

async def main():
    print(f"Etsitään laitetta nimellä '{TARGET_NAME}'...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: d.name == TARGET_NAME,
        timeout=10.0
    )

    if not device:
        print(f"❌ Laitetta '{TARGET_NAME}' ei löytynyt.")
        return

    print(f"✅ Laite löytyi: {device.address}. Yhdistetään...")

    async with BleakClient(device) as client:
        print(f"Yhdistetty: {client.is_connected}")
        
        print("Haetaan palvelut ja ominaisuudet (Services & Characteristics)...")
        for service in client.services:
            print(f"\nService: {service.uuid} ({service.description})")
            for char in service.characteristics:
                print(f"  - Char: {char.uuid} ({char.description})")
                print(f"    Properties: {char.properties}")
        
        # TEST: Try to read FACTORY_RESET_ID
        print("\n\n=== TESTI: Yritetään lukea FACTORY_RESET_ID ===")
        FACTORY_RESET_ID_UUID = "f366dddb-ebe2-43ee-83c0-472ded74c8fa"
        
        import asyncio
        await asyncio.sleep(3)
        
        try:
            data = await client.read_gatt_char(FACTORY_RESET_ID_UUID)
            print(f"✅ ONNISTUI! Luettiin {len(data)} tavua: {data.hex()}")
        except Exception as e:
            print(f"❌ EPÄONNISTUI: {e}")

if __name__ == "__main__":
    asyncio.run(main())
