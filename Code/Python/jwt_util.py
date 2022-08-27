import sys
import json
import base64

# Usage:
if len(sys.argv) != 3:
    print("JTW Util - Usage:")
    print("Decode JWT: {0} -d [jtw]".format(sys.argv[0]))
    print("Ecnode JWT: {0} -e [jtw.json]".format(sys.argv[0]))
    sys.exit()

# Decode:
if sys.argv[1] == "-d":
    try:
        jwt = sys.argv[2].split(".")
        tmp = ""
        for i in jwt:
            tmp += base64.b64decode(i).decode()
        print(tmp)
    except Exception as error:
        print(error)
