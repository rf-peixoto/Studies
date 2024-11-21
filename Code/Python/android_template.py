import os
import subprocess
import json
import psutil
import re
import datetime

def is_device_rooted():
    root_files = [
        '/system/app/Superuser.apk', '/sbin/su', '/system/bin/su',
        '/system/xbin/su', '/data/local/xbin/su', '/data/local/bin/su',
        '/system/sd/xbin/su', '/system/bin/failsafe/su', '/data/local/su'
    ]
    for file in root_files:
        if os.path.exists(file):
            return True
    return False

def get_system_info():
    print("\n--- System Information ---")
    try:
        # Get Termux info
        termux_info = subprocess.check_output(['termux-info'], stderr=subprocess.STDOUT).decode()
        print(termux_info)
    except Exception as e:
        print("Error retrieving Termux information:", e)

def get_device_info():
    print("\n--- Device Information ---")
    try:
        # Get device info using Termux API
        device_info_output = subprocess.check_output(['termux-telephony-deviceinfo'], stderr=subprocess.STDOUT).decode()
        device_info = json.loads(device_info_output)
        for key, value in device_info.items():
            print(f"{key}: {value}")
    except Exception as e:
        print("Error retrieving device information:", e)

def list_installed_packages():
    print("\n--- Installed Packages ---")
    try:
        packages = subprocess.check_output(['pm', 'list', 'packages'], stderr=subprocess.STDOUT).decode()
        package_list = [pkg.replace('package:', '') for pkg in packages.strip().split('\n')]
        for package in package_list:
            print(package)
        return package_list
    except Exception as e:
        print("Error listing installed packages:", e)
        return []

def get_app_permissions(package_name):
    try:
        permissions_output = subprocess.check_output(['dumpsys', 'package', package_name], stderr=subprocess.STDOUT).decode()
        permissions = re.findall(r'android\.permission\.[A-Z_]+', permissions_output)
        return set(permissions)
    except Exception as e:
        # Permissions may not be accessible for all packages
        return set()

def scan_open_ports():
    print("\n--- Open Ports ---")
    try:
        scan_result = subprocess.check_output(['nmap', '-p-', '127.0.0.1'], stderr=subprocess.STDOUT).decode()
        print(scan_result)
    except Exception as e:
        print("Error scanning open ports:", e)

def monitor_network_connections():
    print("\n--- Active Network Connections ---")
    try:
        connections = psutil.net_connections()
        for conn in connections:
            laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "N/A"
            raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "N/A"
            print(f"Type: {conn.type}, Status: {conn.status}, Local Address: {laddr}, Remote Address: {raddr}")
    except Exception as e:
        print("Error monitoring network connections:", e)

def search_sensitive_files():
    print("\n--- Sensitive Files ---")
    sensitive_extensions = ['.pem', '.key', '.crt', '.cred', '.db']
    search_paths = ['/sdcard/', '/storage/emulated/0/']
    found_files = []
    for path in search_paths:
        for root, dirs, files in os.walk(path):
            for file in files:
                if any(file.endswith(ext) for ext in sensitive_extensions):
                    file_path = os.path.join(root, file)
                    found_files.append(file_path)
                    print(f"Sensitive file found: {file_path}")
    if not found_files:
        print("No sensitive files found.")

def check_security_settings():
    print("\n--- Security Settings ---")
    # Check if Developer Options are enabled
    try:
        dev_options = subprocess.check_output(['settings', 'get', 'global', 'development_settings_enabled'], stderr=subprocess.STDOUT).decode().strip()
        print("Developer Options:", "Enabled" if dev_options == '1' else "Disabled")
    except Exception as e:
        print("Error checking Developer Options:", e)
    # Check if Unknown Sources is enabled
    try:
        unknown_sources = subprocess.check_output(['settings', 'get', 'secure', 'install_non_market_apps'], stderr=subprocess.STDOUT).decode().strip()
        print("Unknown Sources:", "Enabled" if unknown_sources == '1' else "Disabled")
    except Exception as e:
        print("Error checking Unknown Sources setting:", e)
    # Check if ADB is enabled
    try:
        adb_enabled = subprocess.check_output(['settings', 'get', 'global', 'adb_enabled'], stderr=subprocess.STDOUT).decode().strip()
        print("ADB Debugging:", "Enabled" if adb_enabled == '1' else "Disabled")
    except Exception as e:
        print("Error checking ADB setting:", e)

