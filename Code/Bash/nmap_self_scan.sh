clear && sudo nmap -sV -Pn --script=vulners --open -D RND:16 $(curl ifconfig.me) #-oX output.xml
