#!/usr/bin/env python3
import asyncio
import argparse
import time
import os
import sys
import json
import requests
from bleak import BleakScanner, BleakClient
from bleak.exc import BleakError

# For color output
from colorama import init, Fore, Style

# Initialize colorama
init()

# Expanded Characteristic UUIDs for known services
CHARACTERISTIC_UUIDS = {
    # Battery Service
    'battery_level': '00002a19-0000-1000-8000-00805f9b34fb',  # Battery Level

    # Device Information Service
    'manufacturer_name': '00002a29-0000-1000-8000-00805f9b34fb',  # Manufacturer Name String
    'model_number': '00002a24-0000-1000-8000-00805f9b34fb',       # Model Number String
    'serial_number': '00002a25-0000-1000-8000-00805f9b34fb',      # Serial Number String
    'hardware_revision': '00002a27-0000-1000-8000-00805f9b34fb',  # Hardware Revision String
    'firmware_revision': '00002a26-0000-1000-8000-00805f9b34fb',  # Firmware Revision String
    'software_revision': '00002a28-0000-1000-8000-00805f9b34fb',  # Software Revision String
    'system_id': '00002a23-0000-1000-8000-00805f9b34fb',          # System ID
	
    # Location and Navigation Service
    'location_and_speed': '00002a67-0000-1000-8000-00805f9b34fb',
    'navigation': '00002a68-0000-1000-8000-00805f9b34fb',
	
    # Alert Notification Service
    'alert_notification_control_point': '00002a44-0000-1000-8000-00805f9b34fb',
    'unread_alert_status': '00002a45-0000-1000-8000-00805f9b34fb',
	
    # Phone Alert Status Service
    'phone_alert_status': '00002a42-0000-1000-8000-00805f9b34fb',
	
    # Automation IO Service
    'digital': '00002a56-0000-1000-8000-00805f9b34fb',
    'analog': '00002a58-0000-1000-8000-00805f9b34fb',
	
    # User Data Service
    'first_name': '00002a8a-0000-1000-8000-00805f9b34fb',
    'age': '00002a80-0000-1000-8000-00805f9b34fb',
    'gender': '00002a8c-0000-1000-8000-00805f9b34fb',
	
    # Pulse Oximeter Service
    'plx_spot_check_measurement': '00002a5e-0000-1000-8000-00805f9b34fb',
    'plx_continuous_measurement': '00002a5f-0000-1000-8000-00805f9b34fb',
	
    # Heart Rate Service
    'heart_rate_measurement': '00002a37-0000-1000-8000-00805f9b34fb',
	
    # Human Interface Device (HID) Service
    'hid_information': '00002a4a-0000-1000-8000-00805f9b34fb',    # HID Information
    'report_map': '00002a4b-0000-1000-8000-00805f9b34fb',         # Report Map
    'protocol_mode': '00002a4e-0000-1000-8000-00805f9b34fb',      # Protocol Mode
	
    # Audio Input Control Service
    'audio_input_state': '00002b77-0000-1000-8000-00805f9b34fb',  # Audio Input State
    'audio_input_type': '00002b78-0000-1000-8000-00805f9b34fb',   # Audio Input Type
    'audio_input_status': '00002b79-0000-1000-8000-00805f9b34fb', # Audio Input Status
	
    # Microphone Control Service
    'mute': '00002b7b-0000-1000-8000-00805f9b34fb',               # Mute
	
    # Volume Control Service
    'volume_state': '00002b7d-0000-1000-8000-00805f9b34fb',       # Volume State
    'volume_control_point': '00002b7e-0000-1000-8000-00805f9b34fb', # Volume Control Point
	
    # Media Control Service
    'media_player_name': '00002b93-0000-1000-8000-00805f9b34fb',  # Media Player Name
    'media_state': '00002b94-0000-1000-8000-00805f9b34fb',        # Media State
    'media_control_point': '00002b95-0000-1000-8000-00805f9b34fb', # Media Control Point
	
    # Object Transfer Service
    'object_action_control_point': '00002ac5-0000-1000-8000-00805f9b34fb', # Object Action Control Point
    'object_list_control_point': '00002ac6-0000-1000-8000-00805f9b34fb',   # Object List Control Point
	
    # Scan Parameters Service
    'scan_interval_window': '00002a4f-0000-1000-8000-00805f9b34fb', # Scan Interval Window
    'scan_refresh': '00002a31-0000-1000-8000-00805f9b34fb',         # Scan Refresh
	
    # Immediate Alert Service
    'alert_level': '00002a06-0000-1000-8000-00805f9b34fb',          # Alert Level
	
    # Link Loss Service
    'link_loss_alert_level': '00002a06-0000-1000-8000-00805f9b34fb', # Alert Level
    'heart_rate_measurement': '00002a37-0000-1000-8000-00805f9b34fb',  # Heart Rate Measurement
}

