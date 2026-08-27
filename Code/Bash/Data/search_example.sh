./bhv4.sh search 'string' pool/shards/ --quiet | cut -d ':' -f 3- | awk '!seen[$0]++' > output.txt
