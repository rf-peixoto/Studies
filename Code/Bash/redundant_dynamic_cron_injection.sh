# Create your script:

#!/bin/bash

# Path to the cron tab
CRON_TAB="/var/spool/cron/crontabs/root"

# Do your stuff here:
# Stuff

# Remove its own cron entry
sed -i '/script.sh/d' $CRON_TAB

# Schedule 'at' job to re-add this script to cron after 3 hours
echo "echo \"$(date --date='10 minutes' +'%M %H * * *') /path/to/script.sh\" >> $CRON_TAB" | at now + 3 hours


# Initialize the first cronjob:
30 22 * * * /path/to/script.sh