async def read_characteristic(client, uuid):
    try:
        value = await client.read_gatt_char(uuid)
        return value
    except Exception:
        return None

async def get_device_info(address):
    device_info = {}
    try:
        async with BleakClient(address) as client:
            for key, uuid in CHARACTERISTIC_UUIDS.items():
                value = await read_characteristic(client, uuid)
                if value is not None:
                    # Decode value based on characteristic
                    if key in ['manufacturer_name', 'model_number', 'serial_number',
                               'hardware_revision', 'firmware_revision', 'software_revision',
                               'system_id', 'first_name']:
                        device_info[key.replace('_', ' ').title()] = value.decode('utf-8', errors='ignore')
                    elif key in ['battery_level', 'heart_rate_measurement', 'age']:
                        device_info[key.replace('_', ' ').title()] = int(value[0])
                    elif key == 'gender':
                        gender = 'Male' if value[0] == 0 else 'Female'
                        device_info['Gender'] = gender
                    elif key in ['plx_spot_check_measurement', 'plx_continuous_measurement']:
                        # Simplified parsing
                        spo2 = value[1]
                        pulse_rate = value[3]
                        device_info['SpO2'] = spo2
                        device_info['Pulse Rate'] = pulse_rate
                    else:
                        # For other characteristics, display raw data
                        device_info[key.replace('_', ' ').title()] = value.hex()
    except Exception:
        # Unable to connect or read characteristics
        pass

    return device_info

async def scan_ble_devices(timeout, filter_name=None, filter_address=None, filter_uuid=None):
    try:
        devices = await BleakScanner.discover(timeout=timeout)
        # Apply filters if specified
        if filter_name:
            devices = [d for d in devices if filter_name.lower() in (d.name or "").lower()]
        if filter_address:
            devices = [d for d in devices if filter_address.lower() in d.address.lower()]
        if filter_uuid:
            devices = [d for d in devices if filter_uuid.lower() in [uuid.lower() for uuid in d.metadata.get('uuids', [])]]
        return devices
    except Exception as e:
        print(f"An error occurred during scanning: {e}")
        return []

def get_geolocation():
    try:
        response = requests.get('https://ipinfo.io/json')
        if response.status_code == 200:
            data = response.json()
            location = data.get('loc', '')  # Format is "latitude,longitude"
            if location:
                latitude, longitude = location.split(',')
                geolocation = {
                    'latitude': latitude,
                    'longitude': longitude,
                    'city': data.get('city', ''),
                    'region': data.get('region', ''),
                    'country': data.get('country', '')
                }
                return geolocation
    except Exception:
        pass
    return {}

async def continuous_scan(args):
    previous_devices = {}
    all_devices_info = []
    try:
        while True:
            # Clear the terminal for better UX
            os.system('cls' if os.name == 'nt' else 'clear')
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            devices = await scan_ble_devices(args.timeout, args.name, args.address, args.uuid)
            current_devices = {}
            if devices:
                for device in devices:
                    name = device.name or "Unknown"
                    address = device.address
                    rssi = device.rssi
                    adv_data = device.metadata.get('uuids', [])
                    manufacturer_data = device.metadata.get('manufacturer_data', {})
                    tx_power = device.metadata.get('tx_power')
                    local_name = device.metadata.get('local_name', 'Unknown')

                    current_devices[address] = name

                    # Determine if new device or update
                    if address not in previous_devices:
                        status_color = Fore.GREEN
                        status_text = "New Device Found"
                    else:
                        status_color = Fore.CYAN
                        status_text = "Device Update"

                    print(f"{status_color}[{timestamp}] {status_text}:{Style.RESET_ALL}")
                    print(f"  Name: {name}")
                    print(f"  Address: {address}")
                    print(f"  RSSI: {rssi} dBm")
                    print(f"  Local Name: {local_name}")
                    print(f"  Advertised Service UUIDs: {adv_data}")
                    print(f"  Manufacturer Data: {manufacturer_data}")
                    print(f"  TX Power: {tx_power}")

                    # Get additional device information
                    device_info = await get_device_info(address)
                    for key, value in device_info.items():
                        print(f"  {key}: {value}")

                    print("")

                    # Collect data for JSON output
                    if args.json:
                        device_data = {
                            'timestamp': timestamp,
                            'name': name,
                            'address': address,
                            'rssi': rssi,
                            'local_name': local_name,
                            'advertised_service_uuids': adv_data,
                            'manufacturer_data': {str(k): v.hex() for k, v in manufacturer_data.items()},
                            'tx_power': tx_power,
                            'additional_info': device_info
                        }
                        all_devices_info.append(device_data)

                for address in previous_devices:
                    if address not in current_devices:
                        name = previous_devices[address]
                        print(f"{Fore.RED}[{timestamp}] Device Lost - Name: {name}, Address: {address}{Style.RESET_ALL}")
            else:
                print(f"No devices found at {timestamp}.")
            previous_devices = current_devices
            print(f"Next scan in {args.interval} seconds...\n")

            # If JSON output is requested, write to file
            if args.json:
                output_data = {
                    'statistics': {
                        'scan_time': timestamp,
                        'geolocation': get_geolocation(),
                        'total_devices_found': len(all_devices_info)
                    },
                    'devices': all_devices_info
                }
                with open(args.json, 'w') as json_file:
                    json.dump(output_data, json_file, indent=4)
                # Clear devices info after writing to avoid duplication
                all_devices_info = []

            await asyncio.sleep(args.interval)
    except KeyboardInterrupt:
        print("Scanning stopped by user.")
        # Write remaining data to JSON if any
        if args.json and all_devices_info:
            output_data = {
                'statistics': {
                    'scan_time': timestamp,
                    'geolocation': get_geolocation(),
                    'total_devices_found': len(all_devices_info)
                },
                'devices': all_devices_info
            }
            with open(args.json, 'w') as json_file:
                json.dump(output_data, json_file, indent=4)
    except Exception as e:
        print(f"An error occurred: {e}")

