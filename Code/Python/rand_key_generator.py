import secrets
from datetime import datetime

for i in range(61):
    timestamp = str(datetime.timestamp(datetime.now()))
    key_id = secrets.token_urlsafe(16)
    randbytes = secrets.token_bytes(128)

    with open("key-{0}".format(key_id), "wb") as data:
        data.write(timestamp.encode() + b"\n")
        data.write(randbytes + b"\n")
        data.write(key_id.encode())
