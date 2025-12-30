#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import stat
import shutil
import argparse
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, List, Optional

GITHUB_API = "https://api.github.com"
CODEBERG_API = "https://codeberg.org/api/v1"


# ----------------------------
# Console colors (ANSI)
# ----------------------------
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"


def supports_ansi() -> bool:
    if os.name != "nt":
        return True
    term = os.getenv("TERM", "")
    wt = os.getenv("WT_SESSION")
    return bool(wt) or "xterm" in term.lower() or "vt" in term.lower()


ANSI = supports_ansi()


def color(s: str, code: str) -> str:
    if not ANSI:
        return s
    return f"{code}{s}{C.RESET}"


def info(msg: str) -> None:
    print(color("[*] ", C.CYAN) + msg)


def ok(msg: str) -> None:
    print(color("[+] ", C.GREEN) + msg)


def warn(msg: str) -> None:
    print(color("[!] ", C.YELLOW) + msg)


def err(msg: str) -> None:
    print(color("[x] ", C.RED) + msg)


# ----------------------------
# HTTP helpers
# ----------------------------
def http_json(url: str, headers: Dict[str, str], method: str = "GET", data: Optional[dict] = None):
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, headers=headers, method=method, data=body)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return None, resp.status, dict(resp.headers)
            return json.loads(raw), resp.status, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            j = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            j = raw
        return j, e.code, dict(e.headers)
    except Exception as e:
        raise RuntimeError(f"HTTP request failed for {url}: {e}") from e


# ----------------------------
# Process helpers
# ----------------------------
def run(cmd: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> str:
    p = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=False,
    )
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}\n\nOutput:\n{p.stdout}")
    return p.stdout


def ensure_host_is_not_github(url: str) -> None:
    host = urllib.parse.urlparse(url).hostname or ""
    if host.lower().endswith("github.com"):
        raise RuntimeError("Safety check failed: refusing to push to github.com (backup-only).")


# ----------------------------
# GitHub / Codeberg API
# ----------------------------
def github_list_repos(github_pat: str, include_orgs: bool, include_forks: bool) -> List[dict]:
    headers = {
        "Authorization": f"token {github_pat}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-to-codeberg-mirror",
    }

    repos: List[dict] = []
    page = 1
    per_page = 100
    repo_type = "all" if include_orgs else "owner"

    while True:
        url = f"{GITHUB_API}/user/repos?per_page={per_page}&page={page}&type={repo_type}"
        data, status, _ = http_json(url, headers=headers)
        if status != 200:
            raise RuntimeError(f"GitHub API error listing repos (status={status}): {data}")

        if not data:
            break

        for r in data:
            if not include_forks and r.get("fork"):
                continue
            repos.append(r)

        if len(data) < per_page:
            break
        page += 1

    return repos


def codeberg_get_user(codeberg_token: str) -> dict:
    headers = {"Authorization": f"token {codeberg_token}", "Accept": "application/json"}
    data, status, _ = http_json(f"{CODEBERG_API}/user", headers=headers)
    if status != 200:
        raise RuntimeError(f"Codeberg API error fetching user (status={status}): {data}")
    return data


def codeberg_repo_exists(codeberg_token: str, owner: str, repo: str) -> bool:
    headers = {"Authorization": f"token {codeberg_token}", "Accept": "application/json"}
    _, status, _ = http_json(f"{CODEBERG_API}/repos/{owner}/{repo}", headers=headers)
    return status == 200


def codeberg_create_repo(codeberg_token: str, name: str, private: bool, description: str = "", default_branch: str = "main"):
    headers = {"Authorization": f"token {codeberg_token}", "Accept": "application/json"}
    payload = {
        "name": name,
        "private": bool(private),
        "description": description or "",
        "default_branch": default_branch,
    }
    data, status, _ = http_json(f"{CODEBERG_API}/user/repos", headers=headers, method="POST", data=payload)
    if status in (200, 201, 409):
        return data
    raise RuntimeError(f"Codeberg API error creating repo '{name}' (status={status}): {data}")


