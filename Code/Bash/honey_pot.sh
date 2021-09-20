#!/bin/bash

# Create Log file:
touch honey.log
# Create Fake Banner:
echo "220 ProFTP 1.3.4a Server (Hanna Montanna Linux)" > banner.txt

# Set permissions:
chmod 777 honey.log
chmod 777 banner.txt

# Open port:
while true;
do
  nc -vnlp 21 < banner.txt >> honey.log 2>> honey.log; echo $(date) >> honey.log;
done;
