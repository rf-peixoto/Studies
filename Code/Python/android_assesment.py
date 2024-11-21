import os
import platform
import subprocess
import socket
import psutil
import re

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
        print("System:", platform.system())
        print("Node Name:", platform.node())
        print("Release:", platform.release())
        print("Version:", platform.version())
        print("Machine:", platform.machine())
        print("Processor:", platform.processor())
    except Exception as e:
        print("Error retrieving system information:", e)

def list_installed_packages():
    print("\n--- Installed Packages ---")
    try:
        packages = subprocess.check_output(['pm', 'list', 'packages'], stderr=subprocess.STDOUT).decode()
        package_list = packages.strip().split('\n')
        for package in package_list:
            print(package.replace('package:', ''))
    except Exception as e:
        print("Error listing installed packages:", e)

def get_app_permissions(package_name):
    try:
        permissions_output = subprocess.check_output(['dumpsys', 'package', package_name], stderr=subprocess.STDOUT).decode()
        permissions = re.findall(r'android.permission.[A-Z_]+', permissions_output)
        return set(permissions)
    except Exception as e:
        print(f"Error retrieving permissions for {package_name}:", e)
        return set()

def scan_open_ports():
    print("\n--- Open Ports ---")
    try:
        scan_result = subprocess.check_output(['nmap', '-p-', 'localhost'], stderr=subprocess.STDOUT).decode()
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
                    found_files.append(os.path.join(root, file))
    if found_files:
        for file in found_files:
            print(f"Sensitive file found: {file}")
    else:
        print("No sensitive files found.")
    if not found_files:
        print("Ensure you have storage permissions enabled for Termux.")

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
        unknown_sources = subprocess.check_output(['settings', 'get', 'global', 'install_non_market_apps'], stderr=subprocess.STDOUT).decode().strip()
        print("Unknown Sources:", "Enabled" if unknown_sources == '1' else "Disabled")
    except Exception as e:
        print("Error checking Unknown Sources setting:", e)

def main():
    print("Starting Security Assessment...\n")
    # Check if device is rooted
    print("--- Root Access Check ---")
    try:
        rooted = is_device_rooted()
        print("Device is rooted." if rooted else "Device is not rooted.")
    except Exception as e:
        print("Error checking root status:", e)
    # Get system information
    get_system_info()
    # List installed packages
    list_installed_packages()
    # Analyze permissions for a specific app (e.g., Termux)
    package_name = 'com.termux'
    print(f"\n--- Permissions for {package_name} ---")
    permissions = get_app_permissions(package_name)
    if permissions:
        for perm in permissions:
            print(perm)
    else:
        print(f"No permissions found or cannot retrieve permissions for {package_name}.")
    # Scan open ports
    scan_open_ports()
    # Monitor network connections
    monitor_network_connections()
    # Search for sensitive files
    search_sensitive_files()
    # Check security settings
    check_security_settings()
    print("\nSecurity Assessment Completed.")

if __name__ == "__main__":
    main()
