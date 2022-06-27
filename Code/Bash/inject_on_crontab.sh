# Hr Min Day Month Week User Command
echo "\n12 0 10 * 1-5 root /root/script.sh\n" >> /etc/crontab

# Shortcuts:
# @yearly
# @annually
# @monthly
# @weekly
# @daily
# @midnight
# @noon
# @reboot

# Example:
@midnight user /home/user/code.sh
