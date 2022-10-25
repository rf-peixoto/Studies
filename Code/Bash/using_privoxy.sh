# Runs on port 8118

# Config:
nano /etc/privoxy/config

# Uncoment lines:

foward-socks4   /   127.0.0.1   9050    .
foward-socks5t   /   127.0.0.1   9050    .

# Start:
service privoxy start

# Test it:
curl --proxy http://127.0.0.1:8118/ ifconfig.me

# Config privoxy on VPS:
nano /etc/privoxy/config
# Change listen-address to 0.0.0.0:8118
# Setup firewall rule to prevent anyone to connect
# And/or setup user and password.
# Comment tor lines.
