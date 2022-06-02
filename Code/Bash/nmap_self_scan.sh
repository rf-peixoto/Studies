clear && sudo nmap -sV -Pn --script=vuln --open -D RND:16 $(curl ifconfig.me) #-oX output.xml
