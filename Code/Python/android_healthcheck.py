import subprocess
import re
import os
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

# Define color shortcuts
INFO = Fore.CYAN + Style.BRIGHT
WARNING = Fore.YELLOW + Style.BRIGHT
DANGER = Fore.RED + Style.BRIGHT
SUCCESS = Fore.GREEN + Style.BRIGHT
RESET = Style.RESET_ALL

# List of dangerous permissions to check for
DANGEROUS_PERMISSIONS = [
    'android.permission.READ_SMS',
    'android.permission.SEND_SMS',
    'android.permission.RECEIVE_SMS',
    'android.permission.RECORD_AUDIO',
    'android.permission.CAMERA',
    'android.permission.READ_CONTACTS',
    'android.permission.WRITE_CONTACTS',
    'android.permission.ACCESS_FINE_LOCATION',
    'android.permission.ACCESS_COARSE_LOCATION',
    'android.permission.READ_CALL_LOG',
    'android.permission.WRITE_CALL_LOG',
    'android.permission.CALL_PHONE',
    'android.permission.PROCESS_OUTGOING_CALLS',
    'android.permission.READ_PHONE_STATE',
    'android.permission.READ_EXTERNAL_STORAGE',
    'android.permission.WRITE_EXTERNAL_STORAGE',
    'android.permission.SYSTEM_ALERT_WINDOW',
    'android.permission.WRITE_SETTINGS',
    'android.permission.CHANGE_WIFI_STATE',
    'android.permission.ACCESS_WIFI_STATE',
    'android.permission.ACCESS_NETWORK_STATE',
    'android.permission.INTERNET',
    'android.permission.RECEIVE_BOOT_COMPLETED',
    'android.permission.BIND_ACCESSIBILITY_SERVICE',
    'android.permission.REQUEST_INSTALL_PACKAGES',
    'android.permission.PACKAGE_USAGE_STATS',
    'android.permission.READ_PHONE_NUMBERS',
    'android.permission.USE_SIP',
    'android.permission.FOREGROUND_SERVICE',
    'android.permission.BIND_DEVICE_ADMIN',
    'android.permission.BLUETOOTH',
    'android.permission.NFC',
    'android.permission.ACCESS_BACKGROUND_LOCATION'
]

def run_shell_command(cmd):
    """Utility function to run shell commands."""
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()

def get_installed_packages():
    """Retrieve a list of installed packages and their APK paths."""
    result = run_shell_command(['pm', 'list', 'packages', '-f'])
    packages = result.strip().split('\n')
    package_info = []
    for pkg in packages:
        match = re.match(r'package:(.*)=(.*)', pkg)
        if match:
            apk_path, package_name = match.groups()
            package_info.append({'package_name': package_name, 'apk_path': apk_path})
    return package_info

def get_package_permissions(package_name):
    """Get the list of permissions requested by a package."""
    result = run_shell_command(['dumpsys', 'package', package_name])
    permissions = []
    lines = result.strip().split('\n')
    in_permissions = False
    for line in lines:
        line = line.strip()
        if line.startswith('requested permissions:'):
            in_permissions = True
            continue
        if in_permissions:
            if not line or not line.startswith('android.permission'):
                break
            perm = line.strip()
            permissions.append(perm)
    return permissions

def check_dangerous_permissions(permissions):
    """Identify any dangerous permissions from the list."""
    dangerous = []
    for perm in permissions:
        if perm in DANGEROUS_PERMISSIONS:
            dangerous.append(perm)
    return dangerous

def check_developer_options():
    """Check if Developer Options are enabled."""
    result = run_shell_command(['settings', 'get', 'global', 'development_settings_enabled'])
    return result == '1'

def check_usb_debugging():
    """Check if USB Debugging is enabled."""
    result = run_shell_command(['settings', 'get', 'global', 'adb_enabled'])
    return result == '1'

def check_unknown_sources():
    """Check if installation from unknown sources is allowed."""
    result = run_shell_command(['settings', 'get', 'secure', 'install_non_market_apps'])
    return result == '1'

def check_screen_lock():
    """Check if screen lock is enabled."""
    result = run_shell_command(['dumpsys', 'device_policy'])
    if 'Password quality: NONE' in result:
        return False
    else:
        return True

def check_encryption():
    """Check if device encryption is enabled."""
    result = run_shell_command(['dumpsys', 'mount'])
    return 'State: encrypted' in result or 'Encryption Status: encrypted' in result

def get_security_patch_level():
    """Get the security patch level of the device."""
    result = run_shell_command(['getprop', 'ro.build.version.security_patch'])
    return result

