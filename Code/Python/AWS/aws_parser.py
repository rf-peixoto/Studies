#!/usr/bin/env python3
"""
aws_url_parser.py

Parse text logs and extract information from AWS-signed URLs, especially S3
pre-signed URLs or query-signed URLs that contain AWSAccessKeyId.

For each URL, the script tries to extract:
- Access Key ID (AKIA..., ASIA..., etc.)
- Signing date (from X-Amz-Credential)
- Region (from X-Amz-Credential or host)
- Bucket / object key (for S3-like hosts)
- Session token (if present)
- Expiration time (from X-Amz-Date + X-Amz-Expires)
- Classification of credential artefact
- "Usability score" (0–100) for use as AWS credentials (SDK/CLI)
"""

import sys
import re
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime, timedelta, timezone

# ============================================================
# ANSI colors
# ============================================================

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

FG_RED = "\033[31m"
FG_GREEN = "\033[32m"
FG_YELLOW = "\033[33m"
FG_BLUE = "\033[34m"
FG_MAGENTA = "\033[35m"
FG_CYAN = "\033[36m"
FG_WHITE = "\033[37m"


def color(text, *styles):
    return "".join(styles) + str(text) + RESET


# ============================================================
# URL detection
# ============================================================

URL_REGEX = re.compile(r"https?://\S+")


def find_urls(line: str):
    """Return all URLs found in a text line."""
    return URL_REGEX.findall(line)


# ============================================================
# S3 path helpers
# ============================================================

