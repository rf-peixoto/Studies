import os
import re
import sys
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

# Define color shortcuts
INFO = Fore.CYAN + Style.BRIGHT
WARNING = Fore.YELLOW + Style.BRIGHT
DANGER = Fore.RED + Style.BRIGHT
SUCCESS = Fore.GREEN + Style.BRIGHT
RESET = Style.RESET_ALL

# Define sensitive data patterns
SENSITIVE_PATTERNS = {
    'AWS Access Key': r'AKIA[0-9A-Z]{16}',
    'AWS Secret Key': r'(?i)aws_secret_access_key.*?[:=]\s*([A-Za-z0-9/+=]{40})',
    'Google API Key': r'AIza[0-9A-Za-z-_]{35}',
    'Email Addresses': r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+',
    'Private Key': r'-----BEGIN PRIVATE KEY-----',
    'Password in Config': r'password\s*=\s*["\'].*?["\']',
    'Credit Card Number': r'\b(?:\d[ -]*?){13,16}\b',
    'Social Security Number': r'\b\d{3}-\d{2}-\d{4}\b',
}

# Define suspicious file extensions
SUSPICIOUS_EXTENSIONS = ['.exe', '.dll', '.js', '.tmp', '.log', '.bak']

# Define maximum file size to read (e.g., 5 MB)
MAX_FILE_SIZE = 5 * 1024 * 1024

def check_file_permissions(root_dir):
    """Check for files and directories with insecure permissions."""
    try:
        for root, dirs, files in os.walk(root_dir):
            for name in files + dirs:
                path = os.path.join(root, name)
                try:
                    mode = os.stat(path).st_mode
                    if mode & 0o0002:
                        print(WARNING + f"[!] Insecure permissions detected: {path}")
                except Exception as e:
                    print(DANGER + f"Error checking permissions for {path}: {str(e)}")
    except Exception as e:
        print(DANGER + f"Error walking through {root_dir}: {str(e)}")

def scan_for_sensitive_data(root_dir):
    """Scan files for sensitive data patterns."""
    try:
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                path = os.path.join(root, file)
                try:
                    if os.path.getsize(path) > MAX_FILE_SIZE:
                        continue
                    with open(path, 'r', errors='ignore') as f:
                        content = f.read()
                        for label, pattern in SENSITIVE_PATTERNS.items():
                            matches = re.findall(pattern, content)
                            if matches:
                                print(DANGER + f"[!] Potential {label} found in {path}")
                except Exception as e:
                    # Handle file read errors
                    continue
    except Exception as e:
        print(DANGER + f"Error scanning for sensitive data: {str(e)}")

def find_hidden_files(root_dir):
    """List hidden files and directories."""
    try:
        for root, dirs, files in os.walk(root_dir):
            for name in files + dirs:
                if name.startswith('.'):
                    path = os.path.join(root, name)
                    print(WARNING + f"[!] Hidden file or directory: {path}")
    except Exception as e:
        print(DANGER + f"Error finding hidden files: {str(e)}")

def find_suspicious_files(root_dir):
    """Identify files with suspicious extensions or names."""
    try:
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                path = os.path.join(root, file)
                ext = os.path.splitext(file)[1]
                if ext.lower() in SUSPICIOUS_EXTENSIONS:
                    print(WARNING + f"[!] Suspicious file detected: {path}")
    except Exception as e:
        print(DANGER + f"Error finding suspicious files: {str(e)}")

def find_large_files(root_dir, size_threshold=50*1024*1024):
    """Find files larger than the specified threshold."""
    try:
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                path = os.path.join(root, file)
                try:
                    size = os.path.getsize(path)
                    if size > size_threshold:
                        print(INFO + f"[i] Large file detected ({size/(1024*1024):.2f} MB): {path}")
                except Exception as e:
                    continue
    except Exception as e:
        print(DANGER + f"Error finding large files: {str(e)}")

def main():
    print(INFO + "Starting file security and privacy checks...\n")
    
    # Set the root directory to the home directory
    root_dir = os.path.expanduser("~")
    print(INFO + f"Scanning directory: {root_dir}\n")
    
    # Check file permissions
    print(INFO + "Checking file permissions...\n")
    check_file_permissions(root_dir)
    
    # Scan for sensitive data
    print(INFO + "\nScanning for sensitive data...\n")
    scan_for_sensitive_data(root_dir)
    
    # Find hidden files
    print(INFO + "\nLooking for hidden files and directories...\n")
    find_hidden_files(root_dir)
    
    # Find suspicious files
    print(INFO + "\nIdentifying suspicious files...\n")
    find_suspicious_files(root_dir)
    
    # Find large files
    print(INFO + "\nFinding large files...\n")
    find_large_files(root_dir)
    
    print(SUCCESS + "\nFile security and privacy check completed.")
    
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(DANGER + "\nScan interrupted by user.")
    except Exception as e:
        print(DANGER + f"An unexpected error occurred: {str(e)}")
