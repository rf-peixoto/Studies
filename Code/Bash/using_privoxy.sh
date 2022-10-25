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
