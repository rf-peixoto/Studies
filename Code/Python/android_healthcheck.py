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
    """Utility function to run shell commands with error handling."""
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(DANGER + f"Error executing command {' '.join(cmd)}: {result.stderr.strip()}")
            return None
        return result.stdout.strip()
    except Exception as e:
        print(DANGER + f"Exception occurred while executing command {' '.join(cmd)}: {str(e)}")
        return None

def get_installed_packages():
    """Retrieve a list of installed packages and their APK paths."""
    result = run_shell_command(['pm', 'list', 'packages', '-f'])
    if result is None:
        print(DANGER + "Failed to retrieve installed packages.")
        return []
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
    if result is None:
        print(DANGER + f"Failed to get permissions for package: {package_name}")
        return []
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
    if result is None:
        print(DANGER + "Failed to check Developer Options status.")
        return False
    return result == '1'

def check_usb_debugging():
    """Check if USB Debugging is enabled."""
    result = run_shell_command(['settings', 'get', 'global', 'adb_enabled'])
    if result is None:
        print(DANGER + "Failed to check USB Debugging status.")
        return False
    return result == '1'

def check_unknown_sources():
    """Check if installation from unknown sources is allowed."""
    result = run_shell_command(['settings', 'get', 'secure', 'install_non_market_apps'])
    if result is None:
        print(DANGER + "Failed to check Unknown Sources setting.")
        return False
    return result == '1'

def check_screen_lock():
    """Check if screen lock is enabled."""
    result = run_shell_command(['dumpsys', 'device_policy'])
    if result is None:
        print(DANGER + "Failed to check Screen Lock status.")
        return False
    if 'Password quality: NONE' in result or 'mPasswordQuality=0' in result:
        return False
    else:
        return True

def check_encryption():
    """Check if device encryption is enabled."""
    result = run_shell_command(['dumpsys', 'mount'])
    if result is None:
        print(DANGER + "Failed to check Encryption status.")
        return False
    return 'State: encrypted' in result or 'Encryption Status: encrypted' in result

def get_security_patch_level():
    """Get the security patch level of the device."""
    result = run_shell_command(['getprop', 'ro.build.version.security_patch'])
    if result is None:
        return "Unknown"
    return result

def get_active_network_interfaces():
    """List active network interfaces."""
    try:
        interfaces = os.listdir('/sys/class/net/')
        return interfaces
    except Exception as e:
        print(DANGER + f"Failed to list network interfaces: {str(e)}")
        return []

def get_open_connections():
    """List open network connections."""
    result = run_shell_command(['ss', '-tulwn'])
    if result is None:
        print(DANGER + "Failed to get open network connections.")
        return ""
    return result

def check_accessibility_services():
    """List enabled accessibility services."""
    result = run_shell_command(['settings', 'get', 'secure', 'enabled_accessibility_services'])
    if result is None:
        print(DANGER + "Failed to check Accessibility Services.")
        return ""
    return result

def get_default_apps():
    """Get default SMS and dialer applications."""
    sms_app = run_shell_command(['settings', 'get', 'secure', 'sms_default_application'])
    if sms_app is None:
        sms_app = "Unknown"
    dialer_app = run_shell_command(['settings', 'get', 'secure', 'dialer_default_application'])
    if dialer_app is None:
        dialer_app = "Unknown"
    return sms_app, dialer_app

def get_running_apps():
    """List running applications."""
    result = run_shell_command(['ps', '-A'])
    if result is None:
        print(DANGER + "Failed to list running applications.")
        return []
    processes = result.strip().split('\n')
    return processes

def check_device_admin_apps():
    """List apps with device administrator privileges."""
    result = run_shell_command(['dumpsys', 'device_policy'])
    if result is None:
        print(DANGER + "Failed to check Device Administrator apps.")
        return []
    admin_apps = re.findall(r'admin=\{(.*?)/', result)
    return admin_apps

def check_vpn_status():
    """Check if a VPN is active."""
    result = run_shell_command(['dumpsys', 'connectivity'])
    if result is None:
        print(DANGER + "Failed to check VPN status.")
        return False
    return 'VPN' in result

def check_call_forwarding():
    """Check call forwarding settings (limited without root)."""
    # Limited functionality due to permissions
    return "Unable to check without root access."

