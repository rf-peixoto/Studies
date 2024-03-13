import shodan

KEY='KEY'
api = shodan.Shodan(KEY)

with open("iplist.txt", "r") as fl:
    ip_list = fl.read().split("\n")

data = ""


for i in ip_list:
    try:
        info = api.host(i, minify=True)
        data += "{0}:{1}:{2}\n".format(info['ip_str'], info['domains'], info['ports'])
    except Exception as error:
        data += "Error on {0}: {1}".format(i, error)
        continue

with open("result.txt", "w") as fl:
    fl.write(data)

	
