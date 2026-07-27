"""PDF cleaning: metadata removal, active content removal, recompression, encryption.

A PDF hides identifying data in more places than the properties dialog shows:
  - the DocInfo dictionary (Author, Producer, Creator, CreationDate)
  - an XMP packet at the document root, which often disagrees with DocInfo and
    is the copy that survives most "remove properties" tools
  - per-page XMP and /PieceInfo, where editors park private application state
    (Illustrator and InDesign both leave working data here)
  - /AA additional-action dictionaries and embedded JavaScript
  - attached files, which travel invisibly inside the document

All of those are removed. Compression is a separate pass over the embedded
images, since in almost every real document the images are the file.
"""
from __future__ import annotations

import io
import math
import os
import secrets

import pikepdf
from PIL import Image

from scrub import images as _images
from scrub.similarity import floor_for

AMBIGUOUS = "Il1O0S5B8|`'\","


def generate_password(length: int = 24, symbols: bool = True,
                      avoid_ambiguous: bool = True) -> tuple[str, float]:
    """A password from the system CSPRNG. Returns (password, entropy_bits)."""
    length = max(8, min(128, int(length)))
    alphabet = ("abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789")
    if symbols:
        alphabet += "!#$%&()*+-=?@[]^_{}~"
    if avoid_ambiguous:
        alphabet = "".join(c for c in alphabet if c not in AMBIGUOUS)
    pw = "".join(secrets.choice(alphabet) for _ in range(length))
    return pw, length * math.log2(len(alphabet))


def _strip_document_metadata(pdf: pikepdf.Pdf, log) -> None:
    found = []

    try:
        info = dict(pdf.docinfo)
    except Exception:
        info = {}
    if info:
        found.append(f"DocInfo ({', '.join(str(k).lstrip('/') for k in info)})")
    with pdf.open_metadata(set_pikepdf_as_editor=False,
                           update_docinfo=False) as meta:
        keys = list(meta.keys())
        if keys:
            found.append(f"XMP ({len(keys)} properties)")
        for key in keys:
            del meta[key]

    if "/Metadata" in pdf.Root:
        del pdf.Root["/Metadata"]
    if "/Info" in pdf.trailer:
        del pdf.trailer["/Info"]
    try:
        pdf.docinfo.clear()
    except Exception:
        pass

    for key in ("/PieceInfo", "/LastModified", "/SpiderInfo"):
        if key in pdf.Root:
            del pdf.Root[key]
            found.append(f"root {key.lstrip('/')}")

    log("document metadata removed: " + ("; ".join(found) if found else "nothing present"))


def _strip_active_content(pdf: pikepdf.Pdf, log) -> None:
    removed = []

    names = pdf.Root.get("/Names")
    if names is not None:
        if "/JavaScript" in names:
            del names["/JavaScript"]
            removed.append("document JavaScript")
        if "/EmbeddedFiles" in names:
            del names["/EmbeddedFiles"]
            removed.append("embedded file attachments")
        if len(names.keys()) == 0:
            del pdf.Root["/Names"]   # do not leave an empty husk behind

    if "/OpenAction" in pdf.Root:
        action = pdf.Root["/OpenAction"]
        if isinstance(action, pikepdf.Dictionary) and action.get("/S") == "/JavaScript":
            del pdf.Root["/OpenAction"]
            removed.append("JavaScript on open")
    if "/AA" in pdf.Root:
        del pdf.Root["/AA"]
        removed.append("document additional-actions")

    n_page_actions = 0
    n_file_annots = 0
    for page in pdf.pages:
        obj = page.obj
        if "/AA" in obj:
            del obj["/AA"]
            n_page_actions += 1
        annots = obj.get("/Annots")
        if annots is None:
            continue
        keep = []
        for annot in annots:
            try:
                subtype = annot.get("/Subtype")
                if subtype == "/FileAttachment" or "/EF" in annot:
                    n_file_annots += 1
                    continue
                if isinstance(annot.get("/A"), pikepdf.Dictionary) and \
                        annot["/A"].get("/S") == "/JavaScript":
                    n_file_annots += 1
                    continue
                if "/AA" in annot:
                    del annot["/AA"]
                keep.append(annot)
            except Exception:
                keep.append(annot)
        if len(keep) != len(annots):
            obj["/Annots"] = pdf.make_indirect(pikepdf.Array(keep))

    if n_page_actions:
        removed.append(f"{n_page_actions} page action dict(s)")
    if n_file_annots:
        removed.append(f"{n_file_annots} attachment/script annotation(s)")

    log("active content removed: " + ("; ".join(removed) if removed else "none found"))


