# $1: JTW / $2: wordlist
# Reference: https://portswigger.net/web-security/jwt
hashcat -a 0 -m 16500 --show $1 $2
