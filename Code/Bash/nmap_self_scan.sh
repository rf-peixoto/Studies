clear && sudo nmap -sV -Pn --script=vuln --open -D RND:16 $(curl ifconfig.me) #-oX output.xml

# Categories to use on --script=CATEGORY

#    auth
#    broadcast
#    brute
#    default
#    discovery
#    dos
#    exploit
#    external
#    fuzzer
#    intrusive
#    malware
#    safe
#    version
#    vuln
