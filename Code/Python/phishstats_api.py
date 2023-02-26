import requests
import sys

# Banner:
print("\033[92m")
print("  _____  _     _     _      _____ _        _")
print(" |  __ \| |   (_)   | |    / ____| |      | |")
print(" | |__) | |__  _ ___| |__ | (___ | |_ __ _| |_ ___")
print(" |  ___/| '_ \| / __| '_ \ \___ \| __/ _` | __/ __|")
print(" | |    | | | | \__ \ | | |____) | || (_| | |_\__ \ ")
print(" |_|    |_| |_|_|___/_| |_|_____/ \__\__,_|\__|___/.info")
print("                            unofficial  API-Searcher")
print("\033[91m  Please do not use this script for scraping phishstats!!\033[00m\n")

# Verify usage:
if len(sys.argv) != 2:
    print("[\033[94m*\033[00m] Usage:")
    print("    \033[92m{0}\033[00m [KEYWORD]    Ex:".format(sys.argv[0]))
    print("    \033[92m{0}\033[00m login".format(sys.argv[0]))
    print("[\033[94m*\033[00m] Check \033[92mphishstats.info\033[00m fore more data.")
    print("\033[00m")
    sys.exit()

# SETUP:
keyword = sys.argv[1]
base_url = "https://phishstats.info:2096/api/phishing?_where=(url,like,~{0}~)&_sort=-id".format(keyword)

# Retrive data:
print("[\033[94m*\033[00m] Retrievening data...")
try:
    data = requests.get(base_url).json()
except Exception as error:
    print("[\033[91m[!]\033[00m Error!\n{0}".format(error))
    sys.exit()

# Print data:
for i in range(1, len(data)):
    print("  [\033[92m+\033[00m] " + data[i]['url'])

# Reset and quit:
print("\n[\033[94m*\033[00m] Check \033[92mphishstats.info\033[00m fore more data.\033[0m")
