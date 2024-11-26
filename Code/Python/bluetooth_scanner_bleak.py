#!/usr/bin/env python3
import asyncio
import argparse
import time
from bleak import BleakScanner

async def scan_ble_devices(timeout):
    try:
        devices = await BleakScanner.discover(timeout=timeout)
        return devices
    except Exception as e:
        print(f"An error occurred during scanning: {e}")
        return []

async def continuous_scan(interval, timeout):
    previous_devices = {}
    try:
        while True:
            print("Scanning for BLE devices...")
            devices = await scan_ble_devices(timeout)
            current_devices = {}
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            if devices:
                for device in devices:
                    name = device.name or "Unknown"
                    address = device.address
                    current_devices[address] = name
                    if address not in previous_devices:
                        print(f"[{timestamp}] New Device Found - Name: {name}, Address: {address}")
                for address in previous_devices:
                    if address not in current_devices:
                        name = previous_devices[address]
                        print(f"[{timestamp}] Device Lost - Name: {name}, Address: {address}")
            else:
                print(f"No devices found at {timestamp}.")
            previous_devices = current_devices
            print(f"Waiting for {interval} seconds before next scan...\n")
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        print("Scanning stopped by user.")
    except Exception as e:
        print(f"An error occurred: {e}")

async def main():
    parser = argparse.ArgumentParser(description='BLE Scanner')
    parser.add_argument('-c', '--continuous', action='store_true', help='Enable continuous scanning')
    parser.add_argument('-i', '--interval', type=int, default=10, help='Interval between scans in seconds')
    parser.add_argument('-t', '--timeout', type=int, default=5, help='Scanning timeout in seconds')
    args = parser.parse_args()

    if args.continuous:
        await continuous_scan(args.interval, args.timeout)
    else:
        print("Scanning for BLE devices...")
        devices = await scan_ble_devices(args.timeout)
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        if devices:
            for device in devices:
                name = device.name or "Unknown"
                address = device.address
                print(f"[{timestamp}] Name: {name}, Address: {address}")
        else:
            print(f"No devices found at {timestamp}.")

if __name__ == '__main__':
    asyncio.run(main())