def get_active_network_interfaces():
    """List active network interfaces."""
    interfaces = os.listdir('/sys/class/net/')
    return interfaces

def get_open_connections():
    """List open network connections."""
    result = run_shell_command(['ss', '-tulwn'])
    return result

def check_accessibility_services():
    """List enabled accessibility services."""
    result = run_shell_command(['settings', 'get', 'secure', 'enabled_accessibility_services'])
    return result

def get_default_apps():
    """Get default SMS and dialer applications."""
    sms_app = run_shell_command(['settings', 'get', 'secure', 'sms_default_application'])
    dialer_app = run_shell_command(['settings', 'get', 'secure', 'dialer_default_application'])
    return sms_app, dialer_app

def get_running_apps():
    """List running applications."""
    result = run_shell_command(['ps', '-A'])
    processes = result.strip().split('\n')
    return processes

def check_device_admin_apps():
    """List apps with device administrator privileges."""
    result = run_shell_command(['dumpsys', 'device_policy'])
    admin_apps = re.findall(r'admin=\{(.*?)/', result)
    return admin_apps

def check_vpn_status():
    """Check if a VPN is active."""
    result = run_shell_command(['dumpsys', 'connectivity'])
    return 'VPN' in result

def check_call_forwarding():
    """Check call forwarding settings (limited without root)."""
    # Limited functionality due to permissions
    return "Unable to check without root access."

def check_saved_wifi_networks():
    """List saved Wi-Fi networks (limited without root)."""
    result = run_shell_command(['dumpsys', 'wifi'])
    networks = re.findall(r'SSID: (\S+)', result)
    return networks

def check_installed_from_unknown_sources(package_name):
    """Check if an app was installed from unknown sources."""
    result = run_shell_command(['dumpsys', 'package', package_name])
    return 'installerPackageName=null' in result

def check_bluetooth_status():
    """Check if Bluetooth is enabled."""
    result = run_shell_command(['settings', 'get', 'global', 'bluetooth_on'])
    return result == '1'

def check_nfc_status():
    """Check if NFC is enabled."""
    result = run_shell_command(['settings', 'get', 'global', 'nfc_on'])
    return result == '1'

def check_mock_location_apps():
    """List apps allowed to mock location data."""
    result = run_shell_command(['settings', 'get', 'secure', 'mock_location_app'])
    return result

def check_app_updates(package_name):
    """Check if an app has pending updates (limited without root)."""
    # Placeholder function; actual implementation requires root or Play Store API access
    return "Unable to check without appropriate permissions."

def check_certificate_validity(apk_path):
    """Check if the app's certificate is valid (limited without root)."""
    # Placeholder function; actual implementation requires parsing the APK file
    return "Unable to check without appropriate permissions."

def analyze_battery_usage():
    """Identify apps with high battery usage (limited without root)."""
    result = run_shell_command(['dumpsys', 'batterystats'])
    # Simplified example; detailed analysis requires more complex parsing
    return result

def analyze_data_usage():
    """List apps with high data consumption (limited without root)."""
    result = run_shell_command(['dumpsys', 'netstats'])
    # Simplified example; detailed analysis requires more complex parsing
    return result

