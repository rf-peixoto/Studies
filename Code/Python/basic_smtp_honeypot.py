import sys
import os

# Path to store logs
log_file_path = "/path/to/log/file.txt"

def setup_postfix():
    """
    Install and configure Postfix.
    This function will setup Postfix to relay mail to our Python script.
    """
    
    # Install Postfix
    os.system("sudo apt update && sudo apt install -y postfix")
    
    # Configure Postfix to relay mail to this Python script
    postfix_configuration = """
smtp      inet  n       -       y       -       -       smtpd
    -o content_filter=filter:dummy
filter    unix  -       n       n       -       10      pipe
    flags=Rq user={user} argv={script_path} {sender} {size} {recipient}
""".format(user=os.getlogin(), script_path=os.path.abspath(__file__))
    
    with open("/etc/postfix/master.cf", "a") as f:
        f.write(postfix_configuration)
    
    # Reload Postfix to apply changes
    os.system("sudo systemctl reload postfix")


def log_message():
    """
    Logs the email message data.
    The message data is piped into this script when used as a Postfix filter.
    """
    sender = sys.argv[1]
    size = sys.argv[2]
    recipient = sys.argv[3]
    data = sys.stdin.read()

    with open(log_file_path, "a") as f:
        f.write(f"Sender: {sender}\nSize: {size}\nRecipient: {recipient}\nData: {data}\n\n")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # If script is called without arguments, it's for setup
        setup_postfix()
    else:
        # If script is called with arguments, it's for logging
        log_message()
