awk '{gsub(/\r/,"")} length($0)<=128 && !seen[$0]++' "$1" > "${1}.parsed.txt"
