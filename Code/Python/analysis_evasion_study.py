import psutil
import sys, os
from pathlib import Path
from hashlib import blake2b

# Check the hash of the file it self!
# md5sum sys.argv[0]

#from datetime import datetime # schedule execution
#-----#
if len(sys.argv) == 2:
    tmp = blake2b(sys.argv[1].encode()).hexdigest()[48:72]
    if tmp != '0ea71024b01abc59ab177756':
        quit()
else:
    quit()

def get_prefix():
    return getattr(sys, "base_prefix", None) or getattr(sys, "real_prefix", None) or sys.prefix

def runs_on_venv():
    return get_prefix() != sys.prefix

if runs_on_venv():
    quit()

debuggers = ['debugger', 'debug', 'ida', 'ghidra', 'rizin', 'cutter', 'gdb', 'tcpdump', 'wireshark', 'snif']
pids = psutil.pids()
for id in pids:
    try:
        process = psutil.Process(id).name().lower()
        if process in debuggers:
            quit()
    except Exception as error:
        print(error)
        continue

os.chdir(str(Path.home()))
with open("Note.txt", "w") as fl:
    fl.write("Congratulations, you were able to run the file and find the flag.\n")

print("[2211] Error loading Python lib '/tmp/_MEItsJHyk/libpython3.10.so.1.0': dlopen: /lib/x86_64-linux-gnu/libm.so.6: version `GLIBC_2.35' not found (required by /tmp/_MEItsJHyk/libpython3.10.so.1.0)")
sys.exit(1)
#-----#
