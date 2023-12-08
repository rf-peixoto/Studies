import paramiko
import socket
import threading
import os

HOST_KEY = paramiko.RSAKey.generate(2048)

class FakeSSHServer(paramiko.ServerInterface):
    def __init__(self):
        self.event = threading.Event()

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        print(f"Login attempt with username: {username} and password: {password}")
        return paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        print(f"Login attempt with username: {username} and public key: {key.get_base64()}")
        return paramiko.AUTH_FAILED

    def check_auth_none(self, username):
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return 'password,publickey'

    def check_channel_shell_request(self, channel):
        self.event.set()
        return True

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        return True

def start_fake_ssh_server(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((ip, port))
    sock.listen(100)
    print(f"Fake SSH Server listening on {ip}:{port}")

    while True:
        client, addr = sock.accept()
        print(f"Connection from {addr}")
        t = paramiko.Transport(client)
        t.add_server_key(HOST_KEY)
        server = FakeSSHServer()
        try:
            t.start_server(server=server)
        except paramiko.SSHException:
            print("SSH negotiation failed.")
            continue

        channel = t.accept(20)
        if channel is None:
            continue

        server.event.wait(10)
        if not server.event.is_set():
            continue

        try:
            channel.send("Debian GNU/Linux 10 \\n \\l\n")  # Simulate Debian welcome message
            cwd = "/home/user"  # Current working directory
            fake_filesystem = {
                "/home/user": ["Desktop", "Documents", "Downloads", "Music", "Pictures", "Videos"],
                "/home/user/Desktop": ["example.txt"],
                # Add more directories and files as needed
            }
            while True:
                channel.send(f"user@debian:{cwd}$ ")  # Simulate Debian command prompt
                command = channel.recv(1024).strip().decode('utf-8')
                if not command:
                    continue
                print(f"Received command: {command}")

                cmd_parts = command.split()
                cmd_name = cmd_parts[0]

                if cmd_name == "pwd":
                    channel.send(f"{cwd}\n")
                elif cmd_name == "ls":
                    contents = fake_filesystem.get(cwd, [])
                    channel.send("  ".join(contents) + "\n")
                elif cmd_name == "cd":
                    if len(cmd_parts) < 2:
                        cwd = "/home/user"  # Default to home directory
                    else:
                        new_dir = cmd_parts[1]
                        if new_dir in ["..", "."]:
                            cwd = "/home/user"  # Simplify handling for '..' and '.'
                        elif new_dir.startswith("/"):
                            if new_dir in fake_filesystem:
                                cwd = new_dir
                            else:
                                channel.send("bash: cd: " + new_dir + ": No such file or directory\n")
                        else:
                            potential_new_dir = os.path.join(cwd, new_dir)
                            if potential_new_dir in fake_filesystem:
                                cwd = potential_new_dir
                            else:
                                channel.send("bash: cd: " + new_dir + ": No such file or directory\n")
                elif cmd_name == "whoami":
                    channel.send("user\n")
                elif cmd_name == "id":
                    channel.send("uid=1000(user) gid=1000(user) groups=1000(user),24(cdrom),25(floppy),29(audio),30(dip),44(video),46(plugdev),109(netdev)\n")
                elif cmd_name == "uname":
                    channel.send("Linux\n")
                else:
                    channel.send(f"bash: {command}: command not found\n")
        except Exception as e:
            print(f"Caught exception: {e}")
            try:
                t.close()
            except:
                pass

# Start the server
start_fake_ssh_server('0.0.0.0', 22)
