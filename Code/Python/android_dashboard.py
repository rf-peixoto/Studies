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
    # Simplify error handling by using default values
    # CPU usage
    cpu_usage = psutil.cpu_percent(interval=None)

    # Memory usage
    memory = psutil.virtual_memory()
    mem_total = memory.total // (1024 * 1024)
    mem_used = memory.used // (1024 * 1024)
    mem_percent = memory.percent

    # Disk usage
    disk = psutil.disk_usage('/')
    disk_total = disk.total // (1024 * 1024 * 1024)
    disk_used = disk.used // (1024 * 1024 * 1024)
    disk_percent = disk.percent

    # Network info
    net_if_addrs = psutil.net_if_addrs()
    network_info = ''
    for interface, addrs in net_if_addrs.items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                network_info += f'{interface}: {addr.address}\n'

    # System uptime
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_string = str(timedelta(seconds=int(uptime_seconds)))

    # Current user
    users = psutil.users()
    current_user = users[0].name if users else 'Unknown'

    # Battery status
    battery = psutil.sensors_battery()
    battery_percent = battery.percent if battery else 'N/A'
    battery_plugged = 'Charging' if battery and battery.power_plugged else 'Not Charging'

    # Number of running processes
    num_processes = len(psutil.pids())

    # Return collected info
    return {
        'cpu_usage': cpu_usage,
        'mem_total': mem_total,
        'mem_used': mem_used,
        'mem_percent': mem_percent,
        'disk_total': disk_total,
        'disk_used': disk_used,
        'disk_percent': disk_percent,
        'network_info': network_info.strip(),
        'uptime': uptime_string,
        'current_user': current_user,
        'battery_percent': battery_percent,
        'battery_plugged': battery_plugged,
        'num_processes': num_processes,
    }

def check_security_settings():
    # Perform basic security checks
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

    # Return the list of security issues found
    return security_issues

def run_shell_command(cmd):
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return None

def ascii_clock_dashboard():
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
        print(f"CPU Usage: {sys_info['cpu_usage']}%")
        print(f"Memory Usage: {sys_info['mem_used']}MB / {sys_info['mem_total']}MB ({sys_info['mem_percent']}%)")
        print(f"Disk Usage: {sys_info['disk_used']}GB / {sys_info['disk_total']}GB ({sys_info['disk_percent']}%)")
        print(f"Battery: {sys_info['battery_percent']}% ({sys_info['battery_plugged']})")
        print(f"Processes Running: {sys_info['num_processes']}")
        print(f"Network Interfaces:\n{sys_info['network_info']}")
        print(f"System Uptime: {sys_info['uptime']}")
        print(f"Current User: {sys_info['current_user']}")

        # Security checks
        security_issues = check_security_settings()
        print(Fore.RED + Style.BRIGHT + "\nSecurity Issues:" + Style.RESET_ALL if security_issues else Fore.GREEN + Style.BRIGHT + "\nNo Security Issues Detected" + Style.RESET_ALL)
        for issue in security_issues:
            print(Fore.RED + f"- {issue}")

        # Wait before updating
        time.sleep(5)

if __name__ == "__main__":
    try:
        ascii_clock_dashboard()
    except KeyboardInterrupt:
        clear_screen()
        sys.exit()
