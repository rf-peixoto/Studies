import subprocess
from termcolor import colored
from pythonping import ping

# Expanded list of IPs including Asian Russia and formatted with tabs for better readability
targets = {
    'North America - USA (California)': '8.8.8.8',        # Google DNS
    'North America - USA (New York)': '208.67.222.222',   # OpenDNS
    'North America - Canada (Toronto)': '24.153.32.5',    # Local Canadian IP
    'Europe - Germany': '193.99.144.80',                  # Heinlein Support IP
    'Europe - UK': '212.58.244.20',                       # BBC UK
    'Europe - Russia (Moscow)': '77.88.8.8',              # Yandex DNS
    'Asia - Russia (Siberia)': '92.255.241.1',          # Siberian ISP
    'Asia - Japan': '202.248.37.77',                      # NTT Japan
    'Asia - China (Beijing)': '202.106.0.20',             # Baidu DNS
    'South America - Brazil': '200.160.0.8',              # Brazil DNS
    'South America - Argentina': '200.51.211.7',          # Argentina DNS
    'Africa - South Africa': '102.67.235.1',              # South Africa DNS server
    'Africa - Egypt': '213.131.64.75',                    # Local Egyptian IP
    'Australia - Sydney': '139.130.4.5',                  # Australia DNS
    'Australia - Melbourne': '203.27.227.220'             # Local Melbourne IP
}

def check_connectivity(ip, region):
    try:
        response = ping(ip, count=4, verbose=False)
        if response.success():
            avg_latency = round(response.rtt_avg_ms, 2)
            return f"{ip}\t{region} {colored('Reachable', 'green')} {avg_latency}ms"
        else:
            return f"{ip}\t{region} {colored('Unreachable', 'red')}"
    except Exception as e:
        return f"{ip}\t{region} {colored('Error', 'red')} {str(e)}"

def main():
    for region, ip in targets.items():
        print(check_connectivity(ip, region))

if __name__ == "__main__":
    main()
