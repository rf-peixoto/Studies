"""Username existence checker (the engine behind the Usernames module).

Pure, framework-free logic so it is easy to test and reason about. The Flask
views pass in the configured targets plus request settings (user-agent,
timeout, worker count) and get back a list of result dicts.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import requests

# Detection methods a target may use.
METHOD_STATUS = "status"          # exists if HTTP status is in expected_status
METHOD_BODY_CONTAINS = "body_contains"  # exists if `match` appears in the body
METHOD_BODY_ABSENT = "body_absent"      # exists if `match` is ABSENT from the body
METHODS = (METHOD_STATUS, METHOD_BODY_CONTAINS, METHOD_BODY_ABSENT)


def build_url(template: str, username: str) -> str:
    """Insert the (already URL-encoded) username into a target template.

    Uses the {} placeholder if present, otherwise appends to the end. This lets
    the username sit anywhere: 'https://x.com/u/{}/about' or 'https://x.com/u/'.
    """
    encoded = quote(username, safe="")
    if "{}" in template:
        return template.replace("{}", encoded)
    return template + encoded


def _decide(method: str, status_code: int, expected_status, body: str, match: str) -> bool:
    if method == METHOD_BODY_CONTAINS:
        return bool(match) and match.lower() in body.lower()
    if method == METHOD_BODY_ABSENT:
        # A profile exists when the "not found" marker is absent and the page loaded.
        return status_code < 400 and not (match and match.lower() in body.lower())
    # Default: status-code match.
    return status_code in (expected_status or [200])


def check_one(target: dict, username: str, *, user_agent: str, timeout: int) -> dict:
    """Check a single target. Never raises — failures are returned as 'error'."""
    url = build_url(target["url"], username)
    result = {
        "name": target.get("name") or target["url"],
        "url": url,
        "status": "error",     # found | absent | error
        "code": None,
        "note": "",
    }
    method = target.get("method", METHOD_STATUS)
    need_body = method in (METHOD_BODY_CONTAINS, METHOD_BODY_ABSENT)
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": user_agent, "Accept-Language": "en-US,en;q=0.9"},
            timeout=timeout,
            allow_redirects=True,
        )
        body = resp.text if need_body else ""
        found = _decide(method, resp.status_code, target.get("expected_status"),
                        body, target.get("match", ""))
        result["code"] = resp.status_code
        result["status"] = "found" if found else "absent"
    except requests.exceptions.Timeout:
        result["note"] = "timed out"
    except requests.exceptions.RequestException as exc:
        result["note"] = type(exc).__name__
    return result


def run_checks(targets: list[dict], username: str, *, user_agent: str,
               timeout: int, max_workers: int) -> list[dict]:
    """Run all enabled targets concurrently. Order of input is preserved."""
    active = [t for t in targets if t.get("enabled", True)]
    if not active:
        return []
    workers = max(1, min(max_workers, len(active)))
    results_by_index: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(check_one, t, username, user_agent=user_agent, timeout=timeout): i
            for i, t in enumerate(active)
        }
        for fut in as_completed(futures):
            results_by_index[futures[fut]] = fut.result()
    return [results_by_index[i] for i in range(len(active))]
