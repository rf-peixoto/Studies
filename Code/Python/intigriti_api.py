#!/usr/bin/env python3
"""
Minimal Intigriti Researcher API CLI (Programs-focused) with colored terminal UX.

- Auth: Authorization: Bearer <PAT>  (per Researcher API swagger securitySchemes) :contentReference[oaicite:1]{index=1}
- Programs list: GET /v1/programs with filters statusId, typeId, following, limit, offset :contentReference[oaicite:2]{index=2}
- Program detail: GET /v1/programs/{programId} includes domains (versioned) with tier per domain :contentReference[oaicite:3]{index=3}

Notes:
- "Payment tiers" are represented here as:
  (1) program-level min/max bounty in the overview, and
  (2) per-domain tier distribution from program detail.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()


# -----------------------------
# API client
# -----------------------------
@dataclass
class ApiConfig:
    base_url: str
    token: str
    timeout: int = 30
    max_retries: int = 4
    backoff_base: float = 0.8  # seconds


class IntigritiClient:
    def __init__(self, cfg: ApiConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {cfg.token}",
                "Accept": "application/json",
                "User-Agent": "intigriti-cli/1.0",
            }
        )

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self.cfg.base_url.rstrip("/") + path
        last_err: Optional[Exception] = None

        for attempt in range(0, self.cfg.max_retries + 1):
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=self.cfg.timeout,
                )

                # Friendly error surface
                if resp.status_code in (401, 403, 409, 500, 503, 400):
                    self._raise_api_error(resp)

                resp.raise_for_status()
                if resp.content:
                    return resp.json()
                return None

            except requests.RequestException as e:
                last_err = e
                # Retry only on transient-ish failures
                if attempt >= self.cfg.max_retries:
                    break
                sleep_s = self.cfg.backoff_base * (2 ** attempt)
                time.sleep(sleep_s)

        raise SystemExit(f"[!] Network/API failure after retries: {last_err}")

    @staticmethod
    def _raise_api_error(resp: requests.Response) -> None:
        status = resp.status_code
        try:
            body = resp.json()
        except Exception:
            body = resp.text.strip()

        # Rate limiting: docs mention 403 on exceeded limits; surface explicitly
        if status == 403:
            raise SystemExit(
                f"[!] 403 Forbidden. This can mean rate limiting or insufficient access/permissions.\n"
                f"    Response: {body}"
            )
        if status == 401:
            raise SystemExit(f"[!] 401 Unauthorized (token invalid/expired?). Response: {body}")
        if status == 400:
            raise SystemExit(f"[!] 400 Bad Request. Response: {body}")
        if status == 409:
            raise SystemExit(f"[!] 409 Conflict. Response: {body}")
        if status == 500:
            raise SystemExit(f"[!] 500 Internal Server Error. Response: {body}")
        if status == 503:
            raise SystemExit(f"[!] 503 Service Unavailable. Response: {body}")

        raise SystemExit(f"[!] HTTP {status}. Response: {body}")

    # ---- Programs ----
    def list_programs(
        self,
        status_id: Optional[int] = None,
        type_id: Optional[int] = None,
        following: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status_id is not None:
            params["statusId"] = status_id
        if type_id is not None:
            params["typeId"] = type_id
        if following is not None:
            params["following"] = following
        return self._request("GET", "/v1/programs", params=params)

    def get_program_detail(self, program_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v1/programs/{program_id}")

    def get_program_domains_version(self, program_id: str, version_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v1/programs/{program_id}/domains/{version_id}")

    def get_program_roe_version(self, program_id: str, version_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v1/programs/{program_id}/rules-of-engagements/{version_id}")


# -----------------------------
# Formatting helpers
# -----------------------------
def money_str(m: Optional[Dict[str, Any]]) -> str:
    if not m:
        return "—"
    val = m.get("value", None)
    cur = m.get("currency", "")
    if val is None:
        return "—"
    # Avoid locale complexity; keep compact
    return f"{cur} {val:g}"


def enum_str(e: Optional[Dict[str, Any]]) -> str:
    if not e:
        return "—"
    v = e.get("value")
    i = e.get("id")
    if v is None and i is None:
        return "—"
    if v is None:
        return str(i)
    if i is None:
        return str(v)
    return f"{v} ({i})"


def color_for_bounty(max_bounty_value: Optional[Union[int, float]]) -> str:
    """
    Minimal, intuitive coloring:
      - unknown: dim
      - low: red-ish
      - mid: yellow-ish
      - high: green-ish
    Thresholds are heuristic and can be adjusted.
    """
    if max_bounty_value is None:
        return "grey50"
    try:
        v = float(max_bounty_value)
    except Exception:
        return "grey50"
    if v < 200:
        return "red"
    if v < 1000:
        return "yellow"
    return "green"


def tier_color(tier_name: str) -> str:
    n = (tier_name or "").lower()
    # Keep neutral but informative
    if "tier 1" in n or n.endswith("1"):
        return "green"
    if "tier 2" in n or n.endswith("2"):
        return "yellow"
    if "tier 3" in n or n.endswith("3"):
        return "orange3"
    if "tier 4" in n or n.endswith("4"):
        return "red"
    if "tier 5" in n or n.endswith("5"):
        return "magenta"
    return "cyan"


# -----------------------------
# CLI actions
# -----------------------------
def cmd_programs_list(args: argparse.Namespace, client: IntigritiClient) -> None:
    data = client.list_programs(
        status_id=args.status,
        type_id=args.type,
        following=args.following,
        limit=args.limit,
        offset=args.offset,
    )
    max_count = data.get("maxCount", 0)
    records: List[Dict[str, Any]] = data.get("records", []) or []

    # Optional client-side search
    if args.search:
        q = args.search.lower().strip()
        records = [
            r for r in records
            if (r.get("name", "") or "").lower().find(q) >= 0
            or (r.get("handle", "") or "").lower().find(q) >= 0
        ]

    header = Text("Intigriti Programs", style="bold")
    subtitle = f"Showing {len(records)} / {max_count} (limit={args.limit}, offset={args.offset})"
    console.print(Panel.fit(Text(subtitle, style="grey70"), title=header, border_style="grey37"))

    t = Table(box=box.SIMPLE_HEAVY, show_lines=False, header_style="bold")
    t.add_column("Handle", style="bold", overflow="fold")
    t.add_column("Name", overflow="fold")
    t.add_column("Min→Max", justify="right")
    t.add_column("Status", style="grey70")
    t.add_column("Type", style="grey70")
    t.add_column("Conf.", style="grey70")
    t.add_column("Follow", justify="center")
    t.add_column("Id", style="grey50", overflow="fold")

    for r in records:
        min_b = r.get("minBounty")
        max_b = r.get("maxBounty")
        max_val = (max_b or {}).get("value") if isinstance(max_b, dict) else None
        bounty_style = color_for_bounty(max_val)

        bounty = Text(f"{money_str(min_b)} → {money_str(max_b)}", style=bounty_style)

        t.add_row(
            r.get("handle", "—"),
            r.get("name", "—"),
            bounty,
            enum_str(r.get("status")),
            enum_str(r.get("type")),
            enum_str(r.get("confidentialityLevel")),
            "✓" if r.get("following") else "",
            r.get("id", "—"),
        )

    console.print(t)

    console.print(
        Text(
            "\nTip: use `programs show <handle|id>` to display domain tiers and current scope summary.",
            style="grey62",
        )
    )


def _resolve_program_id_from_handle(handle_or_id: str, client: IntigritiClient) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    The detail endpoint requires a GUID programId.
    This resolves handle -> id by paging through list results (within reasonable bounds).
    """
    candidate = handle_or_id.strip()
    # If it looks like a GUID, use directly
    if len(candidate) >= 32 and "-" in candidate:
        return candidate, None

    # Try to find by scanning a few pages (minimal but practical).
    # If you have >500 programs, widen pages as needed.
    limit = 500
    offset = 0
    for _ in range(0, 5):  # up to ~2500 records
        data = client.list_programs(limit=limit, offset=offset)
        records = data.get("records", []) or []
        for r in records:
            if (r.get("handle") or "").lower() == candidate.lower():
                return r.get("id"), r
        if len(records) < limit:
            break
        offset += limit

    raise SystemExit(f"[!] Could not resolve handle '{candidate}' to a program id (GUID).")


