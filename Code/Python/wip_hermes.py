import secrets, sys

sizes = [8, 16, 24, 48, 64, 96, 128, 256, 512, 1024, 2048, 4096]

if len(sys.argv) != 2:
    print("Usage: hermes.py KEY-SIZE")
    sys.exit()
elif int(sys.argv[1]) not in sizes:
    print("Invalid key size.")
    sys.exit()

print(secrets.token_bytes(int(sys.argv[1])))