def main():
    print(INFO + "Starting security and privacy checks...\n")
    
    # Check Developer Options
    if check_developer_options():
        print(DANGER + "[!] Developer Options are ENABLED.")
    else:
        print(SUCCESS + "[+] Developer Options are disabled.")
    
    # Check USB Debugging
    if check_usb_debugging():
        print(DANGER + "[!] USB Debugging is ENABLED.")
    else:
        print(SUCCESS + "[+] USB Debugging is disabled.")
    
    # Check Unknown Sources
    if check_unknown_sources():
        print(DANGER + "[!] Installation from unknown sources is ALLOWED.")
    else:
        print(SUCCESS + "[+] Installation from unknown sources is not allowed.")
    
    # Check Screen Lock
    if check_screen_lock():
        print(SUCCESS + "[+] Screen lock is enabled.")
    else:
        print(DANGER + "[!] Screen lock is NOT enabled.")
    
    # Check Device Encryption
    if check_encryption():
        print(SUCCESS + "[+] Device encryption is enabled.")
    else:
        print(DANGER + "[!] Device encryption is NOT enabled.")
    
    # Get Security Patch Level
    patch_level = get_security_patch_level()
    print(INFO + f"[i] Security Patch Level: {patch_level}")
    
    # Check Bluetooth Status
    if check_bluetooth_status():
        print(WARNING + "[!] Bluetooth is ENABLED.")
    else:
        print(SUCCESS + "[+] Bluetooth is disabled.")
    
    # Check NFC Status
    if check_nfc_status():
        print(WARNING + "[!] NFC is ENABLED.")
    else:
        print(SUCCESS + "[+] NFC is disabled.")
    
    # Check Mock Location Apps
    mock_location_app = check_mock_location_apps()
    if mock_location_app and mock_location_app != 'null':
        print(WARNING + f"[!] Mock location app detected: {mock_location_app}")
    else:
        print(SUCCESS + "[+] No mock location apps are set.")
    
    print(INFO + "\nAnalyzing network configurations...\n")
    
    # Active Network Interfaces
    interfaces = get_active_network_interfaces()
    print(INFO + f"[i] Active Network Interfaces: {', '.join(interfaces)}")
    
    # Open Network Connections
    connections = get_open_connections()
    print(INFO + f"[i] Open Network Connections:\n{connections}")
    
    # Check VPN Status
    if check_vpn_status():
        print(SUCCESS + "[i] VPN is active.")
    else:
        print(WARNING + "[i] VPN is not active.")
    
    # Saved Wi-Fi Networks
    wifi_networks = check_saved_wifi_networks()
    if wifi_networks:
        print(INFO + "[i] Saved Wi-Fi Networks:")
        for network in wifi_networks:
            print(f"    - {network}")
    else:
        print(INFO + "[i] No saved Wi-Fi networks found or access is restricted.")
    
    print(INFO + "\nChecking phone and messaging settings...\n")
    
    # Default SMS and Dialer Apps
    sms_app, dialer_app = get_default_apps()
    print(INFO + f"[i] Default SMS App: {sms_app}")
    print(INFO + f"[i] Default Dialer App: {dialer_app}")
    
    # Call Forwarding Settings
    call_forwarding = check_call_forwarding()
    print(INFO + f"[i] Call Forwarding Settings: {call_forwarding}")
    
    print(INFO + "\nAnalyzing installed applications...\n")
    
    permission_usage = {perm: 0 for perm in DANGEROUS_PERMISSIONS}
    
    packages = get_installed_packages()
    for pkg in packages:
        permissions = get_package_permissions(pkg['package_name'])
        dangerous_perms = check_dangerous_permissions(permissions)
        installed_from_unknown = check_installed_from_unknown_sources(pkg['package_name'])
        # Update permission usage count
        for perm in dangerous_perms:
            permission_usage[perm] += 1
        if dangerous_perms or installed_from_unknown:
            print(WARNING + f"[!] {pkg['package_name']} has potential risks:")
            if dangerous_perms:
                print(INFO + f"    Dangerous Permissions:")
                for perm in dangerous_perms:
                    print(f"        - {perm}")
            if installed_from_unknown:
                print(DANGER + "    Installed from unknown sources.")
        else:
            print(SUCCESS + f"[+] {pkg['package_name']} has no immediate risks.")
    
    # Permission Usage Analysis
    print(INFO + "\nAnalyzing permission usage across all apps...\n")
    for perm, count in permission_usage.items():
        if count > 0:
            print(INFO + f"[i] Permission {perm} is used by {count} apps.")
    
    # Battery Usage Analysis
    print(INFO + "\nAnalyzing battery usage...\n")
    battery_usage = analyze_battery_usage()
    print(INFO + battery_usage)
    
    # Data Usage Analysis
    print(INFO + "\nAnalyzing data usage...\n")
    data_usage = analyze_data_usage()
    print(INFO + data_usage)
    
    print(INFO + "\nChecking accessibility services...\n")
    
    accessibility_services = check_accessibility_services()
    if accessibility_services and accessibility_services != 'null':
        print(WARNING + f"[!] Enabled Accessibility Services:\n{accessibility_services}")
    else:
        print(SUCCESS + "[+] No third-party accessibility services enabled.")
    
    print(INFO + "\nChecking device administrator apps...\n")
    
    admin_apps = check_device_admin_apps()
    if admin_apps:
        print(WARNING + "[!] Apps with Device Administrator privileges:")
        for app in admin_apps:
            print(f"    - {app}")
    else:
        print(SUCCESS + "[+] No apps with Device Administrator privileges found.")
    
    print(INFO + "\nListing running applications...\n")
    
    running_apps = get_running_apps()
    for app in running_apps:
        print(app)
    
    print(SUCCESS + "\nSecurity and privacy check completed.")

if __name__ == '__main__':
    main()
