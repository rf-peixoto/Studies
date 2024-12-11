import os
import socket
import subprocess
import glob
import hashlib
import secrets

# Configuration
LISTEN_PORT = 4444  # Port to listen on
BANNER = "Dead Man's Switch - Version 1.0\n"

def generate_hashed_password():
    """Prompt the user for a password, hash it with a random salt, and return the hash."""
    password = input("Set the activation password: ").strip()
    salt = secrets.token_bytes(16)
    hashed_password = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return hashed_password, salt

def verify_password(received_password, stored_hash, salt):
    """Verify if the received password matches the stored hash."""
    hashed_input = hashlib.pbkdf2_hmac('sha256', received_password.encode(), salt, 100000)
    return hashed_input == stored_hash

def ensure_binary(binary):
    """Ensure the required binary is available, install if necessary."""
    for manager in ["apt", "dnf"]:
        if subprocess.call(["which", binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            return
        print(f"[INFO] {binary} not found. Attempting to install using {manager}...")
        try:
            subprocess.run([manager, "update"], check=True)
            subprocess.run([manager, "install", "-y", binary], check=True)
            return
        except Exception as e:
            print(f"[ERROR] Failed to install {binary} using {manager}: {e}")
    raise RuntimeError(f"Required binary {binary} is missing and could not be installed.")

def wipe_logs():
    print("[INFO] Clearing all logs on the machine...")
    log_dirs = [
        "/var/log",
        "/var/log/journal",
        "/var/lib/rsyslog",
        "/var/lib/syslog",
        "/var/tmp",
        "/tmp",
        "/home/*/.bash_history",
        "/home/*/.zsh_history",
        "/home/*/.wget-hsts",
        "/home/*/.python_history",
        "/home/*/.config/google-chrome",
        "/home/*/.mozilla/firefox",
        "/home/*/.tor-browser",
        "/root/.bash_history",
        "/root/.zsh_history",
        "/root/.wget-hsts",
        "/root/.python_history",
        "/root/.tor-browser"
    ]

    for log_dir in log_dirs:
        try:
            matches = glob.glob(log_dir)
            for match in matches:
                if os.path.exists(match):
                    print(f"[INFO] Wiping logs and history files: {match}")
                    subprocess.run(["shred", "--iterations=3", "--remove", "--recursive", match], check=False)
        except Exception as e:
            print(f"[ERROR] Failed to wipe {log_dir}: {e}")

def wipe_cryptocurrency_wallets():
    print("[INFO] Clearing cryptocurrency wallets and related files...")
    wallet_dirs = [
        "/home/*/.bitcoin",
        "/home/*/.electrum",
        "/home/*/.monero",
        "/home/*/.atomic",
        "/home/*/.ethereum",
        "/home/*/.litecoin",
        "/home/*/.dogecoin",
        "/root/.bitcoin",
        "/root/.electrum",
        "/root/.monero",
        "/root/.atomic",
        "/root/.ethereum",
        "/root/.litecoin",
        "/root/.dogecoin"
    ]

    for wallet_dir in wallet_dirs:
        try:
            matches = glob.glob(wallet_dir)
            for match in matches:
                if os.path.exists(match):
                    print(f"[INFO] Wiping wallet directory: {match}")
                    subprocess.run(["shred", "--iterations=3", "--remove", "--recursive", match], check=False)
        except Exception as e:
            print(f"[ERROR] Failed to wipe wallet directory {wallet_dir}: {e}")

def wipe_vpn_and_ssh():
    print("[INFO] Clearing VPN and SSH configurations and histories...")
    vpn_ssh_dirs = [
        "/etc/openvpn",
        "/etc/ssh",
        "/home/*/.ssh",
        "/root/.ssh",
        "/home/*/.openvpn",
        "/root/.openvpn",
        "/var/lib/NetworkManager",
        "/etc/NetworkManager/system-connections"
    ]

    for vpn_ssh_dir in vpn_ssh_dirs:
        try:
            matches = glob.glob(vpn_ssh_dir)
            for match in matches:
                if os.path.exists(match):
                    print(f"[INFO] Wiping VPN/SSH directory: {match}")
                    subprocess.run(["shred", "--iterations=3", "--remove", "--recursive", match], check=False)
        except Exception as e:
            print(f"[ERROR] Failed to wipe {vpn_ssh_dir}: {e}")

def wipe_cron_jobs():
    print("[INFO] Clearing cron jobs...")
    cron_dirs = [
        "/var/spool/cron",
        "/etc/cron.d",
        "/etc/cron.daily",
        "/etc/cron.hourly",
        "/etc/cron.monthly",
        "/etc/cron.weekly"
    ]

    for cron_dir in cron_dirs:
        try:
            if os.path.exists(cron_dir):
                print(f"[INFO] Wiping cron jobs in: {cron_dir}")
                subprocess.run(["shred", "--iterations=3", "--remove", "--recursive", cron_dir], check=False)
        except Exception as e:
            print(f"[ERROR] Failed to wipe cron jobs in {cron_dir}: {e}")

def wipe_messaging_apps():
    print("[INFO] Clearing messaging app data...")
    messaging_dirs = [
        "/home/*/.TelegramDesktop",
        "/home/*/.config/Signal",
        "/root/.TelegramDesktop",
        "/root/.config/Signal"
    ]

    for messaging_dir in messaging_dirs:
        try:
            matches = glob.glob(messaging_dir)
            for match in matches:
                if os.path.exists(match):
                    print(f"[INFO] Wiping messaging app directory: {match}")
                    subprocess.run(["shred", "--iterations=3", "--remove", "--recursive", match], check=False)
        except Exception as e:
            print(f"[ERROR] Failed to wipe {messaging_dir}: {e}")

def wipe_pgp_gpg_keys():
    print("[INFO] Clearing PGP/GPG keys and configurations...")
    key_dirs = [
        "/home/*/.gnupg",
        "/root/.gnupg"
    ]

    for key_dir in key_dirs:
        try:
            matches = glob.glob(key_dir)
            for match in matches:
                if os.path.exists(match):
                    print(f"[INFO] Wiping PGP/GPG directory: {match}")
                    subprocess.run(["shred", "--iterations=3", "--remove", "--recursive", match], check=False)
        except Exception as e:
            print(f"[ERROR] Failed to wipe {key_dir}: {e}")

def wipe_libreoffice_data():
    print("[INFO] Clearing LibreOffice data and backups...")
    office_dirs = [
        "/home/*/.config/libreoffice",
        "/root/.config/libreoffice"
    ]

    for office_dir in office_dirs:
        try:
            matches = glob.glob(office_dir)
            for match in matches:
                if os.path.exists(match):
                    print(f"[INFO] Wiping LibreOffice directory: {match}")
                    subprocess.run(["shred", "--iterations=3", "--remove", "--recursive", match], check=False)
        except Exception as e:
            print(f"[ERROR] Failed to wipe {office_dir}: {e}")

def wipe_torrents():
    print("[INFO] Clearing torrent client data...")
    torrent_dirs = [
        "/home/*/.config/qBittorrent",
        "/home/*/.config/deluge",
        "/home/*/.config/transmission",
        "/root/.config/qBittorrent",
        "/root/.config/deluge",
        "/root/.config/transmission"
    ]

    for torrent_dir in torrent_dirs:
        try:
            matches = glob.glob(torrent_dir)
            for match in matches:
                if os.path.exists(match):
                    print(f"[INFO] Wiping torrent client directory: {match}")
                    subprocess.run(["shred", "--iterations=3", "--remove", "--recursive", match], check=False)
        except Exception as e:
            print(f"[ERROR] Failed to wipe {torrent_dir}: {e}")

def wipe_home_directories():
    print("[INFO] Clearing personal files and directories in /home and /root...")
    home_dirs = [
        "/home/*",
        "/root"
    ]
    for home_dir in home_dirs:
        try:
            matches = glob.glob(home_dir)
            for match in matches:
                if os.path.exists(match):
                    print(f"[INFO] Wiping personal directory: {match}")
                    subprocess.run(["shred", "--iterations=3", "--remove", "--recursive", match], check=False)
        except Exception as e:
            print(f"[ERROR] Failed to wipe personal files in {home_dir}: {e}")

def wipe_disk():
    print("[INFO] Initiating disk wipe procedure...")

    # Ensure required binaries
    ensure_binary("shred")
    ensure_binary("iptables")
    
    # Overwrite all partitions with random data
    try:
        partitions = subprocess.check_output("lsblk -dno NAME", shell=True).decode().strip().split("\n")
        for partition in partitions:
            dev_path = f"/dev/{partition}"
            print(f"[INFO] Wiping partition: {dev_path}")
            subprocess.run(["shred", "--iterations=3", "--random-source=/dev/urandom", "--verbose", dev_path], check=True)
    except Exception as e:
        print(f"[ERROR] Failed to wipe disk partitions: {e}")

    # Wipe free space on mounted file systems
    try:
        mounted_filesystems = subprocess.check_output("df -x tmpfs -x devtmpfs --output=target", shell=True).decode().strip().split("\n")[1:]
        for filesystem in mounted_filesystems:
            print(f"[INFO] Wiping free space on: {filesystem}")
            subprocess.run(["shred", "--iterations=3", "--remove", f"{filesystem}/wipe_temp_file"], check=False)
    except Exception as e:
        print(f"[ERROR] Failed to wipe free space: {e}")

    # Corrupt system files
    try:
        print("[INFO] Corrupting system files...")
        for path in ["/boot", "/etc", "/var"]:
            subprocess.run(["shred", "--iterations=1", "--remove", "--zero", f"{path}/wipe_temp_file"], check=False)
    except Exception as e:
        print(f"[ERROR] Failed to corrupt system files: {e}")

    # Clear logs and network traces
    try:
        wipe_logs()
        wipe_home_directories()
        wipe_cryptocurrency_wallets()
        wipe_vpn_and_ssh()
        wipe_cron_jobs()
        wipe_messaging_apps()
        wipe_pgp_gpg_keys()
        wipe_libreoffice_data()
        wipe_torrents()
        print("[INFO] Clearing network traces...")
        subprocess.run(["iptables", "-F"], check=True)
        subprocess.run(["iptables", "-X"], check=True)
        subprocess.run(["iptables", "-t", "nat", "-F"], check=True)
    except Exception as e:
        print(f"[ERROR] Failed to clear logs, network traces, or personal files: {e}")

    # Trigger kernel panic
    try:
        print("[INFO] Triggering kernel panic...")
        subprocess.run("echo c > /proc/sysrq-trigger", shell=True, check=False)
    except Exception as e:
        print(f"[ERROR] Failed to trigger kernel panic: {e}")

def handle_request(conn, stored_hash, salt):
    conn.sendall(BANNER.encode())
    conn.sendall(b"Enter password: ")
    password = conn.recv(1024).decode().strip()
    if verify_password(password, stored_hash, salt):
        conn.sendall(b"Password accepted. Wiping data.\n")
        conn.close()
        wipe_disk()
    else:
        conn.sendall(b"Incorrect password.\n")
    conn.close()

if __name__ == "__main__":
    print(f"[INFO] Listening on port {LISTEN_PORT}...")
    hashed_password, salt = generate_hashed_password()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(("0.0.0.0", LISTEN_PORT))
        server_socket.listen(5)

        while True:
            try:
                conn, addr = server_socket.accept()
                print(f"[INFO] Connection received from {addr}")
                handle_request(conn, hashed_password, salt)
            except KeyboardInterrupt:
                print("[INFO] Server shutting down.")
                break
            except Exception as e:
                print(f"[ERROR] An error occurred: {e}")
