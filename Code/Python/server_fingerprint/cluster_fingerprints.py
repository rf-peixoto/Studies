#!/usr/bin/env python3
"""
cluster_fingerprints.py — group hosts from infra_fingerprint.py output.

Reads the JSONL produced by infra_fingerprint.py and links hosts that share
fingerprints, so overlapping actor infrastructure falls out into clusters.

Two views:
  1. Exact-match index — for each strong signal (JARM, JA4S, cert SPKI, favicon,
     header-order, structural hash, cert issuer), list which hosts share a value.
  2. Fuzzy body clustering — union-find over hosts whose body SimHashes are within
     a Hamming-distance threshold (near-identical templated pages).

Usage:
    python3 cluster_fingerprints.py out.jsonl
    python3 cluster_fingerprints.py out.jsonl --simhash-threshold 6
"""
import argparse
import json
import sys
from collections import defaultdict

STRONG_SIGNALS = [
    ("jarm", lambda r: r.get("jarm")),
    ("ja4s", lambda r: (r.get("cluster_key") or {}).get("ja4s")),
    ("cert_spki_sha256", lambda r: (r.get("cluster_key") or {}).get("cert_spki_sha256")),
    ("cert_issuer_hash", lambda r: (r.get("cluster_key") or {}).get("cert_issuer_hash")),
    ("favicon_mmh3", lambda r: (r.get("cluster_key") or {}).get("favicon_mmh3")),
    ("header_order_hash", lambda r: (r.get("cluster_key") or {}).get("header_order_hash")),
    ("structural_hash", lambda r: (r.get("cluster_key") or {}).get("structural_hash")),
    ("server", lambda r: (r.get("cluster_key") or {}).get("server")),
]


def label(rec):
    return rec.get("target") or rec.get("host") or "?"


def hamming_hex(a, b):
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except Exception:
        return 64


class UnionFind:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="JSONL from infra_fingerprint.py")
    ap.add_argument("--simhash-threshold", type=int, default=6,
                    help="Max Hamming distance to link two body SimHashes")
    args = ap.parse_args()

    recs = []
    with open(args.input) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    recs.append(json.loads(ln))
                except Exception:
                    pass
    if not recs:
        sys.exit("no records parsed")

    print(f"Loaded {len(recs)} host record(s)\n")

    # 1) Exact shared-signal index
    print("=" * 70)
    print("SHARED SIGNALS (value -> hosts that share it)")
    print("=" * 70)
    for name, getter in STRONG_SIGNALS:
        index = defaultdict(list)
        for r in recs:
            v = getter(r)
            if v not in (None, "", "000000000000"):
                index[str(v)].append(label(r))
        shared = {v: hosts for v, hosts in index.items() if len(hosts) > 1}
        if shared:
            print(f"\n[{name}]")
            for v, hosts in sorted(shared.items(), key=lambda kv: -len(kv[1])):
                print(f"  {v}")
                for h in hosts:
                    print(f"      - {h}")

    # 2) Fuzzy body clustering via SimHash
    print("\n" + "=" * 70)
    print(f"FUZZY BODY CLUSTERS (SimHash Hamming <= {args.simhash_threshold})")
    print("=" * 70)
    uf = UnionFind()
    sims = [(label(r), ((r.get("cluster_key") or {}).get("body_simhash")))
            for r in recs]
    sims = [(h, s) for h, s in sims if s and s != "0" * 16]
    for h, _ in sims:
        uf.find(h)
    for i in range(len(sims)):
        for j in range(i + 1, len(sims)):
            if hamming_hex(sims[i][1], sims[j][1]) <= args.simhash_threshold:
                uf.union(sims[i][0], sims[j][0])
    clusters = defaultdict(list)
    for h, _ in sims:
        clusters[uf.find(h)].append(h)
    multi = [c for c in clusters.values() if len(c) > 1]
    if multi:
        for n, c in enumerate(multi, 1):
            print(f"\n  Cluster {n}: {len(c)} hosts")
            for h in sorted(c):
                print(f"      - {h}")
    else:
        print("\n  (no near-duplicate bodies found)")

    print()


if __name__ == "__main__":
    main()