def _strip_page_metadata(pdf: pikepdf.Pdf, log) -> None:
    n = 0
    for page in pdf.pages:
        obj = page.obj
        for key in ("/Metadata", "/PieceInfo", "/LastModified"):
            if key in obj:
                del obj[key]
                n += 1
    log(f"page-level metadata entries removed: {n}")


MAX_PAGES = int(os.environ.get("SCRUB_PDF_MAX_PAGES", "5000"))


# Below this, searching costs more than it saves; a fixed high setting is used.
SEARCH_MIN_PIXELS = 300_000


def _recompress_images(pdf: pikepdf.Pdf, floor: float | None, max_edge: int,
                       log, progress, lo: int, hi: int) -> None:
    seen: set[tuple[int, int]] = set()
    saved = 0
    touched = 0
    searched = 0
    pages = min(len(pdf.pages), MAX_PAGES)
    if len(pdf.pages) > MAX_PAGES:
        log(f"only the first {MAX_PAGES} pages are scanned for images "
            f"(of {len(pdf.pages)}); metadata removal still covers all of them")

    for idx, page in enumerate(pdf.pages[:pages]):
        try:
            images = dict(page.images)
        except Exception:
            images = {}
        for _name, raw in images.items():
            key = (raw.objgen[0], raw.objgen[1])
            if key in seen:
                continue
            seen.add(key)
            # Screen on the dictionary first. Decoding a JPEG only to discover
            # it was already small is the expensive way to learn nothing.
            try:
                width = int(raw.get("/Width", 0))
                height = int(raw.get("/Height", 0))
                bpc = int(raw.get("/BitsPerComponent", 8))
            except Exception:
                width = height = 0
                bpc = 8
            if bpc == 1:
                continue          # bilevel scan: CCITT/JBIG2, leave it alone
            if width and height and not (max_edge and max(width, height) > max_edge):
                if width * height < 90_000:
                    continue      # under ~0.1 MP, recompression buys nothing
            try:
                before = len(raw.read_raw_bytes())
            except Exception:
                continue
            if before < 8192:
                continue
            try:
                pdfimage = pikepdf.PdfImage(raw)
                if pdfimage.bits_per_component == 1:
                    # Bilevel scans are CCITT or JBIG2. JPEG would both wreck
                    # the text edges and make the file bigger.
                    continue
                pil = pdfimage.as_pil_image()
            except Exception:
                continue

            if pil.mode not in ("RGB", "L"):
                pil = pil.convert("RGB")
            if max_edge and max(pil.size) > max_edge:
                pil.thumbnail((max_edge, max_edge), Image.LANCZOS)

            if floor is None:
                continue     # lossless: the images are the picture, leave them
            if pil.width * pil.height >= SEARCH_MIN_PIXELS:
                # Same perceptual search the standalone image path uses, so a
                # scanned page and a photo get judged the same way.
                data = _images.search_encode(pil, "JPEG", floor, lambda _m: None)
                searched += 1
            else:
                buf = io.BytesIO()
                pil.save(buf, format="JPEG", quality=88, optimize=True,
                         progressive=True, subsampling=2)
                data = buf.getvalue()
            if len(data) >= before:
                continue  # already smaller than we can do; leave it alone

            raw.write(data, filter=pikepdf.Name("/DCTDecode"))
            raw.ColorSpace = pikepdf.Name(
                "/DeviceRGB" if pil.mode == "RGB" else "/DeviceGray")
            raw.BitsPerComponent = 8
            raw.Width, raw.Height = pil.size
            for key_name in ("/DecodeParms", "/Decode"):
                if key_name in raw:
                    del raw[key_name]
            saved += before - len(data)
            touched += 1

        progress(lo + int((hi - lo) * (idx + 1) / max(pages, 1)))

    if touched:
        note = f", {searched} chosen by perceptual search" if searched else ""
        log(f"recompressed {touched} image(s){note}, {saved // 1024} KB removed")
    else:
        log("no images worth recompressing")


