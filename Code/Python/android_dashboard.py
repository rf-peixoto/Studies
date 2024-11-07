import os
import sys
import time
from datetime import datetime, timedelta
from colorama import init, Fore, Style
import psutil
import socket
import subprocess
import re

# Initialize colorama
init(autoreset=True)

def clear_screen():
    os.system('clear')

# ASCII representations of digits
digits = {
    '0': ['  ██████  ',
          ' ██    ██ ',
          ' ██    ██ ',
          ' ██    ██ ',
          ' ██    ██ ',
          ' ██    ██ ',
          '  ██████  '],
    '1': ['    ██    ',
          '   ███    ',
          '    ██    ',
          '    ██    ',
          '    ██    ',
          '    ██    ',
          '  ██████  '],
    '2': ['  ██████  ',
          ' ██    ██ ',
          '       ██ ',
          '   █████  ',
          '  ██      ',
          ' ██       ',
          ' ████████ '],
    '3': ['  ██████  ',
          ' ██    ██ ',
          '       ██ ',
          '   █████  ',
          '       ██ ',
          ' ██    ██ ',
          '  ██████  '],
    '4': ['      ██  ',
          '     ███  ',
          '    █ ██  ',
          '   █  ██  ',
          ' ████████ ',
          '      ██  ',
          '      ██  '],
    '5': [' ████████ ',
          ' ██       ',
          ' ██████   ',
          '       ██ ',
          '       ██ ',
          ' ██    ██ ',
          '  ██████  '],
    '6': ['  ██████  ',
          ' ██    ██ ',
          ' ██       ',
          ' ██████   ',
          ' ██    ██ ',
          ' ██    ██ ',
          '  ██████  '],
    '7': [' ████████ ',
          '       ██ ',
          '      ██  ',
          '     ██   ',
          '    ██    ',
          '    ██    ',
          '    ██    '],
    '8': ['  ██████  ',
          ' ██    ██ ',
          ' ██    ██ ',
          '  ██████  ',
          ' ██    ██ ',
          ' ██    ██ ',
          '  ██████  '],
    '9': ['  ██████  ',
          ' ██    ██ ',
          ' ██    ██ ',
          '  ███████ ',
          '       ██ ',
          ' ██    ██ ',
          '  ██████  '],
    ':': ['          ',
          '    ██    ',
          '    ██    ',
          '          ',
          '    ██    ',
          '    ██    ',
          '          ']
}

def get_system_info():
    sys_info = {}
    
    # CPU usage
    try:
        sys_info['cpu_usage'] = psutil.cpu_percent(interval=None)
    except Exception:
        sys_info['cpu_usage'] = 'N/A'

    # Memory usage
    try:
        memory = psutil.virtual_memory()
        sys_info['mem_total'] = memory.total // (1024 * 1024)
        sys_info['mem_used'] = memory.used // (1024 * 1024)
        sys_info['mem_percent'] = memory.percent
    except Exception:
        sys_info['mem_total'] = sys_info['mem_used'] = sys_info['mem_percent'] = 'N/A'

    # Disk usage
    try:
        disk = psutil.disk_usage('/')
        sys_info['disk_total'] = disk.total // (1024 * 1024 * 1024)
        sys_info['disk_used'] = disk.used // (1024 * 1024 * 1024)
        sys_info['disk_percent'] = disk.percent
    except Exception:
        sys_info['disk_total'] = sys_info['disk_used'] = sys_info['disk_percent'] = 'N/A'

    # Network info
    try:
        net_if_addrs = psutil.net_if_addrs()
        network_info = ''
        for interface, addrs in net_if_addrs.items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    network_info += f'{interface}: {addr.address}\n'
        sys_info['network_info'] = network_info.strip()
    except Exception:
        sys_info['network_info'] = 'N/A'

    # System uptime
    try:
        uptime_seconds = time.time() - psutil.boot_time()
        uptime_string = str(timedelta(seconds=int(uptime_seconds)))
        sys_info['uptime'] = uptime_string
    except Exception:
        sys_info['uptime'] = 'N/A'

    # Current user
    try:
        users = psutil.users()
        sys_info['current_user'] = users[0].name if users else 'Unknown'
    except Exception:
        sys_info['current_user'] = 'Unknown'

    # Battery status
    try:
        battery = psutil.sensors_battery()
        sys_info['battery_percent'] = battery.percent if battery else 'N/A'
        sys_info['battery_plugged'] = 'Charging' if battery and battery.power_plugged else 'Not Charging'
    except Exception:
        sys_info['battery_percent'] = sys_info['battery_plugged'] = 'N/A'

    # Number of running processes
    try:
        sys_info['num_processes'] = len(psutil.pids())
    except Exception:
        sys_info['num_processes'] = 'N/A'

    return sys_info

def check_security_settings():
    security_issues = []

    # Check if Developer Options are enabled
    dev_options = run_shell_command(['settings', 'get', 'global', 'development_settings_enabled'])
    if dev_options == '1':
        security_issues.append('Developer Options are ENABLED')

    # Check if USB Debugging is enabled
    usb_debugging = run_shell_command(['settings', 'get', 'global', 'adb_enabled'])
    if usb_debugging == '1':
        security_issues.append('USB Debugging is ENABLED')

    # Check if installation from unknown sources is allowed
    unknown_sources = run_shell_command(['settings', 'get', 'secure', 'install_non_market_apps'])
    if unknown_sources == '1':
        security_issues.append('Installation from unknown sources is ALLOWED')

    return security_issues

def run_shell_command(cmd):
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def get_installed_packages():
    try:
        result = run_shell_command(['pm', 'list', 'packages'])
        if result:
            packages = result.strip().split('\n')
            package_names = [pkg.replace('package:', '') for pkg in packages]
            return package_names
    except Exception:
        pass
    return []

