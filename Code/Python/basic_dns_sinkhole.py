from dnslib import DNSRecord, RR
from dnslib.server import DNSServer, BaseResolver

# Define redirection rules using a dictionary
REDIRECTION_RULES = {
    "example.com.": "127.0.0.1",
    "malicious-domain.com.": "192.168.1.100"
}

class SinkholeResolver(BaseResolver):
    def resolve(self, request, handler):
        reply = request.reply()
        query_domain = request.q.qname
        
        # Check if the query domain matches any redirection rule
        if query_domain in REDIRECTION_RULES:
            target_ip = REDIRECTION_RULES[query_domain]
            # Redirect to the specified target IP
            reply.add_answer(*RR.fromZone(f"{query_domain} 60 A {target_ip}"))
        else:
            # If no rule matched, pass through the request
            reply = request.send_next(handler.address, handler.port)
        
        return reply

if __name__ == '__main__':
    resolver = SinkholeResolver()
    server = DNSServer(resolver, port=53, address='0.0.0.0')

    print("DNS Sinkhole listening on 0.0.0.0:53 with predefined rules...")

    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