def process(src: str, out_dir: str, opts: dict, log, progress) -> str:
    """Clean a PDF at the requested quality level."""
    dst = os.path.join(out_dir, "out.pdf")
    _produce(src, dst, opts, floor_for(opts.get("level", "balanced")),
             int(opts.get("pdf_max_edge", 2000) or 0), log, progress, 5, 95)
    progress(98)
    return dst


def _produce(src: str, dst: str, opts: dict, floor: float | None, max_edge: int,
             log, progress, lo: int, hi: int) -> None:
    compress_images = bool(opts.get("pdf_compress_images", True))
    strip_active = bool(opts.get("pdf_strip_active", True))
    open_password = opts.get("pdf_open_password") or ""
    user_pw = opts.get("pdf_password") or ""
    perms = opts.get("pdf_permissions") or {}

    progress(lo)
    pdf = pikepdf.open(src, password=open_password, allow_overwriting_input=False)
    if pdf.is_encrypted:
        log("source was encrypted; opened with supplied password")
    log(f"{len(pdf.pages)} page(s), PDF {pdf.pdf_version}")

    span = hi - lo
    _strip_document_metadata(pdf, log)
    _strip_page_metadata(pdf, log)
    progress(lo + span // 6)
    if strip_active:
        _strip_active_content(pdf, log)
    progress(lo + span // 4)

    if compress_images:
        _recompress_images(pdf, floor, max_edge, log, progress,
                           lo + span // 4, lo + int(span * 0.85))
    else:
        progress(lo + int(span * 0.85))

    try:
        pdf.remove_unreferenced_resources()
    except Exception:
        pass

    save_kwargs = dict(
        compress_streams=True,
        recompress_flate=True,
        object_stream_mode=pikepdf.ObjectStreamMode.generate,
    )

    if user_pw:
        # A distinct owner password means the permission flags cannot be lifted
        # by anyone holding only the open password.
        owner_pw, _ = generate_password(32, symbols=True, avoid_ambiguous=False)
        allow = pikepdf.Permissions(
            accessibility=True,
            extract=bool(perms.get("extract", False)),
            modify_annotation=bool(perms.get("annotate", False)),
            modify_assembly=False,
            modify_form=bool(perms.get("forms", False)),
            modify_other=bool(perms.get("modify", False)),
            print_lowres=bool(perms.get("print", True)),
            print_highres=bool(perms.get("print", True)),
        )
        save_kwargs["encryption"] = pikepdf.Encryption(
            user=user_pw, owner=owner_pw, R=6, aes=True, allow=allow)
        log("encrypting with AES-256 (revision 6); owner password randomised")
    else:
        # A deterministic file ID means two runs of the same input produce the
        # same bytes, instead of a random ID that could correlate copies.
        # QPDF cannot do this alongside encryption, so it is the unlocked path only.
        save_kwargs["deterministic_id"] = True
        save_kwargs["linearize"] = True

    pdf.save(dst, **save_kwargs)
    pdf.close()

    # qpdf writes its own /Producer during save. Strip it in a second pass.
    if not user_pw:
        try:
            with pikepdf.open(dst, allow_overwriting_input=True) as check:
                leftovers = [str(k) for k in check.docinfo.keys()]
                if leftovers:
                    check.docinfo.clear()
                    if "/Info" in check.trailer:
                        del check.trailer["/Info"]
                    check.save(dst + ".tmp", **{k: v for k, v in save_kwargs.items()
                                                if k != "linearize"})
                    os.replace(dst + ".tmp", dst)
                    log(f"second pass removed writer-added tags: {', '.join(leftovers)}")
        except Exception:
            pass

    progress(hi)
