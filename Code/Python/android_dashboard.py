import os
import sys
import time
from datetime import datetime, timedelta
from colorama import init, Fore, Style
import psutil
import socket

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
    try:
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
        if users:
            current_user = users[0].name
        else:
            current_user = 'Unknown'
        
        # Battery status
        battery = psutil.sensors_battery()
        if battery:
            battery_percent = battery.percent
            battery_plugged = 'Charging' if battery.power_plugged else 'Not Charging'
            battery_time_left = str(timedelta(seconds=battery.secsleft)) if battery.secsleft != psutil.POWER_TIME_UNLIMITED else 'Unlimited'
        else:
            battery_percent = 'N/A'
            battery_plugged = 'N/A'
            battery_time_left = 'N/A'
        
        # Number of running processes
        num_processes = len(psutil.pids())
        
        # Top CPU-consuming process
        processes = [(p.pid, p.info['name'], p.info['cpu_percent']) for p in psutil.process_iter(['name', 'cpu_percent'])]
        top_process = max(processes, key=lambda x: x[2]) if processes else ('N/A', 'N/A', 0)
        
        # Wi-Fi connection status
        wifi_status = 'Disconnected'
        wifi_ssid = 'N/A'
        try:
            # This command works on Android Termux to get Wi-Fi SSID
            wifi_info = os.popen('dumpsys wifi').read()
            match = re.search(r'SSID: (.+)', wifi_info)
            if match:
                wifi_ssid = match.group(1)
                wifi_status = 'Connected'
        except Exception:
            pass
        
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
            'battery_time_left': battery_time_left,
            'num_processes': num_processes,
            'top_process': top_process,
            'wifi_status': wifi_status,
            'wifi_ssid': wifi_ssid
        }
    except Exception as e:
        print(Fore.RED + f"Error retrieving system info: {e}" + Style.RESET_ALL)
        return None

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
            if sys_info:
                print(Fore.YELLOW + Style.BRIGHT + "\nSystem Information:\n" + Style.RESET_ALL)
                print(f"CPU Usage: {sys_info['cpu_usage']}%")
                print(f"Memory Usage: {sys_info['mem_used']}MB / {sys_info['mem_total']}MB ({sys_info['mem_percent']}%)")
                print(f"Disk Usage: {sys_info['disk_used']}GB / {sys_info['disk_total']}GB ({sys_info['disk_percent']}%)")
                print(f"Battery: {sys_info['battery_percent']}% ({sys_info['battery_plugged']})")
                print(f"Processes Running: {sys_info['num_processes']}")
                print(f"Top Process: PID {sys_info['top_process'][0]} - {sys_info['top_process'][1]} ({sys_info['top_process'][2]}% CPU)")
                print(f"Wi-Fi Status: {sys_info['wifi_status']}")
                if sys_info['wifi_status'] == 'Connected':
                    print(f"Wi-Fi SSID: {sys_info['wifi_ssid']}")
                print(f"Network Interfaces:\n{sys_info['network_info']}")
                print(f"System Uptime: {sys_info['uptime']}")
                print(f"Current User: {sys_info['current_user']}")
            else:
                print(Fore.RED + "Failed to retrieve system information." + Style.RESET_ALL)
            
            time.sleep(1)
    except KeyboardInterrupt:
        clear_screen()
        sys.exit()
    except Exception as e:
        print(Fore.RED + f"An unexpected error occurred: {e}" + Style.RESET_ALL)
        sys.exit()

if __name__ == "__main__":
    ascii_clock_dashboard()
