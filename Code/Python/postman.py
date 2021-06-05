# ======================================================= #
# PyPostman v0.0.3
# Simple tool to manage HTTP Requests
# Usage:
# python postman.py [DOMAIN] [PATH]
# ====================================================== #
import sys
import socket
import urllib.parse

# CONFIG:
method = 'GET' # GET / PUT / POST / OPTIONS / DELETE / MOVE
host = sys.argv[1]
path = sys.argv[2]
port = 80
user_agent = 'BotName'
referer = 'no-referer-when-downgrade'
cookie = ''
payload = urllib.parse.quote('')
content_length = len(payload)
bytes_to_receive = 1024

# REQUEST:
# Change '/' to path:
request = """{0} {1} HTTP/1.0\r\n
Host: {2}\r\n
User-Agent: {3}\r\n
Accept: text/html, application/xhtml+xml, application/xml;q=0.9,*/*;q=0.8\r\n
Accept-Language: en-US, en;q=0.5\r\n
Accept-Encoding: gzip, deflate\r\n
Cache-Control: no-cache\r\n
Pragma: no-cache\r\n
Referer: {4}\r\n
Content-Length: {5}\r\n
DNT: 1\r\n
Connection: close\r\n
Cookie = {6}\r\n
\r\n
{7}""".format(method, path, host, user_agent, referer, content_length, cookie, payload)

# SOCKET
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((host, port))

# SEND
s.send(request.encode())
print(s.recv(bytes_to_receive).decode())
