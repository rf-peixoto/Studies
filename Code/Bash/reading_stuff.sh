# Show/hide cursor:
setterm --cursor [on/off]

# Read values:
read -p variable

# Read n chars:
read -n6 variable; echo

# Read with time:
read -t3 -p "Put your question here." response || echo "Failed!"

# Read password:
echo -n "Password: " && read -sp password

# Stop reading after "%" is pressed:
read -p "End your command with %: " -d'%' comm

# Read file with new lines:
read -r data < file.txt
