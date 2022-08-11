import psutil

# Define list of debuggers:
debuggers = ['debugger', 'debug', 'ida', 'ghidra', 'rizin', 'cutter', 'gdb']
# Get PIDs:
pids = psutil.pids()
# Look for debuggers:
for id in pids:
    try:
        process = psutil.Process(id).name()
        if process in debuggers:
            print("Debugger found!")
            print("Process name: {0}\nPID: {1}".format(process, id))
    except Exception as error:
        print(error)
        continue