def get_package_permissions(package_name):
    try:
        result = run_shell_command(['dumpsys', 'package', package_name])
        if result:
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
    except Exception:
        pass
    return []

def check_dangerous_permissions(permissions):
    dangerous_permissions_list = [
        'android.permission.READ_SMS',
        'android.permission.SEND_SMS',
        'android.permission.RECEIVE_SMS',
        'android.permission.RECORD_AUDIO',
        'android.permission.CAMERA',
        'android.permission.ACCESS_FINE_LOCATION',
        'android.permission.ACCESS_COARSE_LOCATION',
        'android.permission.READ_CONTACTS',
        'android.permission.WRITE_CONTACTS',
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
    dangerous = []
    for perm in permissions:
        if perm in dangerous_permissions_list:
            dangerous.append(perm)
    return dangerous

def scan_filesystem_for_sensitive_files():
    sensitive_files = []
    try:
        for root, dirs, files in os.walk('/'):
            for name in files:
                path = os.path.join(root, name)
                try:
                    mode = os.stat(path).st_mode
                    if mode & 0o0002:
                        sensitive_files.append(path)
                except Exception:
                    continue
    except Exception:
        pass
    return sensitive_files

def scan_open_ports():
    open_ports = []
    try:
        result = run_shell_command(['ss', '-tulwn'])
        if result:
            lines = result.strip().split('\n')
            for line in lines[1:]:
                open_ports.append(line)
    except Exception:
        pass
    return open_ports

def ascii_clock_dashboard():
    try:
        while True:
            clear_screen()
            now = datetime.now()
            current_time = now.strftime("%H:%M:%S")
            current_date = now.strftime("%A, %B %d, %Y")
            lines = ['', '', '', '', '', '', '']
            for char in current_time:
                for i, line in enumerate(digits.get(char, [' ' * 9]*7)):
                    lines[i] += line + '  '
            clock_display = '\n'.join(lines)
            print(Fore.CYAN + Style.BRIGHT + clock_display + Style.RESET_ALL)
            print(Fore.GREEN + Style.BRIGHT + f"\n    {current_date}" + Style.RESET_ALL)

            # Get system info
            sys_info = get_system_info()

            # Display system information
            print(Fore.YELLOW + Style.BRIGHT + "\nSystem Information:\n" + Style.RESET_ALL)
            print(f"CPU Usage: {sys_info.get('cpu_usage', 'N/A')}%")
            print(f"Memory Usage: {sys_info.get('mem_used', 'N/A')}MB / {sys_info.get('mem_total', 'N/A')}MB ({sys_info.get('mem_percent', 'N/A')}%)")
            print(f"Disk Usage: {sys_info.get('disk_used', 'N/A')}GB / {sys_info.get('disk_total', 'N/A')}GB ({sys_info.get('disk_percent', 'N/A')}%)")
            print(f"Battery: {sys_info.get('battery_percent', 'N/A')}% ({sys_info.get('battery_plugged', 'N/A')})")
            print(f"Processes Running: {sys_info.get('num_processes', 'N/A')}")
            print(f"Network Interfaces:\n{sys_info.get('network_info', 'N/A')}")
            print(f"System Uptime: {sys_info.get('uptime', 'N/A')}")
            print(f"Current User: {sys_info.get('current_user', 'N/A')}")

            # Security checks
            security_issues = check_security_settings()
            if security_issues:
                print(Fore.RED + Style.BRIGHT + "\nSecurity Issues:" + Style.RESET_ALL)
                for issue in security_issues:
                    print(Fore.RED + f"- {issue}")
            else:
                print(Fore.GREEN + Style.BRIGHT + "\nNo Security Issues Detected" + Style.RESET_ALL)

            # Deeper security scans
            print(Fore.YELLOW + Style.BRIGHT + "\nPerforming Deep Security Scans...\n" + Style.RESET_ALL)

            # Application Analysis
            installed_packages = get_installed_packages()
            apps_with_dangerous_perms = []
            for package in installed_packages:
                permissions = get_package_permissions(package)
                dangerous_perms = check_dangerous_permissions(permissions)
                if dangerous_perms:
                    apps_with_dangerous_perms.append({'package': package, 'permissions': dangerous_perms})
            if apps_with_dangerous_perms:
                print(Fore.RED + "Applications with Dangerous Permissions:" + Style.RESET_ALL)
                for app in apps_with_dangerous_perms:
                    print(f"- {app['package']}: {', '.join(app['permissions'])}")
            else:
                print(Fore.GREEN + "No applications with dangerous permissions found." + Style.RESET_ALL)

            # Filesystem Scan
            sensitive_files = scan_filesystem_for_sensitive_files()
            if sensitive_files:
                print(Fore.RED + "\nSensitive Files with Insecure Permissions:" + Style.RESET_ALL)
                for file in sensitive_files:
                    print(f"- {file}")
            else:
                print(Fore.GREEN + "\nNo sensitive files with insecure permissions found." + Style.RESET_ALL)

            # Open Ports
            open_ports = scan_open_ports()
            if open_ports:
                print(Fore.RED + "\nOpen Ports Detected:" + Style.RESET_ALL)
                for port_info in open_ports:
                    print(f"- {port_info}")
            else:
                print(Fore.GREEN + "\nNo open ports detected." + Style.RESET_ALL)

            # Wait before updating
            time.sleep(5)
    except KeyboardInterrupt:
        clear_screen()
        sys.exit()
    except Exception:
        # In case of an unexpected error, clear screen and exit gracefully
        clear_screen()
        print(Fore.RED + "An unexpected error occurred. Exiting.")
        sys.exit()

if __name__ == "__main__":
    ascii_clock_dashboard()