def cmd_programs_show(args: argparse.Namespace, client: IntigritiClient) -> None:
    program_id, overview = _resolve_program_id_from_handle(args.program, client)
    detail = client.get_program_detail(program_id)

    # Basic program header
    name = detail.get("name", "—")
    handle = detail.get("handle", "—")
    status = enum_str(detail.get("status"))
    ptype = enum_str(detail.get("type"))
    conf = enum_str(detail.get("confidentialityLevel"))
    following = "yes" if detail.get("following") else "no"
    industry = detail.get("industry") or "—"
    weblink = (detail.get("webLinks") or {}).get("detail") or "—"

    header = Text(f"{name}", style="bold")
    meta = Text()
    meta.append(f"Handle: {handle}\n", style="grey70")
    meta.append(f"Status: {status} | Type: {ptype} | Confidentiality: {conf} | Following: {following}\n", style="grey70")
    meta.append(f"Industry: {industry}\n", style="grey70")
    meta.append(f"Web: {weblink}\n", style="grey62")

    console.print(Panel(meta, title=header, border_style="grey37"))

    # Domains (tier distribution)
    domains_version = detail.get("domains") or {}
    domains_vid = domains_version.get("id")
    domains = domains_version.get("content") or []

    # If domains content is null/empty, still show version id + note
    console.print(Text(f"Domains versionId: {domains_vid or '—'}", style="grey62"))

    tier_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    for d in domains:
        tier = enum_str(d.get("tier"))
        dtype = enum_str(d.get("type"))
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        type_counts[dtype] = type_counts.get(dtype, 0) + 1

    # Table: tier summary
    tier_table = Table(title="Scope tiers (by domain asset tier)", box=box.SIMPLE_HEAVY, header_style="bold")
    tier_table.add_column("Tier", overflow="fold")
    tier_table.add_column("Count", justify="right")

    if tier_counts:
        for tier, cnt in sorted(tier_counts.items(), key=lambda x: x[0]):
            tier_table.add_row(Text(tier, style=tier_color(tier)), str(cnt))
    else:
        tier_table.add_row(Text("—", style="grey50"), "0")

    # Table: domain types
    type_table = Table(title="Domain types (count)", box=box.SIMPLE_HEAVY, header_style="bold")
    type_table.add_column("Type", overflow="fold")
    type_table.add_column("Count", justify="right")
    if type_counts:
        for dtype, cnt in sorted(type_counts.items(), key=lambda x: x[0]):
            type_table.add_row(dtype, str(cnt))
    else:
        type_table.add_row(Text("—", style="grey50"), "0")

    console.print(tier_table)
    console.print(type_table)

    # Optional: show a compact list of domains (limited)
    if args.show_domains:
        domains_table = Table(
            title=f"Domains (showing up to {args.show_domains})",
            box=box.SIMPLE_HEAVY,
            header_style="bold",
        )
        domains_table.add_column("Endpoint", overflow="fold")
        domains_table.add_column("Tier", overflow="fold")
        domains_table.add_column("Type", overflow="fold")
        domains_table.add_column("Description", overflow="fold")

        for d in domains[: args.show_domains]:
            tier = enum_str(d.get("tier"))
            domains_table.add_row(
                d.get("endpoint", "—"),
                Text(tier, style=tier_color(tier)),
                enum_str(d.get("type")),
                (d.get("description") or "—"),
            )
        console.print(domains_table)

    # Program-level bounty view (min/max) is only available on overview records
    # If we resolved by handle we may have overview already; if not, fetch a single page and match.
    if overview is None:
        # Try to find it quickly for min/max bounty display
        try:
            _, overview = _resolve_program_id_from_handle(handle, client)
        except Exception:
            overview = None

    if overview:
        min_b = overview.get("minBounty")
        max_b = overview.get("maxBounty")
        max_val = (max_b or {}).get("value") if isinstance(max_b, dict) else None
        style = color_for_bounty(max_val)
        console.print(
            Panel.fit(
                Text(f"{money_str(min_b)} → {money_str(max_b)}", style=style),
                title=Text("Program payment range (min→max)", style="bold"),
                border_style=style,
            )
        )


