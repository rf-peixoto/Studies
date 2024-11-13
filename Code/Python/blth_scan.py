import sys
import os
import asyncio
from colorama import init, Fore, Style

def is_android():
    return 'ANDROID_ARGUMENT' in os.environ

def main():
    if is_android():
        run_android_scan()
    else:
        asyncio.run(run_pc_scan())

def run_android_scan():
    try:
        import androidhelper
        # Initialize colorama
        init(autoreset=True)

        droid = androidhelper.Android()

        print(Fore.CYAN + "Scanning for Bluetooth devices on Android...")
        devices = droid.bluetoothDiscoverDevices().result

        if not devices:
            print(Fore.RED + "No devices found.")
        else:
            print(Fore.GREEN + f"Found {len(devices)} device(s):\n")
            for device in devices:
                name = device.get('name', 'Unknown')
                address = device.get('address', 'Unknown')
                print(Fore.YELLOW + f"Device Name   : {name}")
                print(Fore.MAGENTA + f"Device Address: {address}\n")
    except Exception as e:
        print(Fore.RED + f"An error occurred while scanning on Android: {e}")

async def run_pc_scan():
    try:
        from bleak import BleakScanner
        # Initialize colorama
        init(autoreset=True)

        print(Fore.CYAN + "Scanning for Bluetooth LE devices on PC...")

        devices = await BleakScanner.discover(timeout=8)
        if not devices:
            print(Fore.RED + "No BLE devices found.")
        else:
            print(Fore.GREEN + f"Found {len(devices)} BLE device(s):\n")
            for device in devices:
                print(Fore.YELLOW + f"Device Name   : {device.name or 'Unknown'}")
                print(Fore.MAGENTA + f"Device Address: {device.address}")
                print(Fore.BLUE + f"RSSI          : {device.rssi} dBm\n")
    except ImportError:
        print(Fore.RED + "Bleak is not installed. Please install it by running 'pip install bleak'.")
    except Exception as e:
        print(Fore.RED + f"An error occurred while scanning on PC: {e}")

if __name__ == "__main__":
    main()