# ----------------------------
# Windows-safe deletion
# ----------------------------
def _on_rm_error(func, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def rmtree_with_retries(path: str, retries: int = 10, delay: float = 0.4) -> None:
    if not os.path.exists(path):
        return

    for i in range(retries):
        try:
            shutil.rmtree(path, onerror=_on_rm_error)
            return
        except (PermissionError, OSError):
            time.sleep(delay * (i + 1))

    shutil.rmtree(path, onerror=_on_rm_error)


# ----------------------------
# Git credential handling (avoid token in URL)
# ----------------------------
def make_askpass_script(temp_dir: str, username: str, password: str) -> str:
    os.makedirs(temp_dir, exist_ok=True)
    if os.name == "nt":
        script_path = os.path.join(temp_dir, "askpass.bat")
        content = f"""@echo off
set PROMPT=%~1
echo %PROMPT% | findstr /I "Username" >nul
if %errorlevel%==0 (
  echo {username}
  exit /b 0
)
echo %PROMPT% | findstr /I "Password" >nul
if %errorlevel%==0 (
  echo {password}
  exit /b 0
)
echo {password}
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(content)
        return script_path
    else:
        script_path = os.path.join(temp_dir, "askpass.sh")
        content = f"""#!/bin/sh
case "$1" in
  *Username*) echo "{username}" ;;
  *Password*) echo "{password}" ;;
  *) echo "{password}" ;;
esac
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(script_path, 0o700)
        return script_path


def git_env_for_askpass(askpass_path: str) -> Dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = askpass_path
    env["SSH_ASKPASS"] = askpass_path
    return env


# ----------------------------
# Mirror logic (skip GitHub PR refs)
# ----------------------------
SKIP_REF_PREFIXES = (
    "refs/pull/",          # GitHub PR refs (blocked by Forgejo/Gitea)
    "refs/merge-requests/",# GitLab-style; safe to skip if ever present
)

def delete_skipped_refs(repo_dir: str, env: Dict[str, str]) -> int:
    """
    Remove refs that are known to be rejected by Codeberg hooks.
    Returns number of deleted refs.
    """
    out = run(["git", "for-each-ref", "--format=%(refname)"], cwd=repo_dir, env=env)
    refs = [line.strip() for line in out.splitlines() if line.strip()]
    to_delete = [r for r in refs if any(r.startswith(p) for p in SKIP_REF_PREFIXES)]
    for r in to_delete:
        run(["git", "update-ref", "-d", r], cwd=repo_dir, env=env)
    return len(to_delete)


def git_force_mirror_push(github_clone_url: str, codeberg_https_url: str, workdir: str, env: Dict[str, str]) -> None:
    """
    "Force mirror" that works with Forgejo:
    - Clone mirror from GitHub (read-only)
    - Delete GitHub-only PR refs (refs/pull/*)
    - Push branches/tags (force+prune) to keep Codeberg aligned
    """
    ensure_host_is_not_github(codeberg_https_url)

    if os.path.isdir(workdir):
        rmtree_with_retries(workdir)

    run(["git", "clone", "--mirror", github_clone_url, workdir], env=env)

    remotes = run(["git", "remote"], cwd=workdir, env=env).splitlines()
    if "codeberg" in remotes:
        run(["git", "remote", "set-url", "codeberg", codeberg_https_url], cwd=workdir, env=env)
    else:
        run(["git", "remote", "add", "codeberg", codeberg_https_url], cwd=workdir, env=env)

    deleted = delete_skipped_refs(workdir, env=env)
    if deleted:
        warn(f"Skipped {deleted} internal refs (e.g., refs/pull/*) that Codeberg blocks.")

    # Force mirror only for namespaces Codeberg accepts:
    # branches:
    run(["git", "push", "--force", "--prune", "codeberg", "refs/heads/*:refs/heads/*"], cwd=workdir, env=env)
    # tags:
    run(["git", "push", "--force", "--prune", "codeberg", "refs/tags/*:refs/tags/*"], cwd=workdir, env=env)

    # Optional: notes. Uncomment if you use notes and want them mirrored.
    # run(["git", "push", "--force", "--prune", "codeberg", "refs/notes/*:refs/notes/*"], cwd=workdir, env=env)


