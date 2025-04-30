import requests
import socket
import sys
import base64
import json
from datetime import datetime

# --- Configuration ---
HOST = sys.argv[1]
PORT = 443
USE_HTTPS = True
VERIFY_SSL = True  # Set False if using self-signed certs
USERNAME = "admin"
PASSWORD = "password"

# Endpoints to test
ENDPOINTS = [
    "/settings",
    "/flows",
    "/nodes",
    "/context",
    "/context/global",
    "/context/flow",
    "/users",
    "/metrics",
    "/auth/logout"
]

protocol = "https" if USE_HTTPS else "http"
BASE_URL = f"{protocol}://{HOST}"
TOKEN_URL = f"{BASE_URL}/auth/token"
INVALID_URL = f"{BASE_URL}/invalid-path-xyz"


# --- Step 1: DNS Resolution and TCP Connectivity ---
try:
    ip = socket.gethostbyname(HOST)
    print(f"[INFO] Host resolved: {HOST} -> {ip}")
except socket.gaierror as e:
    print(f"[ERROR] DNS resolution failed: {e}")
    sys.exit(1)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
try:
    sock.connect((HOST, PORT))
    sock.close()
    print(f"[INFO] TCP connection to {HOST}:{PORT} successful")
except socket.error as e:
    print(f"[ERROR] TCP connection failed: {e}")
    sys.exit(1)

# --- Step 2: Acquire Token ---
payload = {
    "client_id": "node-red-editor",
    "grant_type": "password",
    "scope": "*",
    "username": USERNAME,
    "password": PASSWORD
}

headers = {
    "Content-Type": "application/x-www-form-urlencoded"
}

print(f"[INFO] Requesting token from {TOKEN_URL}")
try:
    response = requests.post(TOKEN_URL, data=payload, headers=headers, timeout=10, verify=VERIFY_SSL)
    print(f"[INFO] Token request status: {response.status_code}")
    if response.status_code == 200:
        token = response.json().get("access_token")
        if not token:
            print("[ERROR] No access_token in response.")
            sys.exit(1)
        print("[SUCCESS] Token acquired.")
    else:
        print("[ERROR] Failed to retrieve token.")
        print(response.text)
        sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Token request failed: {e}")
    sys.exit(1)

# --- Step 3: Decode and Analyze JWT ---
def decode_jwt(jwt_token):
    try:
        parts = jwt_token.split(".")
        if len(parts) != 3:
            print("[ERROR] Invalid JWT structure.")
            return None, None

        def decode_segment(segment):
            padded = segment + '=' * (4 - len(segment) % 4)
            return json.loads(base64.urlsafe_b64decode(padded))

        header = decode_segment(parts[0])
        payload = decode_segment(parts[1])

        print("[INFO] JWT Header:")
        print(json.dumps(header, indent=2))
        print("[INFO] JWT Payload:")
        print(json.dumps(payload, indent=2))
        return header, payload

    except Exception as e:
        print(f"[ERROR] JWT decoding failed: {e}")
        return None, None

def validate_jwt(header, payload):
    print("\n[INFO] Validating JWT claims...")

    if not payload:
        print("[ERROR] No payload to validate.")
        return

    now = datetime.utcnow()

    # exp
    exp = payload.get("exp")
    if exp:
        exp_time = datetime.utcfromtimestamp(exp)
        print(f"[CLAIM] exp (expires): {exp_time} UTC")
        if exp_time < now:
            print("[ERROR] Token is expired.")
    else:
        print("[WARNING] No 'exp' field in token.")

    # iat
    iat = payload.get("iat")
    if iat:
        iat_time = datetime.utcfromtimestamp(iat)
        print(f"[CLAIM] iat (issued): {iat_time} UTC")

    # scope
    scope = payload.get("scope")
    if scope:
        print(f"[CLAIM] scope: {scope}")
        if scope != "*" and "Portal" not in str(scope):
            print("[WARNING] Token scope may be restricted.")

    # aud
    aud = payload.get("aud")
    if aud:
        print(f"[CLAIM] aud: {aud}")

    # iss
    iss = payload.get("iss")
    if iss:
        print(f"[CLAIM] iss: {iss}")

    # sub
    sub = payload.get("sub")
    if sub:
        print(f"[CLAIM] sub: {sub}")

    # client
    client = payload.get("client") or payload.get("client_id")
    if client:
        print(f"[CLAIM] client: {client}")

    # SystemUser
    system_user = payload.get("SystemUser")
    if system_user:
        print(f"[CLAIM] SystemUser: {system_user}")

    # Other fields
    for key in payload:
        if key not in {"exp", "iat", "scope", "aud", "iss", "sub", "client", "SystemUser"}:
            print(f"[CLAIM] {key}: {payload[key]}")

    # alg
    alg = header.get("alg") if header else None
    if alg:
        print(f"[HEADER] alg: {alg}")
        if alg.lower() == "none":
            print("[CRITICAL] Insecure token: alg=none")

jwt_header, jwt_payload = decode_jwt(token)
validate_jwt(jwt_header, jwt_payload)

# --- Step 4: Endpoint Access Test ---
auth_headers = {
    "Authorization": f"Bearer {token}"
}

print("\n[INFO] Testing access to protected endpoints:\n")

for endpoint in ENDPOINTS:
    url = f"{BASE_URL}{endpoint}"
    print(f"  [TEST] {endpoint}")

    # GET request
    try:
        resp = requests.get(url, headers=auth_headers, timeout=10, verify=VERIFY_SSL)
        print(f"    GET      -> {resp.status_code}")
        print(f"    [HEADERS] {resp.headers}")
        print(f"    [BODY]    {resp.text[:300]}...\n")
    except requests.exceptions.RequestException as e:
        print(f"    [ERROR] GET failed: {e}")

    # OPTIONS request
    try:
        resp = requests.options(url, headers=auth_headers, timeout=10, verify=VERIFY_SSL)
        allow = resp.headers.get('Allow', 'N/A')
        print(f"    OPTIONS  -> {resp.status_code}, Allow: {allow}")
    except requests.exceptions.RequestException as e:
        print(f"    [ERROR] OPTIONS failed: {e}")
    print("-" * 60)

# --- Step 5: Invalid Endpoint Test ---
print(f"\n[INFO] Testing invalid endpoint: {INVALID_URL}")
try:
    resp = requests.get(INVALID_URL, headers=auth_headers, timeout=10, verify=VERIFY_SSL)
    print(f"  [INVALID] Response Code: {resp.status_code}")
    print(f"  [HEADERS] {resp.headers}")
    print(f"  [BODY]    {resp.text[:300]}...")
except requests.exceptions.RequestException as e:
    print(f"  [ERROR] Invalid test failed: {e}")
