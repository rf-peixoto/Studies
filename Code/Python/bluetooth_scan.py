#!/usr/bin/env python3
import subprocess
import json
import time
import argparse

def scan_bluetooth_devices():
    try:
        # Run the termux-bluetooth-scan command
        result = subprocess.run(['termux-bluetooth-scan'], stdout=subprocess.PIPE, text=True)
        output = result.stdout.strip()
        devices = []
        # Check if output is not empty
        if output:
            # Parse JSON output
            devices = json.loads(output)
        return devices
    except Exception as e:
        print(f"An error occurred during scanning: {e}")
        return []

def continuous_scan(interval):
    try:
        previous_devices = {}
        while True:
            print("Scanning for Bluetooth devices...")
            devices = scan_bluetooth_devices()
            current_devices = {}
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            if devices:
                for device in devices:
                    name = device.get('name', 'Unknown')
                    address = device.get('address', 'Unknown')
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
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Scanning stopped by user.")

def main():
    parser = argparse.ArgumentParser(description='Bluetooth Scanner')
    parser.add_argument('-c', '--continuous', action='store_true', help='Enable continuous scanning')
    parser.add_argument('-i', '--interval', type=int, default=10, help='Interval between scans in seconds')
    args = parser.parse_args()

    if args.continuous:
        continuous_scan(args.interval)
    else:
        print("Scanning for Bluetooth devices...")
        devices = scan_bluetooth_devices()
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        if devices:
            for device in devices:
                name = device.get('name', 'Unknown')
                address = device.get('address', 'Unknown')
                print(f"[{timestamp}] Name: {name}, Address: {address}")
        else:
            print(f"No devices found at {timestamp}.")

if __name__ == '__main__':
    main()
