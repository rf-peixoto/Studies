import os
import requests

# Path to your MyBB installation
mybb_root = "/path/to/your/mybb"

# Check MyBB version
def check_mybb_version(path):
    try:
        with open(os.path.join(path, 'inc', 'class_core.php'), 'r') as file:
            for line in file:
                if "define('VERSION'," in line:
                    version = line.split(',')[1].strip().strip("');")
                    print(f"Current MyBB version: {version}")
                    # Here you could add a check to see if this version matches the latest from the MyBB website
                    break
    except IOError:
        print("Unable to determine MyBB version or read the file.")

# Check file permissions
def check_file_permissions(path):
    files_to_check = [
        os.path.join(path, 'inc', 'config.php'),
        os.path.join(path, 'inc', 'settings.php'),
    ]
    
    for file in files_to_check:
        if os.path.isfile(file):
            perms = oct(os.stat(file).st_mode)[-3:]
            if perms != '400' and perms != '600':
                print(f"Warning: File permissions for {file} are not secure: {perms}")
            else:
                print(f"File permissions correct for: {file}")

# Check if config.php is accessible via HTTP
def check_config_access(url):
    try:
        response = requests.get(url + '/inc/config.php')
        if response.status_code == 200:
            print("Warning: config.php is accessible publicly!")
        else:
            print("config.php is not accessible publicly. Good.")
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")

# Run the checks
check_mybb_version(mybb_root)
check_file_permissions(mybb_root)
check_config_access('http://yourforum.com') # Replace with your actual forum URL
