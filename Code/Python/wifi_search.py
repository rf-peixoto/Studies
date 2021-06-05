import os
from time import sleep
import threading

first_ip_range = [ip for ip in range(0, 128)]
second_ip_range = [ip for ip in range(127, 256)]
devices_found = []

def first_wifi_search():
    for i in first_ip_range:
        full_ip = "10.0.0.{0}".format(i)
        if os.system("ping -c 1 -q -i 0.2 {0}".format(full_ip)) == 0:
            devices_found.append(full_ip)
        sleep(0.2)

def second_wifi_search():
    for i in second_ip_range:
        full_ip = "10.0.0.{0}".format(i)
        if os.system("ping -c 1 -q -i 0.2 {0}".format(full_ip)) == 0:
            devices_found.append(full_ip)
        sleep(0.2)

first_thread = threading.Thread(target=first_wifi_search)
second_thread = threading.Thread(target=second_wifi_search)

first_thread.start()
second_thread.start()

first_thread.join()
second_thread.join()

print(devices_found)
