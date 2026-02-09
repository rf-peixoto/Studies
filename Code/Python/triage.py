#!/usr/bin/env python3
"""
Submit all files in a folder to tria.ge (Recorded Future Sandbox / Triage Cloud API).

Docs: POST /samples, multipart/form-data with `file` and optional `_json`.

python triage.py phishing_pot/email/ --api-key "PASTE_YOUR_TRIAGE_API_KEY_HERE" --recursive --network internet --timeout 300 --user-tag type:eml --user-tag artifact:email  --user-tag source:phishing_pot  --user-tag intent:phishing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import requests


def iter_files(root: Path, recursive: bool) -> Iterable[Path]:
    if recursive:
        for p in root.rglob("*"):
            if p.is_file():
                yield p
    else:
        for p in root.iterdir():
            if p.is_file():
                yield p


def build_json_payload(args: argparse.Namespace, filename: str) -> Optional[str]:
    payload: Dict[str, object] = {}

    # Force kind to "file" for file submissions.
    payload["kind"] = "file"  # "kind" is a supported parameter. :contentReference[oaicite:1]{index=1}

    # Optional: override displayed filename (target).
    if args.target_mode == "basename":
        payload["target"] = filename
    elif args.target_mode == "relative":
        # Use relative path string (may contain slashes)
        payload["target"] = args._relative_target

    # Optional: interactive mode.
    if args.interactive:
        payload["interactive"] = True  # interactive supported. :contentReference[oaicite:2]{index=2}

    # Optional: defaults.* for automatic analysis parameters.
    defaults: Dict[str, object] = {}
    if args.timeout is not None:
        defaults["timeout"] = int(args.timeout)  # max 3600 per docs. :contentReference[oaicite:3]{index=3}
    if args.network is not None:
        defaults["network"] = args.network  # internet|drop|tor per docs. :contentReference[oaicite:4]{index=4}
    if defaults:
        payload["defaults"] = defaults

    # Optional: user tags (limited total size in docs).
    if args.user_tag:
        payload["user_tags"] = args.user_tag  # user_tags supported. :contentReference[oaicite:5]{index=5}

    # If nothing beyond kind, we still can send it; `_json` is acceptable either way.
    return json.dumps(payload, separators=(",", ":"))


def submit_file(
    session: requests.Session,
    api_base: str,
    api_key: str,
    file_path: Path,
    json_payload: Optional[str],
    password: Optional[str],
    dry_run: bool,
    max_retries: int,
) -> Tuple[bool, str]:
    url = api_base.rstrip("/") + "/samples"  # POST /samples :contentReference[oaicite:6]{index=6}

    if dry_run:
        return True, f"DRY_RUN would submit: {file_path}"

    files = {
        "file": (file_path.name, file_path.open("rb")),
    }

    data: Dict[str, str] = {}
    if json_payload:
        data["_json"] = json_payload  # `_json` form field for JSON parameters. :contentReference[oaicite:7]{index=7}
    if password:
        data["password"] = password  # password supported for archives. :contentReference[oaicite:8]{index=8}

    headers = {
        "Authorization": f"Bearer {api_key}",  # Bearer token shown in examples. :contentReference[oaicite:9]{index=9}
    }

    try:
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = session.post(url, headers=headers, data=data, files=files, timeout=120)
            except requests.RequestException as e:
                if attempt <= max_retries:
                    backoff = min(2 ** (attempt - 1), 30)
                    time.sleep(backoff)
                    continue
                return False, f"{file_path} -> request error: {e!r}"

            # Retry on 429/5xx with backoff
            if resp.status_code in (429, 500, 502, 503, 504) and attempt <= max_retries:
                backoff = min(2 ** (attempt - 1), 30)
                time.sleep(backoff)
                continue

            if not (200 <= resp.status_code < 300):
                body = resp.text.strip()
                body = body[:2000] + ("..." if len(body) > 2000 else "")
                return False, f"{file_path} -> HTTP {resp.status_code}: {body}"

            # Expected response includes "id" and other fields in examples.
            try:
                j = resp.json()
            except ValueError:
                return False, f"{file_path} -> success HTTP {resp.status_code} but non-JSON response: {resp.text[:500]!r}"

            sample_id = j.get("id", "")
            status = j.get("status", "")
            kind = j.get("kind", "")
            return True, f"{file_path} -> id={sample_id} status={status} kind={kind}"

    finally:
        try:
            files["file"][1].close()
        except Exception:
            pass


def main() -> int:
    p = argparse.ArgumentParser(
        description="Submit all files in a folder to tria.ge (Triage Cloud API).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("folder", help="Folder containing files to submit.")
    p.add_argument("--api-key", default=os.getenv("TRIAGE_API_KEY"), help="API key (or set TRIAGE_API_KEY env var).")
    p.add_argument(
        "--api-base",
        default=os.getenv("TRIAGE_API_BASE", "https://tria.ge/api/v0"),
        help="API base URL (e.g., https://tria.ge/api/v0, or private cloud base).",
    )
    p.add_argument("--recursive", action="store_true", help="Recurse into subfolders.")
    p.add_argument("--timeout", type=int, default=None, help="defaults.timeout for behavioral analysis (seconds).")
    p.add_argument(
        "--network",
        choices=["internet", "drop", "tor"],
        default=None,
        help='defaults.network ("internet", "drop", or "tor").',
    )
    p.add_argument("--interactive", action="store_true", help="Set interactive=true (requires manual profile selection).")
    p.add_argument("--password", default=None, help="Password for encrypted archives (zip/rar/etc).")
    p.add_argument(
        "--user-tag",
        action="append",
        default=[],
        help="Add a user tag; repeatable (e.g., --user-tag source:case123).",
    )
    p.add_argument(
        "--target-mode",
        choices=["none", "basename", "relative"],
        default="basename",
        help="How to set `target`: none, basename, or relative path.",
    )
    p.add_argument("--output-jsonl", default="triage_submissions.jsonl", help="Write results to a JSONL file.")
    p.add_argument("--dry-run", action="store_true", help="Do not submit; just show what would be done.")
    p.add_argument("--max-retries", type=int, default=5, help="Retries for 429/5xx or transient errors.")

    args = p.parse_args()

    if not args.api_key:
        print("Error: missing API key. Provide --api-key or set TRIAGE_API_KEY.", file=sys.stderr)
        return 2

    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"Error: folder does not exist or is not a directory: {folder}", file=sys.stderr)
        return 2

    files = list(iter_files(folder, args.recursive))
    if not files:
        print(f"No files found in: {folder}", file=sys.stderr)
        return 0

    session = requests.Session()
    out_path = Path(args.output_jsonl).expanduser().resolve()

    ok_count = 0
    fail_count = 0

    with out_path.open("a", encoding="utf-8") as outf:
        for fp in files:
            if args.target_mode == "relative":
                rel = fp.relative_to(folder).as_posix()
                args._relative_target = rel
            else:
                args._relative_target = fp.name

            json_payload = None
            if args.target_mode != "none" or args.timeout is not None or args.network is not None or args.interactive or args.user_tag:
                json_payload = build_json_payload(args, fp.name)

            success, msg = submit_file(
                session=session,
                api_base=args.api_base,
                api_key=args.api_key,
                file_path=fp,
                json_payload=json_payload,
                password=args.password,
                dry_run=args.dry_run,
                max_retries=args.max_retries,
            )

            record = {
                "ts": time.time(),
                "success": success,
                "file": str(fp),
                "message": msg,
            }
            outf.write(json.dumps(record) + "\n")
            outf.flush()

            print(msg)
            if success:
                ok_count += 1
            else:
                fail_count += 1

    print(f"\nDone. Success={ok_count} Fail={fail_count} Log={out_path}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
