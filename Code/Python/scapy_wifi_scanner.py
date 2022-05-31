# Wi-fi Scanner
from scapy.all import *
from threading import Thread
import pandas
import time
import os

# Initialize dataframes:
networks = pandas.DataFrame(columns=["BSSID", "SSID", "dBm_Signal", "Channel", "Crypto"])
networks.set_index("BSSID", inplace=True)

def callback(packet):
    if packet.haslayer(Dot11Beacon):
        # Extract MAC Address:
        bssid = packet[Dot11].addr2
        # Get the name:
        ssid = packet[Dot11Elt].info.decode()
        try:
            dbm_signal = packet.dBm_AntiSignal
        except:
            dbm_signal = "N/A"
        # Extract network stats:
        stats = packet[Dot11Beacon].network_stats()
        # AP Channel:
        channel = stats.get("channel")
        # Crypto:
        crypto = stats.get("crypto")
        networks.loc[bssid] = (ssid, dbm_signal, channel, crypto)

def print_all():
    while True:
        os.system("clear")
        print(networks)
        time.sleep(0.5)

if __name__ == "__main__":
    # Interface name:
    interface = "wlp2s0"
    # Start Thread:
    printer = Thread(target=print_all)
    printer.daemon = True
    printer.start()
    # Sniff:
    sniff(prn = callback, iface = interface)
