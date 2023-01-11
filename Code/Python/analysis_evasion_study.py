import psutil
import atexit # https://docs.python.org/3/library/atexit.html
import sys, os
from time import sleep
from pathlib import Path
from hashlib import blake2b
from secrets import token_hex

#from datetime import datetime # schedule execution
#-----#

# Encoded starting:
if len(sys.argv) == 2:
    tmp = blake2b(sys.argv[1].encode()).hexdigest()[48:72]
    if tmp != '0ea71024b01abc59ab177756':
        quit()
else:
    quit()

    
# Look for VM:
def get_prefix():
    return getattr(sys, "base_prefix", None) or getattr(sys, "real_prefix", None) or sys.prefix

def runs_on_venv():
    return get_prefix() != sys.prefix

if runs_on_venv():
    quit()

# Check debugger:
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

# Simulate error:
print("[2211] Error loading Python lib '/tmp/_MEItsJHyk/libpython3.10.so.1.0': dlopen: /lib/x86_64-linux-gnu/libm.so.6: version `GLIBC_2.35' not found (required by /tmp/_MEItsJHyk/libpython3.10.so.1.0)")
sys.exit(1)


# Functions thus registered are automatically executed upon normal interpreter termination.
# atexit runs these functions in the reverse order in which they were registered; if you
# register A, B, and C, at interpreter termination time they will be run in the order C, B, A.

# Note: The functions registered via this module are not called when the program is killed
# by a signal not handled by Python, when a Python fatal internal error is detected, or
# when os._exit() is called.

atexit.register(function_name)
atexit.register(function_name, arg1, arg2)

# Use as decorator (only for functions without arguments):
@atextir.register
def thing():
    print("do stuff")


# Stack flooding:
stack = []
counter = 1
while len(stack) <= 5:
    counter *= 2
    stack.append([*str(token_hex(counter))])
    sleep(0.1)


#-----#
