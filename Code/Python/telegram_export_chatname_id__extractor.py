import json,sys

with open(sys.argv[1], "r", encoding="utf-8") as js:
    data = json.load(js)

tmp = []

for i in data['chats']['list']:
    tmp.append("{0},{1}".format(i['name'], i['id']))

with open("output.txt", "w", encoding="utf-8") as fl:
    for t in tmp:
        fl.write(t + '\n')