def parse_s3_bucket_and_key(parsed):
    """
    Infer bucket and key for S3-style hosts.

    Handles patterns:
      - bucket.s3.region.amazonaws.com
      - bucket.s3.amazonaws.com
      - s3.region.amazonaws.com/bucket/key
      - s3.amazonaws.com/bucket/key

    Returns (bucket, key) or (None, None).
    """
    host = parsed.netloc
    path = parsed.path.lstrip("/")

    bucket = None
    key = None

    # bucket.s3.region.amazonaws.com
    m = re.match(r"^(?P<bucket>[^.]+)\.s3[.-](?P<region>[a-z0-9-]+)\.amazonaws\.com$", host)
    if m:
        bucket = m.group("bucket")
        key = path or None
        return bucket, key

    # bucket.s3.amazonaws.com
    m = re.match(r"^(?P<bucket>[^.]+)\.s3\.amazonaws\.com$", host)
    if m:
        bucket = m.group("bucket")
        key = path or None
        return bucket, key

    # s3.region.amazonaws.com/bucket/key
    m = re.match(r"^s3[.-](?P<region>[a-z0-9-]+)\.amazonaws\.com$", host)
    if m and path:
        parts = path.split("/", 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ""
        return bucket, key

    # s3.amazonaws.com/bucket/key
    if host == "s3.amazonaws.com" and path:
        parts = path.split("/", 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ""
        return bucket, key

    return None, None


# ============================================================
# Credential classification & usability scoring
# ============================================================

def classify_access_key_id(access_key_id: str) -> str:
    """
    Rough classification of the access key id based on prefix.
    """
    if not access_key_id:
        return "None"

    if access_key_id.startswith("ASIA"):
        return "STS_TemporaryAccessKeyId"

    # Common long-lived IAM user/root patterns start with these
    if access_key_id.startswith(("AKIA", "AGPA", "AIDA", "ANPA", "AROA")):
        return "LongLivedAccessKeyId"

    # Generic fallback
    return "UnknownAccessKeyPattern"


def classify_credential_artifact(info: dict) -> str:
    """
    Classify what kind of AWS artefact this URL looks like.
    """
    qs = info.get("raw_query", {})
    has_x_amz_alg = any(k.lower() == "x-amz-algorithm" for k in qs.keys())
    has_x_amz_sig = any(k.lower() == "x-amz-signature" for k in qs.keys())
    has_x_amz_cred = any(k.lower() == "x-amz-credential" for k in qs.keys())
    has_aws_access_key = any(k.lower() == "awsaccesskeyid" for k in qs.keys())

    if has_x_amz_alg and has_x_amz_sig and has_x_amz_cred:
        # Signature V4 pre-signed style
        if info.get("session_token"):
            return "PresignedURL_With_STS_Token"
        return "PresignedURL_SigV4"

    if has_aws_access_key:
        # Legacy query auth style
        if info.get("session_token"):
            return "QuerySignedURL_With_STS_Token"
        return "QuerySignedURL"

    if info.get("access_key_id"):
        return "URL_With_AccessKeyId_Only"

    return "NotAWSOrUnclassified"


def compute_usability_score(info: dict) -> (int, str):
    """
    Give a rough "usability score" for the extracted data as AWS credentials.

    0    = not usable at all
    1-30 = partial artefact (access key id and/or session token only)
    100  = full credential set (AK + secret (+ token)) – will never happen from URLs alone.
    """
    access_key_id = info.get("access_key_id")
    session_token = info.get("session_token")
    has_secret = False  # From URLs this is *always* False.

    # Base cases
    if not access_key_id and not session_token:
        return 0, "No AWS credential artefacts detected"

    if access_key_id and not session_token and not has_secret:
        return 10, "AccessKeyId only (no secret, no session token)"

    if access_key_id and session_token and not has_secret:
        return 20, "AccessKeyId + session token (no secret key; cannot be used by SDK/CLI)"

    # Hypothetical case if you ever plug in secrets from another source
    if access_key_id and has_secret and session_token:
        return 100, "Full STS credential triplet (AK + secret + session token)"

    if access_key_id and has_secret:
        return 80, "Long-lived credential pair (AK + secret)"

    return 5, "Unusual artefact; treat as non-usable"


# ============================================================
# Expiration calculation
# ============================================================

def parse_amz_datetime(dt_str: str) -> datetime | None:
    """
    Parse X-Amz-Date format: YYYYMMDD'T'HHMMSS'Z'
    Example: 20250704T141306Z
    """
    try:
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def compute_expiration(info: dict):
    """
    Compute expiration details based on X-Amz-Date and X-Amz-Expires.
    Adds:
      - expires_at (datetime or None)
      - expired (bool or None)
      - seconds_until_expiry (int or None)
    """
    qs = info.get("raw_query", {})

    # Get X-Amz-Date
    amz_date_str = None
    for k in qs.keys():
        if k.lower() == "x-amz-date":
            amz_date_str = qs[k][0]
            break

    # Get X-Amz-Expires
    expires_str = None
    for k in qs.keys():
        if k.lower() == "x-amz-expires":
            expires_str = qs[k][0]
            break

    if not amz_date_str or not expires_str:
        info["expires_at"] = None
        info["expired"] = None
        info["seconds_until_expiry"] = None
        return

    start = parse_amz_datetime(amz_date_str)
    try:
        seconds = int(expires_str)
    except ValueError:
        seconds = None

    if not start or seconds is None:
        info["expires_at"] = None
        info["expired"] = None
        info["seconds_until_expiry"] = None
        return

    expires_at = start + timedelta(seconds=seconds)
    now = datetime.now(timezone.utc)

    info["expires_at"] = expires_at
    info["expired"] = now > expires_at
    info["seconds_until_expiry"] = int((expires_at - now).total_seconds())


# ============================================================
# Core extractor
# ============================================================

def extract_aws_info(url: str):
    """
    Given a URL, try to extract AWS-related signing information.

    Returns a dict with keys like:
      - url, host, access_key_id, signing_date, region
      - bucket, object_key
      - has_session_token, session_token
      - is_aws_signed
      - classification
      - usability_score, usability_reason
      - expires_at, expired, seconds_until_expiry
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    info = {
        "url": url,
        "host": parsed.netloc,
        "access_key_id": None,
        "signing_date": None,
        "region": None,
        "bucket": None,
        "object_key": parsed.path.lstrip("/") or None,
        "has_session_token": False,
        "session_token": None,
        "is_aws_signed": False,
        "raw_query": qs,  # for internal use (classification, expiration)
        "credential_type": None,
        "usability_score": 0,
        "usability_reason": "",
        "expires_at": None,
        "expired": None,
        "seconds_until_expiry": None,
    }

    # 1) Access key from X-Amz-Credential
    cred_param = None
    for k in qs.keys():
        if k.lower() == "x-amz-credential":
            cred_param = qs[k][0]
            break

    if cred_param:
        cred = unquote(cred_param)
        parts = cred.split("/")
        if len(parts) >= 1:
            info["access_key_id"] = parts[0]
        if len(parts) >= 2:
            info["signing_date"] = parts[1]
        if len(parts) >= 3:
            info["region"] = parts[2]
        info["is_aws_signed"] = True

    # 2) Access key from AWSAccessKeyId (older style)
    if not info["access_key_id"]:
        for k in qs.keys():
            if k.lower() == "awsaccesskeyid":
                info["access_key_id"] = qs[k][0]
                info["is_aws_signed"] = True
                break

    # 3) Session token
    for k in qs.keys():
        if k.lower() in ("x-amz-security-token", "x-amz-security-token".lower()):
            info["session_token"] = qs[k][0]
            info["has_session_token"] = True
            info["is_aws_signed"] = True
            break

    # 4) Region heuristics from host if not set
    if not info["region"]:
        m = re.search(r"\.s3[.-]([a-z0-9-]+)\.amazonaws\.com$", info["host"])
        if m:
            info["region"] = m.group(1)
        else:
            m = re.search(r"^s3[.-]([a-z0-9-]+)\.amazonaws\.com$", info["host"])
            if m:
                info["region"] = m.group(1)

    # 5) Bucket / key for S3
    bucket, key = parse_s3_bucket_and_key(parsed)
    if bucket:
        info["bucket"] = bucket
    if key:
        info["object_key"] = key

    # 6) Credential classification
    ak_type = classify_access_key_id(info["access_key_id"]) if info["access_key_id"] else "None"
    artifact_class = classify_credential_artifact(info)
    info["credential_type"] = f"{artifact_class} / {ak_type}"

    # 7) Usability scoring
    score, reason = compute_usability_score(info)
    info["usability_score"] = score
    info["usability_reason"] = reason

    # 8) Expiration info
    compute_expiration(info)

    return info


# ============================================================
# Pretty print
# ============================================================

def pretty_print_info(info: dict):
    # Choose color based on usability score and type
    score = info["usability_score"]
    cred_type = info["credential_type"]

    if score == 0:
        header_color = DIM + FG_WHITE
    elif score <= 20:
        header_color = FG_YELLOW
    elif score < 80:
        header_color = FG_MAGENTA
    else:
        header_color = FG_RED  # Highly sensitive (hypothetically)

    print(color("============================================================", header_color))

    print(color("URL           :", BOLD), info["url"])
    print(color("Host          :", BOLD), info["host"])
    print(color("AWS Signed    :", BOLD), info["is_aws_signed"])

    if info["access_key_id"]:
        print(color("AccessKeyId   :", BOLD), color(info["access_key_id"], FG_CYAN))
    if info["signing_date"]:
        print(color("Signing Date  :", BOLD), info["signing_date"])
    if info["region"]:
        print(color("Region        :", BOLD), info["region"])
    if info["bucket"]:
        print(color("Bucket        :", BOLD), info["bucket"])
    if info["object_key"]:
        print(color("Object Key    :", BOLD), info["object_key"])

    print(color("Session Token :", BOLD), "Yes" if info["has_session_token"] else "No")
    if info["session_token"]:
        print(color("Token Value   :", BOLD), info["session_token"])

    # Expiration details
    if info["expires_at"] is not None:
        exp_str = info["expires_at"].isoformat()
        status = "expired" if info["expired"] else "valid"
        status_color = FG_RED if info["expired"] else FG_GREEN
        print(color("Expires At    :", BOLD), exp_str, f"({color(status, status_color)})")
        print(color("Time Δ (s)    :", BOLD), info["seconds_until_expiry"])
    else:
        print(color("Expires At    :", BOLD), "Unknown / not provided")

    # Credential classification & usability
    print(color("Cred Type     :", BOLD), cred_type)
    print(color("Usability     :", BOLD),
          f"{score}/100 - {info['usability_reason']}")

    print(color("============================================================", header_color))
    print()


# ============================================================
# Stream processing
# ============================================================

def process_stream(f):
    """Read lines, find URLs, and print AWS info where applicable."""
    for line in f:
        line = line.strip()
        if not line:
            continue

        urls = find_urls(line)
        if not urls:
            continue

        for url in urls:
            info = extract_aws_info(url)
            # If you want to skip non-AWS URLs, uncomment:
            # if not info["is_aws_signed"]:
            #     continue
            pretty_print_info(info)


def main():
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        with open(sys.argv[1], "r", encoding="utf-8", errors="ignore") as f:
            process_stream(f)
    else:
        process_stream(sys.stdin)


if __name__ == "__main__":
    main()