def check_saved_wifi_networks():
    """List saved Wi-Fi networks (limited without root)."""
    result = run_shell_command(['dumpsys', 'wifi'])
    if result is None:
        print(DANGER + "Failed to check saved Wi-Fi networks.")
        return []
    networks = re.findall(r'SSID: (\S+)', result)
    return networks

def check_installed_from_unknown_sources(package_name):
    """Check if an app was installed from unknown sources."""
    result = run_shell_command(['dumpsys', 'package', package_name])
    if result is None:
        # Assume it's from known sources if we can't determine
        return False
    return 'installerPackageName=null' in result

def check_bluetooth_status():
    """Check if Bluetooth is enabled."""
    result = run_shell_command(['settings', 'get', 'global', 'bluetooth_on'])
    if result is None:
        print(DANGER + "Failed to check Bluetooth status.")
        return False
    return result == '1'

def check_nfc_status():
    """Check if NFC is enabled."""
    result = run_shell_command(['settings', 'get', 'global', 'nfc_on'])
    if result is None:
        print(DANGER + "Failed to check NFC status.")
        return False
    return result == '1'

def check_mock_location_apps():
    """List apps allowed to mock location data."""
    result = run_shell_command(['settings', 'get', 'secure', 'mock_location_app'])
    if result is None:
        print(DANGER + "Failed to check for mock location apps.")
        return ""
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
    if result is None:
        print(DANGER + "Failed to analyze battery usage.")
        return ""
    # Simplified example; detailed analysis requires more complex parsing
    return result

def analyze_data_usage():
    """List apps with high data consumption (limited without root)."""
    result = run_shell_command(['dumpsys', 'netstats'])
    if result is None:
        print(DANGER + "Failed to analyze data usage.")
        return ""
    # Simplified example; detailed analysis requires more complex parsing
    return result

