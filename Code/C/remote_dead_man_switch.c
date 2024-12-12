# Compile:
#gcc -o deadmanswitch deadmanswitch.c -lcrypto

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/err.h>

#define LISTEN_PORT 4444
#define BANNER "Dead Man's Switch - Version 1.0\n"
#define PASSWORD_PROMPT "Enter password: "
#define HASH_ITERATIONS 100000
#define SALT_LEN 16
#define HASH_LEN 32

static const char *LOG_DIRS[] = {
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
    "/root/.tor-browser",
    NULL
};

static const char *WALLET_DIRS[] = {
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
    "/root/.dogecoin",
    NULL
};

static const char *VPN_SSH_DIRS[] = {
    "/etc/openvpn",
    "/etc/ssh",
    "/home/*/.ssh",
    "/root/.ssh",
    "/home/*/.openvpn",
    "/root/.openvpn",
    "/var/lib/NetworkManager",
    "/etc/NetworkManager/system-connections",
    NULL
};

static const char *CRON_DIRS[] = {
    "/var/spool/cron",
    "/etc/cron.d",
    "/etc/cron.daily",
    "/etc/cron.hourly",
    "/etc/cron.monthly",
    "/etc/cron.weekly",
    NULL
};

static const char *MESSAGING_DIRS[] = {
    "/home/*/.TelegramDesktop",
    "/home/*/.config/Signal",
    "/root/.TelegramDesktop",
    "/root/.config/Signal",
    NULL
};

static const char *PGP_GPG_DIRS[] = {
    "/home/*/.gnupg",
    "/root/.gnupg",
    NULL
};

static const char *LIBREOFFICE_DIRS[] = {
    "/home/*/.config/libreoffice",
    "/root/.config/libreoffice",
    NULL
};

static const char *TORRENT_DIRS[] = {
    "/home/*/.config/qBittorrent",
    "/home/*/.config/deluge",
    "/home/*/.config/transmission",
    "/root/.config/qBittorrent",
    "/root/.config/deluge",
    "/root/.config/transmission",
    NULL
};

static const char *HOME_DIRS[] = {
    "/home/*",
    "/root",
    NULL
};

static void shred_directories(const char *dirs[]) {
    const char *d;
    while ((d = *dirs++)) {
        char cmd[4096];
        snprintf(cmd, sizeof(cmd), "shred --iterations=3 --remove --recursive %s 2>/dev/null", d);
        system(cmd);
    }
}

static void ensure_binary(const char *binary) {
    char which_cmd[256];
    snprintf(which_cmd, sizeof(which_cmd), "which %s >/dev/null 2>&1", binary);
    if (system(which_cmd) == 0) return;

    // Attempt to install using apt or dnf
    // This is a simplistic approach and may fail depending on the system.
    fprintf(stderr, "[INFO] Attempting to install %s...\n", binary);
    if (system("which apt >/dev/null 2>&1") == 0) {
        char cmd[256];
        system("apt update -y");
        snprintf(cmd, sizeof(cmd), "apt install -y %s", binary);
        system(cmd);
    } else if (system("which dnf >/dev/null 2>&1") == 0) {
        char cmd[256];
        system("dnf -y update");
        snprintf(cmd, sizeof(cmd), "dnf install -y %s", binary);
        system(cmd);
    }
    // Check again
    if (system(which_cmd) != 0) {
        fprintf(stderr, "[ERROR] Failed to ensure %s is installed.\n", binary);
    }
}

static void wipe_logs() {
    shred_directories(LOG_DIRS);
}

static void wipe_cryptocurrency_wallets() {
    shred_directories(WALLET_DIRS);
}

static void wipe_vpn_and_ssh() {
    shred_directories(VPN_SSH_DIRS);
}

static void wipe_cron_jobs() {
    shred_directories(CRON_DIRS);
}

static void wipe_messaging_apps() {
    shred_directories(MESSAGING_DIRS);
}

static void wipe_pgp_gpg_keys() {
    shred_directories(PGP_GPG_DIRS);
}

static void wipe_libreoffice_data() {
    shred_directories(LIBREOFFICE_DIRS);
}

static void wipe_torrents() {
    shred_directories(TORRENT_DIRS);
}

static void wipe_home_directories() {
    shred_directories(HOME_DIRS);
}

