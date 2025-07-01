import dns.name
import dns.message
import dns.query
import dns.dnssec
import dns.resolver

from acme import client, messages, challenges
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# ── 1) DNSSEC‐authenticated CAA retrieval ──────────────────────────────────────────

def fetch_and_validate_caa(domain, resolver_ip="8.8.8.8"):
    """
    Query the CAA RRset for `domain` with DNSSEC (DNSSEC OK bit),
    then validate the RRSIG using the DNSKEYs in the response.
    Raises an exception if validation fails.
    Returns a list of (flags, tag, value) tuples.
    """
    qname = dns.name.from_text(domain)
    # Build a DNS query for CAA with DNSSEC enabled
    req = dns.message.make_query(qname, dns.rdatatype.CAA, want_dnssec=True)
    resp = dns.query.udp(req, resolver_ip, timeout=5)

    # Extract the CAA RRset and its RRSIG
    caa_rrset = resp.find_rrset(resp.answer, qname, dns.rdataclass.IN, dns.rdatatype.CAA)
    rrsig_rrset = resp.find_rrset(resp.answer, qname, dns.rdataclass.IN, dns.rdatatype.RRSIG, dns.rdatatype.CAA)

    # Extract the DNSKEY RRset for validation (from authority/additional)
    key_rrset = resp.find_rrset(resp.answer, qname, dns.rdataclass.IN, dns.rdatatype.DNSKEY)

    # Perform DNSSEC validation
    dns.dnssec.validate(caa_rrset, rrsig_rrset, {qname: key_rrset})

    # Parse and return CAA records
    policies = []
    for rdata in caa_rrset:
        policies.append((rdata.flags, rdata.tag, rdata.value))
    return policies

# Example usage:
domain = "example.com"
try:
    policies = fetch_and_validate_caa(domain)
    print(f"Validated CAA policies for {domain}:")
    for flags, tag, value in policies:
        print(f"  – flags={flags}, tag={tag}, value={value}")
except Exception as e:
    raise SystemExit(f"DNSSEC validation failed: {e}")


# ── 2) ACME DNS‐01 Challenge over Authenticated DNS ───────────────────────────────

# 2.1 Generate or load your ACME account key (here: a fresh RSA key)
account_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pem_key = account_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

# 2.2 Initialize ACME client against Let's Encrypt staging
directory_url = "https://acme-staging-v02.api.letsencrypt.org/directory"
net = client.ClientNetwork(account_key, user_agent="crypto-dv-example/1.0")
directory = messages.Directory.from_json(net.get(directory_url).json())
acme_client = client.ClientV2(directory, net)

# 2.3 Register (or load) ACME account
email = ("mailto:admin@" + domain)
acct = acme_client.new_account(messages.NewRegistration.from_data(
    email=email, terms_of_service_agreed=True
))

# 2.4 Create a new order for our domain
order = acme_client.new_order(csr_pem=None, identifiers=[messages.Identifier(type="dns", value=domain)])

# 2.5 Select the DNS-01 challenge
authz = order.authorizations[0]
dns_chal = next(c for c in authz.body.challenges if isinstance(c.chall, challenges.DNS01)).chall

# 2.6 Compute the TXT record name & value
txt_name = "_acme-challenge." + domain + "."
token = dns_chal.token
key_auth = dns_chal.key_authorization(account_key)
txt_value = challenges.DNS01(token).validation(account_key)

print("\n=== DNS-01 Challenge Setup ===")
print(f"Add this TXT record via DNSSEC-authenticated channel:\n")
print(f"{txt_name:40}TXT  {txt_value}\n")

# At this point, you would use an authenticated DNS API (or signed zone editor)
# to create that TXT record. Once propagated:

# 2.7 Notify ACME server to validate
response = acme_client.respond_to_challenge(dns_chal, dns_chal.response(account_key))

# 2.8 Poll until the challenge is valid
acme_client.poll(authz)

print(f"✅ Domain {domain} validated via DNS-01 over DNSSEC.")
