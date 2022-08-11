import psutil

psutil.pids()
psutil.users()
psutil.Process(ID)

# "Manual mode"
import os
pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]

for pid in pids:
    try:
        print(open(os.path.join('/proc', pid, 'cmdline'), 'r').read().split('\0')[0])
    except IOError: # proc has already terminated
        continue
