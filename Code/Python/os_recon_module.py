import platform, socket
from pathlib import Path

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
