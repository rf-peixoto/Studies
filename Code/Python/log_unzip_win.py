import os
import subprocess
import shutil

# Update this path according to your 7-Zip installation
SEVEN_ZIP_PATH = r'C:\Program Files\7-Zip\7z.exe'

def decompress_file(archive_path, password, output_dir):
    """Attempt to decompress an archive with the given password using 7z."""
    try:
        # Ensure the command uses the full path to 7z.exe
        subprocess.run([SEVEN_ZIP_PATH, 'x', archive_path, f'-p{password}', f'-o{output_dir}', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        return False

def process_archives(folder_path, password_file, failed_folder):
    """Process all archives in the given folder with passwords from the password file."""
    if not os.path.exists(failed_folder):
        os.makedirs(failed_folder)
    
    with open(password_file, 'r') as pf:
        passwords = pf.read().splitlines()
    
    for file in os.listdir(folder_path):
        if file.endswith(('.rar', '.zip', '.7z')):
            archive_path = os.path.join(folder_path, file)
            output_dir = os.path.dirname(archive_path)
            print(f"Processing {file}...")
            success = False
            
            for password in passwords:
                if decompress_file(archive_path, password, output_dir):
                    print(f"Successfully decompressed {file} with password: {password}")
                    os.remove(archive_path)
                    success = True
                    break
            
            if not success:
                print(f"Failed to decompress {file}, moving to failed folder.")
                shutil.move(archive_path, os.path.join(failed_folder, file))

# Example usage
folder_path = r'C:\Users\User\Downloads\Telegram Desktop'
password_file = r'C:\path\to\your\passwords.txt'
failed_folder = r'C:\path\to\your\failed_folder'
process_archives(folder_path, password_file, failed_folder)
