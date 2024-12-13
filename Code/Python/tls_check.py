"""
Attempts deprecated protocols and weak ciphers to see if the server accepts them.

1. If TLS 1.3 is not supported in your Python/OpenSSL environment, the script gracefully skips it.
2. Use only on fgc.org.br or domains you have explicit permission to test.
3. This does NOT brute-force modern TLS. It enumerates misconfigurations in protocols/ciphers.
"""

import ssl, sys
import socket

TARGET_DOMAIN = sys.argv[1]
TARGET_PORT = 443

def get_protocol_versions():
    """
    Return a list of protocol versions to test.
    Attempt to use TLS 1.3 if available; otherwise skip it.
    """
    protocol_list = []

    # Try TLSv1.3
    try:
        protocol_list.append(ssl.PROTOCOL_TLSv1_3)
    except AttributeError:
        pass  # TLS 1.3 unsupported in current environment

    # TLS 1.2, 1.1, 1.0 are typically present
    protocol_list.append(ssl.PROTOCOL_TLSv1_2)
    protocol_list.append(ssl.PROTOCOL_TLSv1_1)
    protocol_list.append(ssl.PROTOCOL_TLSv1)

    return protocol_list


# Example ciphers from stronger to weaker:
cipher_suites = [
    "ECDHE-ECDSA-AES256-GCM-SHA384", 
    "ECDHE-RSA-AES256-GCM-SHA384",
    "ECDHE-ECDSA-AES128-GCM-SHA256",
    "ECDHE-RSA-AES128-GCM-SHA256",
    "AES256-SHA",     # older, not as strong as GCM
    "RC4-SHA",        # very weak
    "RC4-MD5"         # extremely weak
]

def test_tls_connection(protocol, cipher):
    """
    Attempt to connect to fgc.org.br:443 using a given TLS protocol and cipher.
    Returns True if the handshake succeeds; otherwise False.
    """
    try:
        context = ssl.SSLContext(protocol)
    except (ValueError, ssl.SSLError):
        # Protocol might not be supported on some environments
        return False

    # Try forcing a single cipher suite
    try:
        context.set_ciphers(cipher)
    except ssl.SSLError:
        # The local SSL library does not allow this cipher
        return False

    # No cert verification for this test. We only care if the handshake succeeds.
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    try:
        with socket.create_connection((TARGET_DOMAIN, TARGET_PORT), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=TARGET_DOMAIN) as ssock:
                # If no exception, handshake likely succeeded
                protocol_str = protocol_name(protocol)
                cipher_used = ssock.cipher()
                print(f"[SUCCESS] Protocol: {protocol_str}, Cipher: {cipher_used}")
                return True
    except (ssl.SSLError, socket.error):
        # Handshake failed or connection error => server refused or doesn't support
        return False

def protocol_name(protocol_constant):
    """
    Convert ssl.PROTOCOL_* constant to a human-readable label.
    """
    mapping = {
        getattr(ssl, 'PROTOCOL_TLSv1_3', None): "TLS 1.3",
        ssl.PROTOCOL_TLSv1_2: "TLS 1.2",
        ssl.PROTOCOL_TLSv1_1: "TLS 1.1",
        ssl.PROTOCOL_TLSv1:   "TLS 1.0"
    }
    return mapping.get(protocol_constant, str(protocol_constant))

def main():
    protocols_to_test = get_protocol_versions()

    print(f"Testing deprecated protocols and weak ciphers on {TARGET_DOMAIN}...\n")
    found_insecure = False

    for protocol in protocols_to_test:
        for cipher in cipher_suites:
            result = test_tls_connection(protocol, cipher)
            if result:
                # The server accepted a handshake with the given protocol/cipher.
                print(f" --> Potentially Insecure Config: {protocol_name(protocol)} + {cipher}")
                found_insecure = True

    if not found_insecure:
        print("No deprecated protocols or weak ciphers were accepted. Server appears secure.")

if __name__ == "__main__":
    main()
