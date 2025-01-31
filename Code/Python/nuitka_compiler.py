import subprocess
import sys
import platform

def install_nuitka():
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "nuitka"],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error installing Nuitka: {e}")
        sys.exit(1)

def install_zstandard():
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "zstandard"],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error installing zstandard: {e}")
        sys.exit(1)

def compile_script(script_path):
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--onefile",
        "--remove-output",
        script_path
    ]
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error compiling script: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Replace this with your script's path
    script_to_compile = sys.argv[1]

    # Install required packages
    install_nuitka()
    if platform.system() != "Windows":
        install_zstandard()

    # Compile the script
    compile_script(script_to_compile)
    print("Compilation completed successfully! Check for the executable in the current directory.")
