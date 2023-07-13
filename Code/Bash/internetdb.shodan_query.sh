curl https://internetdb.shodan.io/$(host $1 | head -n 1 | cut -d " " -f 4)
