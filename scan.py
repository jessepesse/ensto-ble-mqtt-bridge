import asyncio
from bleak import BleakScanner

# Sinun termostaattisi MAC
TARGET_MAC = "6C:FD:22:F4:7B:06"

async def main():
    print("Skannataan Bluetooth-laitteita (10 sekuntia)...")
    
    # Skannaa kaiken ympärillä olevan, palauttaa sanakirjan {osoite: (laite, mainosdata)}
    devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
    
    found = False
    for d, adv in devices.values():
        # Tulostetaan kaikki Enstot tai meidän kohde
        if d.address == TARGET_MAC:
            print(f"✅ LÖYTYI! Nimi: {d.name} | Osoite: {d.address} | Voimakkuus: {adv.rssi} dBm")
            found = True
        elif "Ensto" in (d.name or "") or "ECO" in (d.name or ""):
            print(f"❓ Muu Ensto löytyi: {d.name} | {d.address} | {adv.rssi} dBm")

    if not found:
        print("❌ Laitetta ei näy skannauksessa.")
        print("VINKKI: Onko joku muu laite (puhelin/Home Assistant) yhä yhteydessä siihen?")

if __name__ == "__main__":
    asyncio.run(main())
