# NETRECON — Path Intelligence System

Cyberpunk HUD-style network traceroute analysis tool built with Flask.

## Setup

```bash
# Linux / macOS
sudo apt install traceroute     # or brew install traceroute
pip install -r requirements.txt
sudo python app.py              # sudo needed for raw ICMP on Linux
```

Open: http://localhost:5000

## Features

- Real-time hop-by-hop streaming via SSE
- Reverse DNS resolution
- Organization, ASN, geolocation via ip-api.com
- OS fingerprinting via TTL (Linux ≤64 / Windows ≤128 / Cisco ≤255)
- Hop type classification: GATEWAY · ISP · BACKBONE · CDN · CLOUD · HOSTING · PROXY · TRANSIT · TARGET
- Packet loss % per hop
- Jitter (latency standard deviation) per hop
- Proxy / hosting / mobile detection
- Latency profile chart (canvas)
- JSON export
- Copy IP to clipboard
