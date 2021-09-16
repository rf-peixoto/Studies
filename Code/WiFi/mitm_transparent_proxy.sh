# Enable IP Foward:
sysctl -w net.ipv4.ip_forward=1

# Disable ICMP Redirects:
sysctl -w net.ipv4.conf.all.send_redirects=0

# Create IP Tables Ruleset:
# $1 : Interface conected.
iptables -t nat -A PREROUTING -i $1 -p tcp --dport 80 -j REDIRECT --to-port 8080
iptables -t nat -A PREROUTING -i $1 -p tcp --dport 443 -j REDIRECT --to-port 8080

# Your ARP Spoofing goes here.
#----------------------------#

# Run mitmproxy
mitmproxy --mode transparent --showhost -w mitm.log


# To open your log file:
# mitmproxy -r mitm.log
