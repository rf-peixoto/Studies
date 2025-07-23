from imap_tools import MailBox, AND
import os

EMAIL = "email"
PASSWD = "password or application password"
IMAP_FOLDER = "Folder Name"
OUTPUT_FOLDER = "output folder path"

def download_emls():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    with MailBox('imap-mail.outlook.com').login(EMAIL, PASSWD, initial_folder=IMAP_FOLDER) as mailbox:
        for i, msg in enumerate(mailbox.fetch(criteria=AND(all=True), bulk=True), 1):
            title = msg.subject.replace('/', '_').replace('\\', '_').strip() or "untitled"
            filename = f"{i:04d} - {title}.eml"
            output_path = os.path.join(OUTPUT_FOLDER, filename)

            with open(output_path, 'wb') as f:
                f.write(msg.eml_bytes)

            print(f"[{i}] Saved: {filename}")

if __name__ == "__main__":
    download_emls()
