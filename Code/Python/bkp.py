#!/usr/bin/env python3
"""
Backup all GitHub repositories for the authenticated user.
Requires: Python 3.6+, requests, git (installed and in PATH)
"""

import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' module not installed. Run: pip install requests")
    sys.exit(1)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
GITHUB_API = "https://api.github.com"
REPOS_PER_PAGE = 100  # max is 100
RETRY_DELAY = 5       # seconds when rate limited


def get_headers(token):
    """Return HTTP headers for GitHub API requests."""
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }


def get_all_repos(token):
    """Fetch all repositories (public + private) for the authenticated user."""
    repos = []
    page = 1
    while True:
        url = f"{GITHUB_API}/user/repos"
        params = {
            "per_page": REPOS_PER_PAGE,
            "page": page,
            "visibility": "all",      # public, private, or all
            "affiliation": "owner"    # only repos owned by the user (not orgs)
        }
        response = requests.get(url, headers=get_headers(token), params=params)

        if response.status_code == 401:
            print("Error: Invalid or expired GitHub token.")
            sys.exit(1)
        if response.status_code == 403:
            # Rate limit exceeded
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset_time - time.time(), RETRY_DELAY)
            print(f"Rate limit hit. Waiting {wait:.0f} seconds...")
            time.sleep(wait)
            continue
        if response.status_code != 200:
            print(f"Error fetching repos: HTTP {response.status_code}")
            print(response.text)
            sys.exit(1)

        data = response.json()
        if not data:
            break
        repos.extend(data)

        # Pagination via Link header (simple: stop when fewer than full page)
        if len(data) < REPOS_PER_PAGE:
            break
        page += 1

    return repos


def clone_repo(repo_url, destination_path, token):
    """
    Clone a repository using the token for authentication.
    Uses --mirror for a full backup (all branches, tags, etc.).
    """
    # Inject token into HTTPS URL: https://<token>@github.com/owner/repo.git
    if repo_url.startswith("https://"):
        parts = repo_url.split("https://")
        auth_url = f"https://{token}@{parts[1]}"
    else:
        print(f"  Skipping non-HTTPS repo: {repo_url}")
        return False

    if destination_path.exists():
        print(f"  Directory already exists, skipping: {destination_path}")
        return False

    print(f"  Cloning {repo_url} -> {destination_path}")
    cmd = ["git", "clone", "--mirror", auth_url, str(destination_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"  Successfully cloned {repo_url}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error cloning {repo_url}: {e.stderr}")
        return False


def main():
    # Get token from environment variable or command line argument
    token = os.environ.get("GITHUB_TOKEN")
    if len(sys.argv) > 1:
        token = sys.argv[1]

    if not token:
        print("Usage:")
        print("  export GITHUB_TOKEN='your_pat_here'")
        print("  python backup_github_repos.py")
        print("or directly:")
        print("  python backup_github_repos.py YOUR_TOKEN")
        sys.exit(1)

    # Create output directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path.cwd() / f"github_backup_{timestamp}"
    backup_dir.mkdir(exist_ok=True)
    print(f"Backup directory: {backup_dir}")

    # Fetch all repositories
    print("Fetching repository list from GitHub...")
    repos = get_all_repos(token)
    if not repos:
        print("No repositories found. Check token permissions (needs 'repo' scope).")
        sys.exit(0)

    print(f"Found {len(repos)} repositories to back up.\n")

    # Clone each repository
    success_count = 0
    for repo in repos:
        repo_name = repo["name"]
        clone_url = repo["clone_url"]
        dest = backup_dir / repo_name
        print(f"[{success_count+1}/{len(repos)}] {repo_name}")
        if clone_repo(clone_url, dest, token):
            success_count += 1
        print()  # blank line for readability

    print(f"Backup completed: {success_count} of {len(repos)} repositories cloned.")
    print(f"Backup location: {backup_dir}")


if __name__ == "__main__":
    main()