#!/usr/bin/env python3
import os
import sys
import time
import requests
from pathlib import Path

API_BASE = "https://api.github.com"


def get_github_token():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    return token


def get_repos(session):
    """
    Return all repositories where the authenticated user is the owner.
    This includes public and private repos, but we will filter out forks.
    """
    repos = []
    page = 1

    while True:
        params = {
            "per_page": 100,
            "page": page,
            # 'owner' means repos the user owns (not just collaborates on)
            "affiliation": "owner",
        }
        resp = session.get(f"{API_BASE}/user/repos", params=params)
        if resp.status_code != 200:
            print(
                f"ERROR: Failed to fetch repos (HTTP {resp.status_code}): {resp.text}",
                file=sys.stderr,
            )
            sys.exit(1)

        batch = resp.json()
        if not batch:
            break

        repos.extend(batch)
        page += 1

    return repos


def safe_filename(name):
    """
    Very simple sanitization for filenames.
    """
    return "".join(c for c in name if c not in r'\/:*?"<>|').strip() or "repo"


def download_repo_zip(session, repo, dest_dir):
    """
    Download the ZIP archive of a repo (default branch) to dest_dir.
    Skips if file already exists.
    """
    name = repo["name"]
    owner = repo["owner"]["login"]
    zip_url = f"{API_BASE}/repos/{owner}/{name}/zipball"

    # Basic filename; if you want to include branch or sha, adapt this.
    base_filename = safe_filename(name)
    out_path = dest_dir / f"{base_filename}.zip"

    # Avoid overwriting if somehow duplicated names appear
    counter = 1
    while out_path.exists():
        out_path = dest_dir / f"{base_filename}_{counter}.zip"
        counter += 1

    print(f"[*] Downloading {owner}/{name} -> {out_path.name}")

    try:
        with session.get(zip_url, stream=True) as r:
            if r.status_code != 200:
                print(
                    f"    [!] Failed (HTTP {r.status_code}): {r.text[:200]}",
                    file=sys.stderr,
                )
                return

            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
    except requests.RequestException as e:
        print(f"    [!] Error downloading {owner}/{name}: {e}", file=sys.stderr)


def main():
    token = get_github_token()

    # Destination directory (can be passed as an argument)
    if len(sys.argv) > 1:
        dest = Path(sys.argv[1])
    else:
        dest = Path("github-backup-zips")

    dest.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-backup-script",
        }
    )

    print("[*] Fetching repositories...")
    repos = get_repos(session)
    print(f"[*] Found {len(repos)} repos owned by you (including forks).")

    # Filter out forks
    own_non_fork_repos = [r for r in repos if not r.get("fork", False)]
    print(f"[*] After excluding forks: {len(own_non_fork_repos)} repos to back up.\n")

    for repo in own_non_fork_repos:
        download_repo_zip(session, repo, dest)
        # Be polite to the API; not strictly necessary but avoids hammering.
        time.sleep(0.2)

    print("\n[*] Done.")


if __name__ == "__main__":
    main()
