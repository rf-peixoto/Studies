# Removes duplicates without sorting a file:
awk '!seen[$0]++' $1
