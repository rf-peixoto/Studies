#!/bin/bash

# Ref: https://www.linkedin.com/posts/nr025_bugbounty-bugbountytips-xss-activity-7069005687707627520-wWni/?utm_source=share&utm_medium=member_android

cat urls.txt | grep ".php" | sed 's/\.php.*/.php\//' | sort -u | sed s/$/%27%22%60/ | while read url do ; do curl --silent "$url" | grep -qs "You have an error in your SQL syntax" && echo -e "$url \e[1;32mVulnerable\e[0m" || echo -e "$url \e[1;31mNot Vulnerable\e[0m" ;done

cat urls.txt | grep ".php" | sed 's/\.php.*/.php\//' | sort -u | sed s/$/%27%22%60/ | httpx -silent -ms "You have an error in your SQL syntax"
