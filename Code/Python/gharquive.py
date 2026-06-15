#!/usr/bin/env python3
import argparse
import gzip
import json
import os
import shutil
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


GHARCHIVE_URL = "https://data.gharchive.org/{date}-{hour}.json.gz"
GITHUB_ZIP_URL = "https://github.com/{repo}/archive/refs/heads/{branch}.zip"


def download(url, dest, token=None, timeout=90):
    headers = {"User-Agent": "gharchive-repo-downloader/1.0"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return False, f"HTTP {response.status}"

            dest.parent.mkdir(parents=True, exist_ok=True)

            with open(dest, "wb") as f:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

        return True, "ok"

    except Exception as e:
        return False, str(e)


def parse_repos_from_gharchive(gz_path):
    repos = set()

    with gzip.open(gz_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            repo = event.get("repo", {})
            name = repo.get("name")

            if name and "/" in name:
                repos.add(name.strip())

    return repos


def safe_repo_name(repo):
    return repo.replace("/", "__")


def parse_hours(value):
    if "-" in value:
        start, end = map(int, value.split("-", 1))
        return range(start, end + 1)

    return [int(value)]


def extract_zip(zip_path, extract_to):
    temp_dir = extract_to.with_suffix(".tmp")

    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(temp_dir)

        extracted_items = list(temp_dir.iterdir())

        if len(extracted_items) == 1 and extracted_items[0].is_dir():
            inner_root = extracted_items[0]

            extract_to.mkdir(parents=True, exist_ok=True)

            for item in inner_root.iterdir():
                target = extract_to / item.name
                shutil.move(str(item), str(target))

            shutil.rmtree(temp_dir)
        else:
            if extract_to.exists():
                shutil.rmtree(extract_to)

            shutil.move(str(temp_dir), str(extract_to))

        return True, "ok"

    except Exception as e:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

        return False, str(e)


def append_line(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Download today's GHArchive files, extract GitHub repositories, download each repository ZIP, and unzip it."
    )

    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="UTC date to download. Format: YYYY-MM-DD. Default: today UTC."
    )

    parser.add_argument(
        "--hours",
        default="0-23",
        help="Hours to fetch. Examples: 15, 10-18, 0-23. Default: 0-23."
    )

    parser.add_argument(
        "--out",
        default="gharchive_downloads",
        help="Output directory. Default: gharchive_downloads."
    )

    parser.add_argument(
        "--branch",
        default="master",
        help="Primary branch to download. Default: master."
    )

    parser.add_argument(
        "--fallback-branch",
        default="main",
        help="Fallback branch if primary branch fails. Default: main."
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between repository downloads. Default: 1 second."
    )

    parser.add_argument(
        "--max-repos",
        type=int,
        default=0,
        help="Maximum repositories to download. 0 means unlimited."
    )

    parser.add_argument(
        "--keep-zip",
        action="store_true",
        help="Keep ZIP files after successful extraction."
    )

    parser.add_argument(
        "--token",
        default=os.getenv("GITHUB_TOKEN"),
        help="Optional GitHub token. Defaults to GITHUB_TOKEN environment variable."
    )

    args = parser.parse_args()

    out = Path(args.out)
    raw_dir = out / "raw"
    zip_dir = out / "zips"
    repo_dir = out / "repos"

    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_dir.mkdir(parents=True, exist_ok=True)
    repo_dir.mkdir(parents=True, exist_ok=True)

    failed_path = out / "failed.txt"
    repo_list_path = out / f"repos-{args.date}.txt"

    all_repos = set()
    hours = parse_hours(args.hours)

    print(f"[+] Date: {args.date}")
    print("[+] Downloading GHArchive files...")

    for hour in hours:
        url = GHARCHIVE_URL.format(date=args.date, hour=hour)
        gz_path = raw_dir / f"{args.date}-{hour}.json.gz"

        print(f"    -> {url}")

        ok, msg = download(url, gz_path)

        if not ok:
            print(f"       [!] skipped: {msg}")
            append_line(failed_path, f"GHARCHIVE {url} :: {msg}")
            continue

        repos = parse_repos_from_gharchive(gz_path)
        all_repos.update(repos)

        print(f"       [+] found: {len(repos)} repos")
        print(f"       [+] total unique: {len(all_repos)}")

    repos = sorted(all_repos)

    if args.max_repos > 0:
        repos = repos[:args.max_repos]

    repo_list_path.write_text("\n".join(repos) + "\n", encoding="utf-8")

    print(f"[+] Unique repositories: {len(repos)}")
    print(f"[+] Repository list saved to: {repo_list_path}")
    print("[+] Downloading and extracting repositories...")

    for index, repo in enumerate(repos, 1):
        safe_name = safe_repo_name(repo)

        zip_path = zip_dir / f"{safe_name}.zip"
        extract_path = repo_dir / safe_name

        if extract_path.exists() and any(extract_path.iterdir()):
            print(f"[{index}/{len(repos)}] already extracted: {repo}")
            continue

        print(f"[{index}/{len(repos)}] {repo}")

        url = GITHUB_ZIP_URL.format(repo=repo, branch=args.branch)

        ok, msg = download(
            url=url,
            dest=zip_path,
            token=args.token
        )

        used_branch = args.branch

        if not ok and args.fallback_branch:
            print(f"    [!] failed on {args.branch}: {msg}")
            print(f"    [*] trying fallback branch: {args.fallback_branch}")

            url = GITHUB_ZIP_URL.format(repo=repo, branch=args.fallback_branch)

            ok, msg = download(
                url=url,
                dest=zip_path,
                token=args.token
            )

            used_branch = args.fallback_branch

        if not ok:
            print(f"    [!] download failed: {msg}")
            append_line(failed_path, f"{repo} :: download failed :: {msg}")

            if zip_path.exists():
                zip_path.unlink(missing_ok=True)

            time.sleep(args.delay)
            continue

        ok, msg = extract_zip(zip_path, extract_path)

        if not ok:
            print(f"    [!] extraction failed: {msg}")
            append_line(failed_path, f"{repo} :: extraction failed :: {msg}")
            time.sleep(args.delay)
            continue

        print(f"    [+] extracted: {extract_path}")
        print(f"    [+] branch: {used_branch}")

        if not args.keep_zip:
            zip_path.unlink(missing_ok=True)

        time.sleep(args.delay)

    print("[+] Done.")


if __name__ == "__main__":
    main()