def main():
    print(INFO + "Starting security and privacy checks...\n")
    
    # Check Developer Options
    try:
        if check_developer_options():
            print(DANGER + "[!] Developer Options are ENABLED.")
        else:
            print(SUCCESS + "[+] Developer Options are disabled.")
    except Exception as e:
        print(DANGER + f"Error checking Developer Options: {str(e)}")
    
    # Check USB Debugging
    try:
        if check_usb_debugging():
            print(DANGER + "[!] USB Debugging is ENABLED.")
        else:
            print(SUCCESS + "[+] USB Debugging is disabled.")
    except Exception as e:
        print(DANGER + f"Error checking USB Debugging: {str(e)}")
    
    # Check Unknown Sources
    try:
        if check_unknown_sources():
            print(DANGER + "[!] Installation from unknown sources is ALLOWED.")
        else:
            print(SUCCESS + "[+] Installation from unknown sources is not allowed.")
    except Exception as e:
        print(DANGER + f"Error checking Unknown Sources: {str(e)}")
    
    # Check Screen Lock
    try:
        if check_screen_lock():
            print(SUCCESS + "[+] Screen lock is enabled.")
        else:
            print(DANGER + "[!] Screen lock is NOT enabled.")
    except Exception as e:
        print(DANGER + f"Error checking Screen Lock: {str(e)}")
    
    # Check Device Encryption
    try:
        if check_encryption():
            print(SUCCESS + "[+] Device encryption is enabled.")
        else:
            print(DANGER + "[!] Device encryption is NOT enabled.")
    except Exception as e:
        print(DANGER + f"Error checking Encryption status: {str(e)}")
    
    # Get Security Patch Level
    patch_level = get_security_patch_level()
    print(INFO + f"[i] Security Patch Level: {patch_level}")
    
    # Check Bluetooth Status
    try:
        if check_bluetooth_status():
            print(WARNING + "[!] Bluetooth is ENABLED.")
        else:
            print(SUCCESS + "[+] Bluetooth is disabled.")
    except Exception as e:
        print(DANGER + f"Error checking Bluetooth status: {str(e)}")
    
    # Check NFC Status
    try:
        if check_nfc_status():
            print(WARNING + "[!] NFC is ENABLED.")
        else:
            print(SUCCESS + "[+] NFC is disabled.")
    except Exception as e:
        print(DANGER + f"Error checking NFC status: {str(e)}")
    
    # Check Mock Location Apps
    try:
        mock_location_app = check_mock_location_apps()
        if mock_location_app and mock_location_app != 'null':
            print(WARNING + f"[!] Mock location app detected: {mock_location_app}")
        else:
            print(SUCCESS + "[+] No mock location apps are set.")
    except Exception as e:
        print(DANGER + f"Error checking for Mock Location apps: {str(e)}")
    
    print(INFO + "\nAnalyzing network configurations...\n")
    
    # Active Network Interfaces
    try:
        interfaces = get_active_network_interfaces()
        print(INFO + f"[i] Active Network Interfaces: {', '.join(interfaces)}")
    except Exception as e:
        print(DANGER + f"Error listing network interfaces: {str(e)}")
    
    # Open Network Connections
    try:
        connections = get_open_connections()
        print(INFO + f"[i] Open Network Connections:\n{connections}")
    except Exception as e:
        print(DANGER + f"Error getting open network connections: {str(e)}")
    
    # Check VPN Status
    try:
        if check_vpn_status():
            print(SUCCESS + "[i] VPN is active.")
        else:
            print(WARNING + "[i] VPN is not active.")
    except Exception as e:
        print(DANGER + f"Error checking VPN status: {str(e)}")
    
    # Saved Wi-Fi Networks
    try:
        wifi_networks = check_saved_wifi_networks()
        if wifi_networks:
            print(INFO + "[i] Saved Wi-Fi Networks:")
            for network in wifi_networks:
                print(f"    - {network}")
        else:
            print(INFO + "[i] No saved Wi-Fi networks found or access is restricted.")
    except Exception as e:
        print(DANGER + f"Error retrieving saved Wi-Fi networks: {str(e)}")
    
    print(INFO + "\nChecking phone and messaging settings...\n")
    
    # Default SMS and Dialer Apps
    try:
        sms_app, dialer_app = get_default_apps()
        print(INFO + f"[i] Default SMS App: {sms_app}")
        print(INFO + f"[i] Default Dialer App: {dialer_app}")
    except Exception as e:
        print(DANGER + f"Error getting default apps: {str(e)}")
    
    # Call Forwarding Settings
    call_forwarding = check_call_forwarding()
    print(INFO + f"[i] Call Forwarding Settings: {call_forwarding}")
    
    print(INFO + "\nAnalyzing installed applications...\n")
    
    permission_usage = {perm: 0 for perm in DANGEROUS_PERMISSIONS}
    
    try:
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
    except Exception as e:
        print(DANGER + f"Error analyzing installed applications: {str(e)}")
    
    # Permission Usage Analysis
    print(INFO + "\nAnalyzing permission usage across all apps...\n")
    try:
        for perm, count in permission_usage.items():
            if count > 0:
                print(INFO + f"[i] Permission {perm} is used by {count} apps.")
    except Exception as e:
        print(DANGER + f"Error analyzing permission usage: {str(e)}")
    
    # Battery Usage Analysis
    print(INFO + "\nAnalyzing battery usage...\n")
    try:
        battery_usage = analyze_battery_usage()
        print(INFO + battery_usage)
    except Exception as e:
        print(DANGER + f"Error analyzing battery usage: {str(e)}")
    
    # Data Usage Analysis
    print(INFO + "\nAnalyzing data usage...\n")
    try:
        data_usage = analyze_data_usage()
        print(INFO + data_usage)
    except Exception as e:
        print(DANGER + f"Error analyzing data usage: {str(e)}")
    
    print(INFO + "\nChecking accessibility services...\n")
    
    try:
        accessibility_services = check_accessibility_services()
        if accessibility_services and accessibility_services != 'null':
            print(WARNING + f"[!] Enabled Accessibility Services:\n{accessibility_services}")
        else:
            print(SUCCESS + "[+] No third-party accessibility services enabled.")
    except Exception as e:
        print(DANGER + f"Error checking accessibility services: {str(e)}")
    
    print(INFO + "\nChecking device administrator apps...\n")
    
    try:
        admin_apps = check_device_admin_apps()
        if admin_apps:
            print(WARNING + "[!] Apps with Device Administrator privileges:")
            for app in admin_apps:
                print(f"    - {app}")
        else:
            print(SUCCESS + "[+] No apps with Device Administrator privileges found.")
    except Exception as e:
        print(DANGER + f"Error checking device administrator apps: {str(e)}")
    
    print(INFO + "\nListing running applications...\n")
    
    try:
        running_apps = get_running_apps()
        for app in running_apps:
            print(app)
    except Exception as e:
        print(DANGER + f"Error listing running applications: {str(e)}")
    
    print(SUCCESS + "\nSecurity and privacy check completed.")
    
if __name__ == '__main__':
    main()
