# --------------------------------------------------------------------- #
#
#
# --------------------------------------------------------------------- #
import requests
import socket

print("\nWellcome. Input pattern: domain.com\n")
# Config -------------------------------------------------------------- #
url = input("Url: ")
host = socket.gethostbyname(url)

# Connection ---------------------------------------------------------- #
request = requests.get("http://" + url)

# Print --------------------------------------------------------------- #
print("\nURL: {0}".format(url))
print("HOST: {0}".format(host))
print("STATUS: {0} {1}".format(request.status_code, request.reason))
print("SERVER:: {0}".format(request.headers['Server']))
print("METHOD: {0}".format(request.request.method))
print("TYPE: {0}".format(request.headers['Content-Type']))

# Subdomains ---------------------------------------------------------- #
if not (request.ok):
    print("\nERROR! Status code: {0} {1}\n".format(request.status_code, request.reason))
else:
    while True:
        try:
            test_sub = input("\nLook for subdomains? <y/n>: ")
            if test_sub in "nN":
                break
            if test_sub in "yY":
                word_list = input("Wordlist file: ")
                try:
                    with open(word_list, "r") as word_list_file:
                        for line in word_list_file:
                            dns_request = requests.get("http://" + line + "." + url)
                            if dns_resquet.ok:
                                print(dns_request.url + " found!")
                                dns_request.close()
                        word_list_file.close()
                    break
                except Exception as error:
                    print(error)
                    break
            else:
                print("Invalid option. Try again.")
                continue
        except Exception as error:
            print(error)
            break

# --------------------------------------------------------------------- #
input("\nPress anything to quit.")
