import platform, socket
from pathlib import Path
from datetime import datetime

class OSRecon:
    def __init__(self):
        self.os = platform.system()
        self.arch = "{0} {1}".format(platform.machine(), platform.architecture()[0])
        self.username = platform.os.getlogin()
        self.home = str(Path.home())
        self.node = platform.node()
        self.node_ip = socket.gethostbyname(socket.gethostname())
        try:
            self.dump = platform.freedesktop_os_release()
        except:
            pass

# Debug:
r = OSRecon()
print("OS: {0}".format(r.os))
print("Architecture: {0}".format(r.arch))
print("Username: {0}".format(r.username))
print("Home Path: {0}".format(r.home))
print("Network Node: {0}".format(r.node))
print("Local Address: {0}".format(r.node_ip))
print("\n")
print(f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}|{r.username}|{r.os} {r.arch}|{r.home}|{r.node}|{r.node_ip}")
