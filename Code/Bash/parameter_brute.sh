# Wordlist at https://github.com/danielmiessler/SecLists/blob/master/Discovery/Web-Content/burp-parameter-names.txt
# Dork: inurl:download.php?

# -c: Color
# -z: Use wordlist
# --hl 0: Hide responses with 0 lines (empty)
wfuzz -c -z file,[WORDLIST] --hl 0 https://site.com/file.php?FUZZ=file.php