async def main():
    parser = argparse.ArgumentParser(description='BLE Scanner')
    parser.add_argument('-c', '--continuous', action='store_true', help='Enable continuous scanning')
    parser.add_argument('-i', '--interval', type=int, default=10, help='Interval between scans in seconds')
    parser.add_argument('-t', '--timeout', type=int, default=5, help='Scanning timeout in seconds')
    parser.add_argument('-n', '--name', type=str, help='Filter devices by name')
    parser.add_argument('-a', '--address', type=str, help='Filter devices by address')
    parser.add_argument('-u', '--uuid', type=str, help='Filter devices by advertised service UUID')
    parser.add_argument('-l', '--log', type=str, help='Log output to a file')
    parser.add_argument('-j', '--json', type=str, help='Output results to a JSON file')
    args = parser.parse_args()

    # Redirect output to log file if specified
    if args.log:
        sys.stdout = open(args.log, 'w')

    if args.continuous:
        await continuous_scan(args)
    else:
        # Clear the terminal for better UX
        os.system('cls' if os.name == 'nt' else 'clear')
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        devices = await scan_ble_devices(args.timeout, args.name, args.address, args.uuid)
        all_devices_info = []
        if devices:
            for device in devices:
                name = device.name or "Unknown"
                address = device.address
                rssi = device.rssi
                adv_data = device.metadata.get('uuids', [])
                manufacturer_data = device.metadata.get('manufacturer_data', {})
                tx_power = device.metadata.get('tx_power')
                local_name = device.metadata.get('local_name', 'Unknown')

                print(f"{Fore.GREEN}[{timestamp}] Device Found:{Style.RESET_ALL}")
                print(f"  Name: {name}")
                print(f"  Address: {address}")
                print(f"  RSSI: {rssi} dBm")
                print(f"  Local Name: {local_name}")
                print(f"  Advertised Service UUIDs: {adv_data}")
                print(f"  Manufacturer Data: {manufacturer_data}")
                print(f"  TX Power: {tx_power}")

                # Get additional device information
                device_info = await get_device_info(address)
                for key, value in device_info.items():
                    print(f"  {key}: {value}")

                print("")

                # Collect data for JSON output
                if args.json:
                    device_data = {
                        'timestamp': timestamp,
                        'name': name,
                        'address': address,
                        'rssi': rssi,
                        'local_name': local_name,
                        'advertised_service_uuids': adv_data,
                        'manufacturer_data': {str(k): v.hex() for k, v in manufacturer_data.items()},
                        'tx_power': tx_power,
                        'additional_info': device_info
                    }
                    all_devices_info.append(device_data)

            # If JSON output is requested, write to file
            if args.json:
                output_data = {
                    'statistics': {
                        'scan_time': timestamp,
                        'geolocation': get_geolocation(),
                        'total_devices_found': len(all_devices_info)
                    },
                    'devices': all_devices_info
                }
                with open(args.json, 'w') as json_file:
                    json.dump(output_data, json_file, indent=4)
        else:
            print(f"No devices found at {timestamp}.")

if __name__ == '__main__':
    asyncio.run(main())
