clear && sudo nmap -sV -Pn --script=vuln -D RND:16 $(curl ifconfig.me)
