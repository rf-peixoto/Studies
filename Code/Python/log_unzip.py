import os
import patoolib
import shutil

def decompress_file(archive_path, password):
    """Attempt to decompress an archive with the given password."""
    try:
        patoolib.extract_archive(archive_path, outdir=os.path.dirname(archive_path), passwords=[password])
        return True
    except patoolib.util.PatoolError:
        return False

def process_archives(folder_path, password_file, failed_folder):
    """Process all archives in the given folder with passwords from the password file."""
    # Ensure the failed folder exists
    if not os.path.exists(failed_folder):
        os.makedirs(failed_folder)
    
    # Load passwords from the file
    with open(password_file, 'r') as pf:
        passwords = pf.read().splitlines()
    
    # Iterate through all files in the folder
    for file in os.listdir(folder_path):
        if file.endswith(('.rar', '.zip', '.7z')):  # Add other formats if needed
            archive_path = os.path.join(folder_path, file)
            print(f"Processing {file}...")
            success = False
            
            for password in passwords:
                if decompress_file(archive_path, password):
                    print(f"Successfully decompressed {file} with password: {password}")
                    os.remove(archive_path)  # Delete the compressed file
                    success = True
                    break
            
            if not success:
                print(f"Failed to decompress {file}, moving to failed folder.")
                shutil.move(archive_path, os.path.join(failed_folder, file))

# Example usage
folder_path = 'path/to/your/folder'
password_file = 'path/to/your/passwords.txt'
failed_folder = 'path/to/your/failed_folder'
process_archives(folder_path, password_file, failed_folder)

""" Sample passwords.txt

https://t.me/EuropeCloud
https://t.me/PegasusCloud
t.me/wlfrcloud
https://t.me/dragoncloud1
https://t.me/ganjacloud
@watercloud_notify
https://t.me/BananaLogs
https://t.me/luntancloud
@FreeOLDCloud
@TinyLogs
@HarvestGoodLike
@MetaCloudVIP
https://t.me/Logs_Tizix
@MetaCloudVip
https://t.me/cvv190_cloud
https://t.me/scorpionlogs
https://t.me/+kqevP-a_nq44MjQy #BHF
https://t.me/Logs_Tizix
https://t.me/crypton_logs
https://t.me/scorpionlogs
https://t.me/Everlasting_Cloud
https://t.me/Trident_Cloud
https://t.me/SunCloudPubl
@ManticoreCloud
@HAWKLOG
netxworld
t.me/wlfrcloud
https://t.me/dvdcloud_free
@NEW_DAISYCLOUD
https://t.me/CLOUDCASPER
https://t.me/klaus_cloud_public
https://t.me/luntancloud
https://t.me/OmegaCloud_FreeLogs
https://t.me/+2ofZFLh--cdhYzJh # neverhode
https://t.me/+wPskart56f04NGYy # smoker & cloud
https://t.me/LulzsecCloudLogs
https://t.me/FehuCloud
https://t.me/cherry_cloud
@LOGS_CENTER
https://t.me/RedlineLogsGroup
https://t.me/powercloudlogs
@premcloud
https://t.me/PremCloud
https://t.me/prdscloud
"""
