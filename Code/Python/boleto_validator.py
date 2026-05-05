#!/usr/bin/env python3
import argparse
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("[ERROR] Missing dependency: pymupdf. Install with: pip install pymupdf")
    sys.exit(1)

try:
    from PIL import Image
    from pyzbar.pyzbar import decode as zbar_decode
except ImportError:
    Image = None
    zbar_decode = None


BANKS = {
    "001": "Banco do Brasil",
    "033": "Santander",
    "104": "Caixa Econômica Federal",
    "237": "Bradesco",
    "341": "Itaú",
    "336": "C6 Bank",
    "422": "Safra",
    "756": "Sicoob",
}


def only_digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def mod10_check_digit(number: str) -> int:
    total = 0
    factor = 2

    for digit in reversed(number):
        product = int(digit) * factor
        if product > 9:
            product = (product // 10) + (product % 10)

        total += product
        factor = 1 if factor == 2 else 2

    remainder = total % 10
    return 0 if remainder == 0 else 10 - remainder


def mod11_barcode_dac(barcode_without_dac: str) -> int:
    total = 0
    factor = 2

    for digit in reversed(barcode_without_dac):
        total += int(digit) * factor
        factor += 1
        if factor > 9:
            factor = 2

    remainder = total % 11
    dac = 11 - remainder

    if dac in (0, 10, 11):
        return 1

    return dac


def linha_to_barcode(linha: str) -> str:
    linha = only_digits(linha)

    if len(linha) != 47:
        raise ValueError("Linha digitável must contain exactly 47 digits.")

    campo1 = linha[0:10]
    campo2 = linha[10:21]
    campo3 = linha[21:32]
    dac_geral = linha[32]
    fator_valor = linha[33:47]

    free_field = campo1[4:9] + campo2[0:10] + campo3[0:10]

    return linha[0:4] + dac_geral + fator_valor + free_field


def barcode_to_linha(barcode: str) -> str:
    barcode = only_digits(barcode)

    if len(barcode) != 44:
        raise ValueError("Barcode must contain exactly 44 digits.")

    bank_currency = barcode[0:4]
    dac_geral = barcode[4]
    fator_valor = barcode[5:19]
    free_field = barcode[19:44]

    campo1_base = bank_currency + free_field[0:5]
    campo2_base = free_field[5:15]
    campo3_base = free_field[15:25]

    campo1 = campo1_base + str(mod10_check_digit(campo1_base))
    campo2 = campo2_base + str(mod10_check_digit(campo2_base))
    campo3 = campo3_base + str(mod10_check_digit(campo3_base))

    return campo1 + campo2 + campo3 + dac_geral + fator_valor


def due_date_from_factor(factor: str):
    """
    Brazilian boleto due-date factor:
    - Original base: 1997-10-07
    - On 2025-02-22, factor restarted at 1000.
    """
    if not factor or factor == "0000":
        return None

    factor_int = int(factor)

    if factor_int >= 1000:
        new_base = date(2025, 2, 22)
        return new_base + timedelta(days=factor_int - 1000)

    old_base = date(1997, 10, 7)
    return old_base + timedelta(days=factor_int)


def extract_text_from_pdf(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    chunks = []

    for page in doc:
        chunks.append(page.get_text("text"))

    return "\n".join(chunks)


def find_linhas_digitaveis(text: str) -> list[str]:
    candidates = []

    # Matches formatted or unformatted boleto linha digitável.
    pattern = re.compile(
        r"""
        (?:
            \b\d{5}[.\s]?\d{5}\s+
            \d{5}[.\s]?\d{6}\s+
            \d{5}[.\s]?\d{6}\s+
            \d\s+
            \d{14}\b
        )
        |
        (?:
            \b\d{47}\b
        )
        """,
        re.VERBOSE,
    )

    for match in pattern.finditer(text):
        digits = only_digits(match.group(0))
        if len(digits) == 47 and digits not in candidates:
            candidates.append(digits)

    return candidates


def find_possible_barcode_text(text: str) -> list[str]:
    candidates = []

    for match in re.finditer(r"\b\d{44}\b", only_digits(text)):
        value = match.group(0)
        if value not in candidates:
            candidates.append(value)

    return candidates


def decode_barcodes_from_pdf_images(pdf_path: Path, dpi: int = 300) -> list[str]:
    if Image is None or zbar_decode is None:
        return []

    found = []
    doc = fitz.open(pdf_path)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for page in doc:
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        decoded_items = zbar_decode(img)

        for item in decoded_items:
            raw = item.data.decode("utf-8", errors="ignore")
            digits = only_digits(raw)

            if len(digits) == 44 and digits not in found:
                found.append(digits)

    return found


def validate_linha(linha: str) -> dict:
    linha = only_digits(linha)

    if len(linha) != 47:
        return {"valid": False, "error": "Linha digitável does not have 47 digits."}

    c1_base = linha[0:9]
    c1_dac = int(linha[9])

    c2_base = linha[10:20]
    c2_dac = int(linha[20])

    c3_base = linha[21:31]
    c3_dac = int(linha[31])

    checks = {
        "field_1": mod10_check_digit(c1_base) == c1_dac,
        "field_2": mod10_check_digit(c2_base) == c2_dac,
        "field_3": mod10_check_digit(c3_base) == c3_dac,
    }

    barcode = linha_to_barcode(linha)
    barcode_without_dac = barcode[:4] + barcode[5:]
    expected_dac = mod11_barcode_dac(barcode_without_dac)

    checks["general_dac"] = expected_dac == int(barcode[4])

    return {
        "valid": all(checks.values()),
        "checks": checks,
        "barcode": barcode,
        "expected_general_dac": expected_dac,
        "actual_general_dac": int(barcode[4]),
    }


def analyze_barcode(barcode: str) -> dict:
    barcode = only_digits(barcode)

    if len(barcode) != 44:
        raise ValueError("Barcode must have 44 digits.")

    bank = barcode[0:3]
    currency = barcode[3]
    general_dac = barcode[4]
    factor = barcode[5:9]
    amount_raw = barcode[9:19]
    free_field = barcode[19:44]

    amount = Decimal(amount_raw) / Decimal("100")
    due_date = due_date_from_factor(factor)

    expected_dac = mod11_barcode_dac(barcode[:4] + barcode[5:])

    return {
        "barcode": barcode,
        "bank_code": bank,
        "bank_name": BANKS.get(bank, "Unknown"),
        "currency_code": currency,
        "currency": "BRL" if currency == "9" else "Unknown",
        "general_dac": general_dac,
        "expected_general_dac": str(expected_dac),
        "general_dac_valid": general_dac == str(expected_dac),
        "due_factor": factor,
        "due_date": due_date.isoformat() if due_date else None,
        "amount": f"{amount:.2f}",
        "free_field": free_field,
        "linha_digitavel_from_barcode": barcode_to_linha(barcode),
    }


def print_report(pdf_path: Path, linhas: list[str], barcodes_text: list[str], barcodes_img: list[str]):
    print("=" * 72)
    print("BOLETO PDF ANALYSIS")
    print("=" * 72)
    print(f"File: {pdf_path}")
    print()

    all_barcodes = []

    print("[Linha Digitável]")
    if not linhas:
        print("  Not found")
    else:
        for idx, linha in enumerate(linhas, 1):
            validation = validate_linha(linha)
            barcode = validation.get("barcode")

            if barcode and barcode not in all_barcodes:
                all_barcodes.append(barcode)

            print(f"  #{idx}")
            print(f"    Raw:        {linha}")
            print(f"    Formatted:  {linha[0:5]}.{linha[5:10]} {linha[10:15]}.{linha[15:21]} {linha[21:26]}.{linha[26:32]} {linha[32]} {linha[33:47]}")
            print(f"    Valid:      {validation['valid']}")

            if "checks" in validation:
                checks = validation["checks"]
                print("    Checks:")
                print(f"      Field 1 mod10:   {checks['field_1']}")
                print(f"      Field 2 mod10:   {checks['field_2']}")
                print(f"      Field 3 mod10:   {checks['field_3']}")
                print(f"      General DAC:     {checks['general_dac']}")
                print(f"    Barcode derived:   {barcode}")

            print()

    print("[Barcode]")
    for src, barcodes in (("Text", barcodes_text), ("Image scan", barcodes_img)):
        if barcodes:
            print(f"  Source: {src}")
            for bc in barcodes:
                print(f"    {bc}")
                if bc not in all_barcodes:
                    all_barcodes.append(bc)
        else:
            print(f"  Source: {src}: not found")
    print()

    unique_barcodes = list(dict.fromkeys(all_barcodes))

    print("[Structured Data]")
    if not unique_barcodes:
        print("  No barcode available for structured analysis.")
        print()
        return

    for idx, barcode in enumerate(unique_barcodes, 1):
        try:
            info = analyze_barcode(barcode)
        except Exception as exc:
            print(f"  #{idx}: failed to analyze barcode: {exc}")
            continue

        print(f"  #{idx}")
        print(f"    Bank:              {info['bank_code']} - {info['bank_name']}")
        print(f"    Currency:          {info['currency_code']} - {info['currency']}")
        print(f"    Amount:            R$ {info['amount']}")
        print(f"    Due factor:        {info['due_factor']}")
        print(f"    Due date:          {info['due_date']}")
        print(f"    General DAC:       {info['general_dac']}")
        print(f"    Expected DAC:      {info['expected_general_dac']}")
        print(f"    DAC valid:         {info['general_dac_valid']}")
        print(f"    Free field:        {info['free_field']}")
        print(f"    Linha from barcode:{info['linha_digitavel_from_barcode']}")
        print()

    if linhas and unique_barcodes:
        print("[Consistency]")
        for linha in linhas:
            derived = linha_to_barcode(linha)
            match = derived in unique_barcodes
            print(f"  Linha -> barcode match found: {match}")
            print(f"    Linha:   {linha}")
            print(f"    Barcode: {derived}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Extract and analyze Brazilian boleto linha digitável and barcode from a PDF."
    )
    parser.add_argument("pdf", help="Path to boleto PDF")
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI used to render PDF pages for barcode image decoding. Default: 300",
    )

    args = parser.parse_args()
    pdf_path = Path(args.pdf)

    if not pdf_path.exists():
        print(f"[ERROR] File not found: {pdf_path}")
        sys.exit(1)

    if not pdf_path.is_file():
        print(f"[ERROR] Not a file: {pdf_path}")
        sys.exit(1)

    text = extract_text_from_pdf(pdf_path)

    linhas = find_linhas_digitaveis(text)
    barcode_text = find_possible_barcode_text(text)
    barcode_img = decode_barcodes_from_pdf_images(pdf_path, dpi=args.dpi)

    print_report(pdf_path, linhas, barcode_text, barcode_img)


if __name__ == "__main__":
    main()