# -----------------------------
# Argument parsing
# -----------------------------
def parse_bool(s: str) -> bool:
    v = s.strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError("Expected a boolean: true/false")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Minimal Intigriti Researcher API CLI (programs).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--base-url", default="https://api.intigriti.com/external/researcher", help="API base URL")
    p.add_argument(
        "--token",
        default=os.getenv("INTIGRITI_PAT", ""),
        help="Personal Access Token (or set INTIGRITI_PAT env var)",
    )
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout (seconds)")

    sub = p.add_subparsers(dest="cmd", required=True)

    # programs
    programs = sub.add_parser("programs", help="Browse programs")
    psub = programs.add_subparsers(dest="programs_cmd", required=True)

    plist = psub.add_parser("list", help="List programs you have access to")
    plist.add_argument("--status", type=int, default=None, help="statusId filter (e.g., 3=open)")
    plist.add_argument("--type", type=int, default=None, help="typeId filter (e.g., 1=bug bounty)")
    plist.add_argument("--following", type=parse_bool, default=None, help="following filter (true/false)")
    plist.add_argument("--limit", type=int, default=50, help="limit (max 500)")
    plist.add_argument("--offset", type=int, default=0, help="offset for pagination")
    plist.add_argument("--search", default=None, help="client-side search over name/handle (substring)")

    pshow = psub.add_parser("show", help="Show program details (tier distribution, scope summary)")
    pshow.add_argument("program", help="program handle or programId (GUID)")
    pshow.add_argument("--show-domains", type=int, default=0, help="also list up to N domain entries")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("[!] Missing token. Provide --token or set INTIGRITI_PAT.")

    cfg = ApiConfig(base_url=args.base_url, token=args.token, timeout=args.timeout)
    client = IntigritiClient(cfg)

    if args.cmd == "programs":
        if args.programs_cmd == "list":
            if args.limit > 500:
                raise SystemExit("[!] limit cannot exceed 500.")
            cmd_programs_list(args, client)
            return
        if args.programs_cmd == "show":
            cmd_programs_show(args, client)
            return

    raise SystemExit("[!] Unknown command")


if __name__ == "__main__":
    main()