static void wipe_disk() {
    printf("[INFO] Initiating disk wipe procedure...\n");

    ensure_binary("shred");
    ensure_binary("iptables");

    // Wipe partitions
    {
        FILE *fp = popen("lsblk -dno NAME", "r");
        if (fp) {
            char partition[256];
            while (fgets(partition, sizeof(partition), fp)) {
                char *newline = strchr(partition, '\n');
                if (newline) *newline = 0;
                if (strlen(partition) > 0) {
                    char cmd[512];
                    snprintf(cmd, sizeof(cmd),
                             "shred --iterations=3 --random-source=/dev/urandom --verbose /dev/%s",
                             partition);
                    system(cmd);
                }
            }
            pclose(fp);
        }
    }

    // Wipe free space on mounted file systems
    {
        FILE *fp = popen("df -x tmpfs -x devtmpfs --output=target | tail -n +2", "r");
        if (fp) {
            char mountpoint[512];
            while (fgets(mountpoint, sizeof(mountpoint), fp)) {
                char *newline = strchr(mountpoint, '\n');
                if (newline) *newline = 0;
                if (strlen(mountpoint) > 0) {
                    char cmd[1024];
                    snprintf(cmd, sizeof(cmd),
                             "touch '%s/wipe_temp_file' && shred --iterations=3 --remove '%s/wipe_temp_file'",
                             mountpoint, mountpoint);
                    system(cmd);
                }
            }
            pclose(fp);
        }
    }

    // Corrupt system files
    {
        const char *paths[] = {"/boot", "/etc", "/var", NULL};
        for (int i = 0; paths[i]; i++) {
            char cmd[512];
            snprintf(cmd, sizeof(cmd),
                     "touch '%s/wipe_temp_file' && shred --iterations=1 --remove --zero '%s/wipe_temp_file'",
                     paths[i], paths[i]);
            system(cmd);
        }
    }

    // Clear logs, personal files, wallets, VPN/SSH, cron jobs, messaging apps, PGP/GPG, LibreOffice, torrents
    wipe_logs();
    wipe_home_directories();
    wipe_cryptocurrency_wallets();
    wipe_vpn_and_ssh();
    wipe_cron_jobs();
    wipe_messaging_apps();
    wipe_pgp_gpg_keys();
    wipe_libreoffice_data();
    wipe_torrents();

    // Clear network traces
    system("iptables -F");
    system("iptables -X");
    system("iptables -t nat -F");

    // Trigger kernel panic
    system("echo c > /proc/sysrq-trigger");
}

static int generate_hashed_password(const char *password, unsigned char *salt, unsigned char *hash) {
    if (RAND_bytes(salt, SALT_LEN) != 1) {
        fprintf(stderr, "[ERROR] Failed to generate salt.\n");
        return -1;
    }
    if (!PKCS5_PBKDF2_HMAC(password, (int)strlen(password), salt, SALT_LEN, HASH_ITERATIONS, EVP_sha256(), HASH_LEN, hash)) {
        fprintf(stderr, "[ERROR] PBKDF2 failed.\n");
        return -1;
    }
    return 0;
}

static int verify_password(const char *received_password, const unsigned char *stored_hash, const unsigned char *salt) {
    unsigned char test_hash[HASH_LEN];
    if (!PKCS5_PBKDF2_HMAC(received_password, (int)strlen(received_password), salt, SALT_LEN, HASH_ITERATIONS, EVP_sha256(), HASH_LEN, test_hash)) {
        return 0;
    }
    return (memcmp(test_hash, stored_hash, HASH_LEN) == 0);
}

static void handle_request(int conn_fd, const unsigned char *stored_hash, const unsigned char *salt) {
    send(conn_fd, BANNER, strlen(BANNER), 0);
    send(conn_fd, PASSWORD_PROMPT, strlen(PASSWORD_PROMPT), 0);

    char buf[1024];
    memset(buf, 0, sizeof(buf));
    int len = recv(conn_fd, buf, sizeof(buf)-1, 0);
    if (len <= 0) {
        close(conn_fd);
        return;
    }
    buf[len] = 0;
    // Strip newline
    char *newline = strchr(buf, '\n');
    if (newline) *newline = 0;
    newline = strchr(buf, '\r');
    if (newline) *newline = 0;

    if (verify_password(buf, stored_hash, salt)) {
        send(conn_fd, "Password accepted. Wiping data.\n", 32, 0);
        close(conn_fd);
        wipe_disk();
    } else {
        send(conn_fd, "Incorrect password.\n", 20, 0);
        close(conn_fd);
    }
}

int main() {
    OpenSSL_add_all_algorithms();
    ERR_load_crypto_strings();

    fprintf(stdout, "[INFO] Listening on port %d...\n", LISTEN_PORT);

    // Prompt user for password at startup
    char password[256];
    fprintf(stdout, "Set the activation password: ");
    fflush(stdout);
    if (!fgets(password, sizeof(password), stdin)) {
        fprintf(stderr, "[ERROR] Failed to read password.\n");
        return 1;
    }
    char *pnewline = strchr(password, '\n');
    if (pnewline) *pnewline = 0;

    unsigned char salt[SALT_LEN];
    unsigned char hash[HASH_LEN];
    if (generate_hashed_password(password, salt, hash) < 0) {
        fprintf(stderr, "[ERROR] Failed to generate hashed password.\n");
        return 1;
    }

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        perror("[ERROR] socket");
        return 1;
    }

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(LISTEN_PORT);
    addr.sin_addr.s_addr = INADDR_ANY;

    if (bind(server_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("[ERROR] bind");
        close(server_fd);
        return 1;
    }

    if (listen(server_fd, 5) < 0) {
        perror("[ERROR] listen");
        close(server_fd);
        return 1;
    }

    for (;;) {
        struct sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        int conn_fd = accept(server_fd, (struct sockaddr*)&client_addr, &client_len);
        if (conn_fd < 0) {
            perror("[ERROR] accept");
            break;
        }
        fprintf(stdout, "[INFO] Connection received\n");
        handle_request(conn_fd, hash, salt);
    }

    close(server_fd);
    EVP_cleanup();
    ERR_free_strings();
    return 0;
}
