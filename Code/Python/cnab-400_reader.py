#!/usr/bin/env python3
"""
parse_sicredi_cnab400.py – Parse a Sicredi CNAB‑400 “retorno de cobrança” file.

Usage examples
--------------
    python parse_sicredi_cnab400.py 76214414.CRT
    python parse_sicredi_cnab400.py anyname.txt --csv boletos_2025‑08‑06.csv

Features
--------
* Accepts any file extension.
* Verifies that the file header matches a Sicredi CNAB‑400 return.
* Prints a concise human‑readable summary:
    – record count, occurrence breakdown, total amount credited, date span.
* Shows the first 10 detail lines in tabular form.
* Optionally exports the full table to CSV via --csv.
"""

from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sys

try:
    import pandas as pd
except ImportError:
    sys.exit("ERROR: pandas is required – install it with `pip install pandas`")

# ---------- fixed slices (0‑based Python indexing, end exclusive) ----------
SLICE = {
    "record_type" : slice(0, 1),
    "nosso_numero": slice(47, 62),   # positions 48‑62 in the CNAB spec
    "occurrence"  : slice(108, 110),
    "date_occ"    : slice(110, 116), # DDMMYY
    "amount_paid" : slice(253, 266), # numeric, 2 implied decimals
}

# Occurrence codes that represent a paid boleto
PAID_CODES = {"06", "15", "17", "40"}

# Friendly English labels for common occurrences
OCC_LABEL = {
    "06": "Paid",
    "15": "Paid – registry office",
    "17": "Paid after write‑off",
    "02": "Entry confirmed",
    "03": "Entry rejected",
    "14": "Due date changed",
}

# ---------------------------------------------------------------------------

def parse_decimal(raw: str) -> Decimal:
    """Convert the raw 13‑digit numeric field (two implied decimals) to Decimal."""
    raw = raw.strip() or "0"
    return Decimal(raw) / 100

def parse_date(raw: str):
    """Return a date object from DDMMYY or None if the field is blank."""
    raw = raw.strip()
    return datetime.strptime(raw, "%d%m%y").date() if len(raw) == 6 else None

def parse_detail(line: str) -> dict:
    """Extract the fields we care about from a detail (type 1) record."""
    return {
        "nosso_numero": line[SLICE["nosso_numero"]].strip(),
        "occurrence"  : line[SLICE["occurrence"]].strip(),
        "date"        : parse_date(line[SLICE["date_occ"]]),
        "amount_paid" : parse_decimal(line[SLICE["amount_paid"]]),
    }

def sanity_check_header(line: str):
    """Abort if the header does not look like a Sicredi return file."""
    if not line.startswith("02RETORNO"):
        sys.exit("ERROR: File does not look like a Sicredi CNAB‑400 return (header mismatch).")

def build_df(path: Path) -> pd.DataFrame:
    """Read the file and build a DataFrame with detail records only."""
    records = []
    with path.open("r", encoding="latin1") as fh:
        first_line = fh.readline()
        sanity_check_header(first_line)

        for line in fh:
            if line[SLICE["record_type"]] == "1":      # detail record
                records.append(parse_detail(line))

    if not records:
        sys.exit("ERROR: No detail (type 1) records found – is the file complete?")

    return pd.DataFrame.from_records(records)

def print_summary(df: pd.DataFrame):
    """Output an easy‑to‑read summary of the parsed DataFrame."""
    total_records = len(df)
    occ_counts    = Counter(df["occurrence"])
    total_paid    = df.loc[df["occurrence"].isin(PAID_CODES), "amount_paid"].sum()
    date_series   = df["date"].dropna()

    date_span = "n/a"
    if not date_series.empty:
        date_span = f"{date_series.min()}  →  {date_series.max()}"

    print("\nSUMMARY")
    print("-------")
    print(f"Detail records        : {total_records}")
    print(f"Date span             : {date_span}")

    print("\nOccurrences:")
    for code, qty in sorted(occ_counts.items()):
        label = OCC_LABEL.get(code, "Other")
        print(f"  {code} – {label:<27}: {qty}")

    print(f"\nTotal amount credited : R$ {total_paid:,.2f}")

def main():
    parser = argparse.ArgumentParser(
        description="Parse Sicredi CNAB‑400 return files (.CRT, any extension).")
    parser.add_argument("file", help="Path to the return file")
    parser.add_argument("--csv", metavar="DEST",
                        help="Save the full parsed table to CSV at DEST")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        sys.exit(f"ERROR: File not found – {path}")

    df = build_df(path)
    print_summary(df)

    print("\nFirst 10 records:")
    print(df.head(10).to_string(index=False))

    if args.csv:
        df.to_csv(args.csv, index=False, encoding="utf‑8")
        print(f"\nCSV saved to {args.csv}")

if __name__ == "__main__":
    main()
