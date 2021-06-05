import platform
import socket

# Platform
op_sys = platform.system()
arch = platform.architecture()
user_name = platform.os.getlogin()
network_name = platform.node()

# Network
internal_ip = socket.gethostbyname(socket.gethostname())
