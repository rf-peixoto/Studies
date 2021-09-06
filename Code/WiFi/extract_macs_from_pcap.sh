# $1 : file.pcap
tcpdump -r $1 | grep -o -E '([[:xdigit:]]{1,2}:){5}[[:xdigit:]]{1,2}' | sort -u
