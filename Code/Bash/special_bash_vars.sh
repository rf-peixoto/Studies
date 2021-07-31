#!/bin/bash +x

# +x on sheebang include debbuging info.

$0 # Script name
$1-$9 # Nine first args.
$# # Number of arguments passed.
$@ # All arguments passed (at once)
$? # Exit status of the most recent process.
$USER # User running the code.
$HOSTNAME # Machine hostname.
$RANDOM # Random number.
$LINENO # Actual line number on the script.

# Read user input:
read option
echo $option

read -p 'Username: ' user
read -sp 'Password: ' password