def check_outdated_packages():
    print("\n--- Outdated Termux Packages ---")
    try:
        updates = subprocess.check_output(['pkg', 'list-upgradable'], stderr=subprocess.STDOUT).decode()
        if updates.strip():
            print("The following packages can be upgraded:")
            print(updates)
        else:
            print("All Termux packages are up to date.")
    except Exception as e:
        print("Error checking for package updates:", e)

def analyze_processes():
    print("\n--- Running Processes ---")
    try:
        suspicious_keywords = ['keylogger', 'sniff', 'spy', 'hack']
        suspicious_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username']):
            name = proc.info['name'].lower()
            if any(keyword in name for keyword in suspicious_keywords):
                suspicious_processes.append(proc.info)
        if suspicious_processes:
            print("Suspicious processes found:")
            for proc in suspicious_processes:
                print(f"PID: {proc['pid']}, Name: {proc['name']}, User: {proc['username']}")
        else:
            print("No suspicious processes detected.")
    except Exception as e:
        print("Error analyzing processes:", e)

def check_wifi_security():
    print("\n--- Wi-Fi Security Assessment ---")
    try:
        # Get Wi-Fi connection info using Termux API
        wifi_info_output = subprocess.check_output(['termux-wifi-connectioninfo'], stderr=subprocess.STDOUT).decode()
        wifi_info = json.loads(wifi_info_output)
        if 'supplicant_state' in wifi_info and wifi_info['supplicant_state'] == 'COMPLETED':
            ssid = wifi_info.get('ssid', 'Unknown')
            ip_address = wifi_info.get('ip', 'Unknown')
            mac_address = wifi_info.get('mac_address', 'Unknown')
            frequency = wifi_info.get('frequency', 'Unknown')
            link_speed = wifi_info.get('link_speed', 'Unknown')
            signal_level = wifi_info.get('rssi', 'Unknown')
            print(f"Connected to SSID: {ssid}")
            print(f"IP Address: {ip_address}")
            print(f"MAC Address: {mac_address}")
            print(f"Frequency: {frequency} MHz")
            print(f"Link Speed: {link_speed} Mbps")
            print(f"Signal Level: {signal_level} dBm")
            # Assess security (this information might not be available)
            security_info = subprocess.check_output(['termux-wifi-scaninfo'], stderr=subprocess.STDOUT).decode()
            scan_info = json.loads(security_info)
            for network in scan_info:
                if network.get('ssid') == ssid:
                    capabilities = network.get('capabilities', '')
                    print(f"Security Capabilities: {capabilities}")
                    if 'WEP' in capabilities or 'WPA' in capabilities:
                        print("Wi-Fi network is secured.")
                    else:
                        print("Warning: Wi-Fi network is not secured.")
                    break
            else:
                print("Could not find security information for the connected Wi-Fi network.")
        else:
            print("Not connected to any Wi-Fi network.")
    except Exception as e:
        print("Error assessing Wi-Fi security:", e)

def main():
    start_time = datetime.datetime.now()
    print("Starting Comprehensive Security Assessment using Termux API...\n")
    # Check if device is rooted
    print("--- Root Access Check ---")
    try:
        rooted = is_device_rooted()
        print("Device is rooted." if rooted else "Device is not rooted.")
    except Exception as e:
        print("Error checking root status:", e)
    # Get system information
    get_system_info()
    # Get device information
    get_device_info()
    # List installed packages
    installed_packages = list_installed_packages()
    # Analyze permissions for each installed app
    print("\n--- Applications and Permissions ---")
    for package_name in installed_packages:
        permissions = get_app_permissions(package_name)
        if permissions:
            print(f"\nApp: {package_name}")
            for perm in permissions:
                print(f"- {perm}")
    # Scan open ports
    scan_open_ports()
    # Monitor network connections
    monitor_network_connections()
    # Search for sensitive files
    search_sensitive_files()
    # Check security settings
    check_security_settings()
    # Check outdated packages
    check_outdated_packages()
    # Analyze running processes
    analyze_processes()
    # Assess Wi-Fi security
    check_wifi_security()
    end_time = datetime.datetime.now()
    duration = end_time - start_time
    print(f"\nSecurity Assessment Completed in {duration}.")

if __name__ == "__main__":
    main()