def main():
    ap = argparse.ArgumentParser(description="Force-mirror GitHub repos to Codeberg (backup).")
    ap.add_argument("--github-pat", default=os.getenv("GITHUB_PAT"), help="GitHub PAT (or env GITHUB_PAT).")
    ap.add_argument("--codeberg-token", default=os.getenv("CODEBERG_TOKEN"), help="Codeberg token (or env CODEBERG_TOKEN).")
    ap.add_argument("--include-orgs", action="store_true", help="Include repos you can access via orgs.")
    ap.add_argument("--include-forks", action="store_true", help="Include forked repositories.")
    ap.add_argument("--prefix", default="", help="Optional prefix for Codeberg repo names.")
    ap.add_argument("--dry-run", action="store_true", help="Do not create/push, only print actions.")
    ap.add_argument("--temp-root", default="./_mirror_tmp", help="Temp directory root for mirror clones.")
    ap.add_argument("--keep-temp", action="store_true", help="Keep temp clones for debugging.")
    args = ap.parse_args()

    if not args.github_pat or not args.codeberg_token:
        err("Provide --github-pat and --codeberg-token, or set GITHUB_PAT and CODEBERG_TOKEN.")
        sys.exit(2)

    info("Authenticating to Codeberg...")
    cb_user = codeberg_get_user(args.codeberg_token)
    cb_login = cb_user.get("login")
    if not cb_login:
        raise RuntimeError(f"Could not determine Codeberg username from /user response: {cb_user}")
    ok(f"Codeberg user: {cb_login}")

    info("Listing GitHub repositories (read-only)...")
    repos = github_list_repos(args.github_pat, include_orgs=args.include_orgs, include_forks=args.include_forks)
    ok(f"Found {len(repos)} repos to process.")

    os.makedirs(args.temp_root, exist_ok=True)

    askpass_dir = os.path.join(args.temp_root, "_askpass")
    askpass_path = make_askpass_script(askpass_dir, username=cb_login, password=args.codeberg_token)
    env = git_env_for_askpass(askpass_path)

    for idx, r in enumerate(repos, start=1):
        gh_full = r.get("full_name", "<unknown>")
        gh_name = r.get("name", "repo")
        gh_private = bool(r.get("private"))
        gh_desc = r.get("description") or ""
        gh_clone = r.get("clone_url")
        default_branch = r.get("default_branch") or "main"

        cb_repo_name = f"{args.prefix}{gh_name}"
        cb_repo_url = f"https://codeberg.org/{cb_login}/{cb_repo_name}.git"

        print()
        header = f"[{idx}/{len(repos)}] {gh_full}  ->  codeberg.org/{cb_login}/{cb_repo_name}  (private={gh_private})"
        print(color(header, C.BOLD) if ANSI else header)

        if args.dry_run:
            warn("DRY RUN: would ensure Codeberg repo exists and force-mirror branches/tags.")
            continue

        if not codeberg_repo_exists(args.codeberg_token, cb_login, cb_repo_name):
            info("Creating repo on Codeberg...")
            codeberg_create_repo(
                args.codeberg_token,
                name=cb_repo_name,
                private=gh_private,
                description=gh_desc,
                default_branch=default_branch,
            )
            ok("Repo created.")
        else:
            ok("Repo already exists on Codeberg.")

        tmp_path = os.path.join(args.temp_root, f"{cb_repo_name}.git")

        try:
            info("Force-mirroring branches/tags (GitHub read-only; Codeberg write)...")
            git_force_mirror_push(gh_clone, cb_repo_url, tmp_path, env=env)
            ok("Mirror completed.")
        finally:
            if not args.keep_temp:
                try:
                    rmtree_with_retries(tmp_path)
                except Exception as e:
                    warn(f"Could not fully delete temp dir '{tmp_path}'. Remove it later. Details: {e}")

        time.sleep(0.2)

    ok("All done.")
    print(color("Safety: GitHub was only read from; no deletes/writes were performed on GitHub.", C.DIM) if ANSI else
          "Safety: GitHub was only read from; no deletes/writes were performed on GitHub.")


if __name__ == "__main__":
    main()
