#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
from pypdf import PdfReader


SUSPICIOUS_TOKENS = [
    b"/JavaScript",
    b"/JS",
    b"/OpenAction",
    b"/AA",
    b"/Launch",
    b"/EmbeddedFile",
    b"/Filespec",
    b"/RichMedia",
    b"/XFA",
    b"/AcroForm",
    b"/SubmitForm",
    b"/ImportData",
    b"/GoToE",
    b"/GoToR",
    b"/URI",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_hashes(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "md5": hashlib.md5(data).hexdigest(),
        "sha1": hashlib.sha1(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def extract_urls(data: bytes) -> list[str]:
    pattern = rb"""(?i)\b(?:https?|ftp)://[^\s<>"')\]]+"""
    urls = sorted(set(m.group(0).decode("utf-8", errors="replace") for m in re.finditer(pattern, data)))
    return urls


def scan_raw_tokens(data: bytes) -> dict:
    results = {}
    for token in SUSPICIOUS_TOKENS:
        positions = [m.start() for m in re.finditer(re.escape(token), data)]
        results[token.decode()] = {
            "count": len(positions),
            "offsets_first_20": positions[:20],
        }
    return results


def get_pdf_metadata_pymupdf(doc: fitz.Document) -> dict:
    return dict(doc.metadata or {})


def get_pdf_metadata_pypdf(path: Path) -> dict:
    try:
        reader = PdfReader(str(path))
        meta = reader.metadata or {}
        return {str(k): str(v) for k, v in meta.items()}
    except Exception as exc:
        return {"error": str(exc)}


def get_page_inventory(doc: fitz.Document) -> list[dict]:
    pages = []
    for page_index in range(doc.page_count):
        page = doc[page_index]

        links = []
        for link in page.get_links():
            item = dict(link)
            if "from" in item:
                item["from"] = list(item["from"])
            links.append(item)

        annotations = []
        annot = page.first_annot
        while annot:
            annotations.append({
                "type": annot.type,
                "xref": annot.xref,
                "content": annot.info.get("content", ""),
                "title": annot.info.get("title", ""),
                "subject": annot.info.get("subject", ""),
                "name": annot.info.get("name", ""),
            })
            annot = annot.next

        images = []
        for img in page.get_images(full=True):
            images.append({
                "xref": img[0],
                "smask": img[1],
                "width": img[2],
                "height": img[3],
                "bpc": img[4],
                "colorspace": img[5],
                "alt_colorspace": img[6],
                "name": img[7],
                "filter": img[8],
            })

        fonts = []
        for font in page.get_fonts(full=True):
            fonts.append({
                "xref": font[0],
                "ext": font[1],
                "type": font[2],
                "basefont": font[3],
                "name": font[4],
                "encoding": font[5],
                "embedded": font[6],
            })

        drawings_count = len(page.get_drawings())

        pages.append({
            "page": page_index + 1,
            "text_length": len(page.get_text("text") or ""),
            "links": links,
            "annotations": annotations,
            "image_count": len(images),
            "images": images,
            "font_count": len(fonts),
            "fonts": fonts,
            "drawing_object_count": drawings_count,
        })

    return pages


def get_embedded_files(doc: fitz.Document) -> list[dict]:
    embedded = []
    try:
        count = doc.embfile_count()
    except Exception:
        return embedded

    for i in range(count):
        try:
            info = doc.embfile_info(i)
            embedded.append({
                "index": i,
                "filename": info.get("filename"),
                "ufilename": info.get("ufilename"),
                "description": info.get("desc"),
                "size": info.get("size"),
                "creation_date": info.get("creationDate"),
                "modification_date": info.get("modDate"),
            })
        except Exception as exc:
            embedded.append({"index": i, "error": str(exc)})

    return embedded


def xref_object_scan(doc: fitz.Document, max_object_preview: int = 500) -> list[dict]:
    findings = []

    for xref in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(xref, compressed=True)
        except Exception:
            continue

        obj_l = obj.lower()
        hits = []

        for token in SUSPICIOUS_TOKENS:
            t = token.decode(errors="ignore").lower()
            if t in obj_l:
                hits.append(token.decode(errors="ignore"))

        if hits:
            preview = obj[:max_object_preview].replace("\n", "\\n")
            findings.append({
                "xref": xref,
                "hits": hits,
                "preview": preview,
            })

    return findings


def catalog_checks(path: Path) -> dict:
    results = {}
    try:
        reader = PdfReader(str(path))
        trailer = reader.trailer
        root = trailer.get("/Root", {})

        for key in ["/OpenAction", "/AA", "/AcroForm", "/Names", "/Outlines"]:
            try:
                results[key] = str(root.get(key)) if key in root else None
            except Exception as exc:
                results[key] = f"error: {exc}"

        results["is_encrypted"] = bool(reader.is_encrypted)
        results["page_count"] = len(reader.pages)
    except Exception as exc:
        results["error"] = str(exc)

    return results


def risk_summary(raw_tokens: dict, xref_findings: list[dict], embedded_files: list[dict], urls: list[str], catalog: dict) -> dict:
    risk = []
    score = 0

    high_tokens = ["/JavaScript", "/JS", "/OpenAction", "/AA", "/Launch", "/EmbeddedFile", "/RichMedia", "/XFA"]
    for token in high_tokens:
        if raw_tokens.get(token, {}).get("count", 0) > 0:
            risk.append(f"Token present: {token}")
            score += 3

    if embedded_files:
        risk.append("Embedded files present")
        score += 4

    if urls:
        risk.append("External URLs present")
        score += 1

    if catalog.get("/OpenAction"):
        risk.append("Catalog contains /OpenAction")
        score += 4

    if catalog.get("/AA"):
        risk.append("Catalog contains /AA additional actions")
        score += 4

    if xref_findings:
        score += min(len(xref_findings), 5)

    if score == 0:
        level = "low"
    elif score <= 3:
        level = "medium"
    else:
        level = "high"

    return {
        "risk_level": level,
        "risk_score": score,
        "findings": risk,
    }


def build_report(path: Path) -> dict:
    data = path.read_bytes()
    doc = fitz.open(path)

    raw_tokens = scan_raw_tokens(data)
    embedded_files = get_embedded_files(doc)
    urls = extract_urls(data)
    xref_findings = xref_object_scan(doc)
    catalog = catalog_checks(path)

    return {
        "file": str(path),
        "hashes": file_hashes(path),
        "metadata_pymupdf": get_pdf_metadata_pymupdf(doc),
        "metadata_pypdf": get_pdf_metadata_pypdf(path),
        "catalog_checks": catalog,
        "raw_token_scan": raw_tokens,
        "urls": urls,
        "embedded_files": embedded_files,
        "xref_suspicious_objects": xref_findings,
        "pages": get_page_inventory(doc),
        "risk_summary": risk_summary(raw_tokens, xref_findings, embedded_files, urls, catalog),
    }


def print_human(report: dict):
    print("=" * 80)
    print("PDF STATIC TRIAGE REPORT")
    print("=" * 80)

    print(f"File: {report['file']}")
    print(f"Size: {report['hashes']['size_bytes']} bytes")
    print(f"MD5: {report['hashes']['md5']}")
    print(f"SHA1: {report['hashes']['sha1']}")
    print(f"SHA256: {report['hashes']['sha256']}")
    print()

    risk = report["risk_summary"]
    print("[Risk]")
    print(f"  Level: {risk['risk_level']}")
    print(f"  Score: {risk['risk_score']}")
    if risk["findings"]:
        for item in risk["findings"]:
            print(f"  - {item}")
    else:
        print("  No obvious high-risk PDF features found.")
    print()

    print("[Metadata: PyMuPDF]")
    for k, v in report["metadata_pymupdf"].items():
        print(f"  {k}: {v}")
    print()

    print("[Metadata: pypdf]")
    for k, v in report["metadata_pypdf"].items():
        print(f"  {k}: {v}")
    print()

    print("[Catalog]")
    for k, v in report["catalog_checks"].items():
        print(f"  {k}: {v}")
    print()

    print("[Suspicious Tokens]")
    for token, info in report["raw_token_scan"].items():
        if info["count"]:
            print(f"  {token}: {info['count']} occurrence(s), offsets={info['offsets_first_20']}")
    if not any(info["count"] for info in report["raw_token_scan"].values()):
        print("  None found.")
    print()

    print("[URLs]")
    if report["urls"]:
        for url in report["urls"]:
            print(f"  {url}")
    else:
        print("  None found.")
    print()

    print("[Embedded Files]")
    if report["embedded_files"]:
        for item in report["embedded_files"]:
            print(f"  {item}")
    else:
        print("  None found.")
    print()

    print("[Suspicious XRef Objects]")
    if report["xref_suspicious_objects"]:
        for item in report["xref_suspicious_objects"]:
            print(f"  xref {item['xref']} hits={item['hits']}")
            print(f"    preview: {item['preview']}")
    else:
        print("  None found.")
    print()

    print("[Pages]")
    for page in report["pages"]:
        print(f"  Page {page['page']}")
        print(f"    Text length: {page['text_length']}")
        print(f"    Links: {len(page['links'])}")
        print(f"    Annotations: {len(page['annotations'])}")
        print(f"    Images: {page['image_count']}")
        print(f"    Fonts: {page['font_count']}")
        print(f"    Drawing objects: {page['drawing_object_count']}")

        if page["links"]:
            print("    Link details:")
            for link in page["links"]:
                print(f"      {link}")

        if page["annotations"]:
            print("    Annotation details:")
            for annot in page["annotations"]:
                print(f"      {annot}")

        if page["fonts"]:
            print("    Fonts:")
            for font in page["fonts"]:
                print(f"      {font}")

        if page["images"]:
            print("    Images:")
            for image in page["images"]:
                print(f"      {image}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Static PDF metadata and object triage.")
    parser.add_argument("pdf", help="PDF file to analyze")
    parser.add_argument("--json", dest="json_out", help="Write full JSON report to this file")
    parser.add_argument("--quiet", action="store_true", help="Only write JSON, do not print human report")

    args = parser.parse_args()
    path = Path(args.pdf)

    if not path.exists():
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)

    if not path.is_file():
        print(f"[ERROR] Not a file: {path}")
        sys.exit(1)

    try:
        report = build_report(path)
    except Exception as exc:
        print(f"[ERROR] Failed to analyze PDF: {exc}")
        sys.exit(1)

    if args.json_out:
        out = Path(args.json_out)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] JSON report written: {out}")

    if not args.quiet:
        print_human(report)


if __name__ == "__main__":
    main()