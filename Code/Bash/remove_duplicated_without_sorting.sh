awk '!seen[$0]++' $1 > $1.uniq.txt
