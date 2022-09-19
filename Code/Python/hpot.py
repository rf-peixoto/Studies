import http.server
import socketserver
import sys

# Setup:
PORT = 8000
handler = http.server.SimpleHTTPRequestHandler
handler.server_version = "nginx"
handler.sys_version = "/1.6.2"
handler.protocol_version = "HTTP/1.1"
handler.error_message_format = "Undefined error."
# Prepare log:
log = open("server.log", "w")
sys.stdout = log
sys.stdin = log
sys.stderr = log


# Start:
try:
    print("[*] Starting server.")
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print("[*] Serving on port {0}.".format(PORT))
        httpd.serve_forever()
except KeyboardInterrupt:
    print("\n[-] Closing.")
    log.close()
    httpd.shutdown()
    httpd.server_close()
