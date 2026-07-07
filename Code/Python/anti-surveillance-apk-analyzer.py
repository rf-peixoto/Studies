#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
mad_apk_hunter.py

Varre APKs em uma pasta e subpastas procurando pistas de Mobile Application Defense / MAD,
RASP, app shielding, antifraude mobile e artefatos relacionados.

Dependências obrigatórias:
    - Python 3.10+

Ferramentas opcionais:
    - jadx
    - unzip
    - apktool
    - aapt ou aapt2

Exemplos:
    python3 mad_apk_hunter.py ./apks
    python3 mad_apk_hunter.py ./apks --out ./mad_results --jadx always
    python3 mad_apk_hunter.py ./apks --jadx never --apktool never
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional


# ----------------------------------------------------------------------
# Indicadores
# ----------------------------------------------------------------------

INDICATOR_PATTERNS = [
    # Indicadores explícitos de fornecedor/produto: alta confiança.
    {
        "id": "mad_domain",
        "category": "explicit_mad",
        "severity": "HIGH",
        "score": 100,
        "regex": r"\b(?:[\w.-]+\.)?mobileappdefense\.com\b",
        "description": "Domínio explicitamente relacionado a Mobile App Defense.",
    },
    {
        "id": "mad_product_name",
        "category": "explicit_mad",
        "severity": "HIGH",
        "score": 95,
        "regex": r"\bMobile\s+Application\s+Defense\b|\bMAD\s+Dynamic\s+Protection\b|\bMAD\s+Dynamic\b",
        "description": "Nome explícito do produto/fornecedor.",
    },
    {
        "id": "mad_tooling",
        "category": "explicit_mad",
        "severity": "HIGH",
        "score": 90,
        "regex": r"\bmad-cli\b|\bMadconfigGen\b|\bMAD\s+Command\s+Center\b",
        "description": "Ferramenta ou componente associado ao MAD.",
    },
    {
        "id": "possible_appcrypt",
        "category": "possible_mad",
        "severity": "MEDIUM",
        "score": 45,
        "regex": r"\bAppCrypt\b|\bApp\s*Crypt\b",
        "description": "Possível referência a AppCrypt/MAD; requer confirmação manual.",
    },

    # Antifraude comportamental citada no material MAD. Não prova MAD sozinha.
    {
        "id": "sim_swap_terms",
        "category": "mobile_antifraud",
        "severity": "MEDIUM",
        "score": 25,
        "regex": r"\bSIM\s*Swap\b|\bSIMSwap\b|\bsim_swap\b|\bsim-swap\b",
        "description": "Referência a SIM Swap.",
    },
    {
        "id": "vishing_terms",
        "category": "mobile_antifraud",
        "severity": "MEDIUM",
        "score": 25,
        "regex": r"\bvishing\b|\bvoice\s+phishing\b|\bactive\s+call\b|\bphone\s+call\s+active\b|\blig[aã]o\s+ativa\b",
        "description": "Referência a vishing ou chamada ativa.",
    },
    {
        "id": "virtual_camera_terms",
        "category": "mobile_antifraud",
        "severity": "MEDIUM",
        "score": 20,
        "regex": r"\bvirtual\s+camera\b|\bcamera\s+virtual\b|\bdeepfake\b|\bfake\s+camera\b",
        "description": "Referência a câmera virtualizada/deepfake.",
    },
    {
        "id": "autoclick_terms",
        "category": "mobile_antifraud",
        "severity": "LOW",
        "score": 10,
        "regex": r"\bauto[-_ ]?click\b|\bautoclicker\b|\baccessibility\s+abuse\b",
        "description": "Referência a auto-click ou abuso de acessibilidade.",
    },

    # RASP / anti-instrumentação / anti-debug / anti-root.
    # Esses indicadores sugerem RASP/app shielding, mas não identificam MAD especificamente.
    {
        "id": "frida_detection",
        "category": "rasp_instrumentation",
        "severity": "LOW",
        "score": 12,
        "regex": r"\bfrida\b|\bfrida-server\b|\bfrida-gadget\b|\bgum-js-loop\b|\bre\.frida\b",
        "description": "Referência a Frida/Frida Gadget.",
    },
    {
        "id": "xposed_detection",
        "category": "rasp_instrumentation",
        "severity": "LOW",
        "score": 10,
        "regex": r"\bxposed\b|\blsposed\b|\bedxposed\b|\bsubstrate\b|\bcydia\s+substrate\b",
        "description": "Referência a Xposed/LSPosed/Substrate.",
    },
    {
        "id": "zygisk_magisk_detection",
        "category": "rasp_root",
        "severity": "LOW",
        "score": 10,
        "regex": r"\bmagisk\b|\bzygisk\b|\bshamiko\b|\bsu\b|\bsuperuser\b",
        "description": "Referência a Magisk/Zygisk/su.",
    },
    {
        "id": "debugger_detection",
        "category": "rasp_debug",
        "severity": "LOW",
        "score": 8,
        "regex": r"\banti[-_ ]?debug\b|\bptrace\b|\bTracerPid\b|\bisDebuggerConnected\b|\bDebug\.isDebuggerConnected\b",
        "description": "Referência a anti-debugging.",
    },
    {
        "id": "emulator_detection",
        "category": "rasp_environment",
        "severity": "LOW",
        "score": 8,
        "regex": r"\bqemu\b|\bgoldfish\b|\branchu\b|\bgenymotion\b|\blemulator\b|\bro\.kernel\.qemu\b",
        "description": "Referência a detecção de emulador/virtualização.",
    },
    {
        "id": "tamper_integrity",
        "category": "rasp_integrity",
        "severity": "LOW",
        "score": 8,
        "regex": r"\banti[-_ ]?tamper\b|\btamper(?:ing)?\b|\bintegrity\s+check\b|\bsignature\s+check\b|\bapk\s+signature\b",
        "description": "Referência a anti-tampering/integridade.",
    },
    {
        "id": "ssl_pinning",
        "category": "network_security",
        "severity": "LOW",
        "score": 6,
        "regex": r"\bssl\s*pinning\b|\bcertificate\s+pinning\b|\btrustmanager\b|\bX509TrustManager\b|\bpinning\b",
        "description": "Referência a SSL/certificate pinning.",
    },
    {
        "id": "proxy_vpn_detection",
        "category": "rasp_network",
        "severity": "LOW",
        "score": 6,
        "regex": r"\bproxy\s+detection\b|\bvpn\s+detection\b|\bisVpnActive\b|\bNetworkCapabilities\.TRANSPORT_VPN\b",
        "description": "Referência a detecção de proxy/VPN.",
    },
]


PERMISSION_PATTERNS = [
    # Não são evidência de MAD. Servem apenas como contexto.
    "android.permission.READ_PHONE_STATE",
    "android.permission.READ_PHONE_NUMBERS",
    "android.permission.READ_BASIC_PHONE_STATE",
    "android.permission.CALL_PHONE",
    "android.permission.READ_CALL_LOG",
    "android.permission.PROCESS_OUTGOING_CALLS",
    "android.permission.CAMERA",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.ACCESS_BACKGROUND_LOCATION",
    "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.ACCESS_WIFI_STATE",
    "android.permission.QUERY_ALL_PACKAGES",
    "android.permission.PACKAGE_USAGE_STATS",
    "android.permission.BIND_ACCESSIBILITY_SERVICE",
    "android.permission.SYSTEM_ALERT_WINDOW",
    "android.permission.USE_BIOMETRIC",
    "android.permission.USE_FINGERPRINT",
]


TEXT_EXTENSIONS = {
    ".java", ".kt", ".xml", ".json", ".properties", ".txt", ".smali",
    ".cfg", ".conf", ".ini", ".yml", ".yaml", ".html", ".js", ".c", ".cpp", ".h",
}


# ----------------------------------------------------------------------
# Estruturas de dados
# ----------------------------------------------------------------------

@dataclass
class Indicator:
    apk: str
    package: str
    sha256: str
    severity: str
    score: int
    category: str
    pattern_id: str
    source: str
    match: str
    description: str


@dataclass
class ApkSummary:
    apk: str
    package: str
    sha256: str
    size_mb: float
    confidence: str
    score: int
    high_hits: int
    medium_hits: int
    low_hits: int
    explicit_mad_hits: int
    permission_hits: str
    notes: str


# ----------------------------------------------------------------------
# Utilitários
# ----------------------------------------------------------------------

def which_any(names: Iterable[str]) -> Optional[str]:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or f"Timeout after {timeout}s"
    except Exception as exc:
        return 1, "", str(exc)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except Exception:
        return str(path)


def extract_ascii_strings(blob: bytes, min_len: int = 5) -> list[str]:
    pattern = rb"[ -~]{" + str(min_len).encode() + rb",}"
    return [m.decode("utf-8", errors="replace") for m in re.findall(pattern, blob)]


def extract_utf16le_strings(blob: bytes, min_len: int = 5) -> list[str]:
    # Sequências do tipo A\x00B\x00C\x00...
    pattern = rb"(?:[ -~]\x00){" + str(min_len).encode() + rb",}"
    out = []
    for m in re.findall(pattern, blob):
        try:
            out.append(m.decode("utf-16le", errors="replace"))
        except Exception:
            pass
    return out


def snippet(text: str, max_len: int = 180) -> str:
    text = text.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def confidence_from_score(score: int, explicit_hits: int, high_hits: int, medium_hits: int, low_hits: int) -> str:
    if explicit_hits > 0 or high_hits > 0 or score >= 100:
        return "ALTA"
    if score >= 45 or medium_hits >= 2:
        return "MEDIA"
    if score >= 15 or low_hits >= 3:
        return "BAIXA_RASP_OU_ANTIFRAUDE"
    return "SEM_PISTA_FORTE"


# ----------------------------------------------------------------------
# Scanner
# ----------------------------------------------------------------------

class MadApkScanner:
    def __init__(
        self,
        out_dir: Path,
        jadx_mode: str,
        apktool_mode: str,
        max_decompile_mb: int,
        max_member_mb: int,
        jadx_timeout: int,
        apktool_timeout: int,
        keep_work: bool,
    ) -> None:
        self.out_dir = out_dir
        self.jadx_mode = jadx_mode
        self.apktool_mode = apktool_mode
        self.max_decompile_mb = max_decompile_mb
        self.max_member_mb = max_member_mb
        self.jadx_timeout = jadx_timeout
        self.apktool_timeout = apktool_timeout
        self.keep_work = keep_work

        self.tools = {
            "jadx": which_any(["jadx", "jadx.bat"]),
            "unzip": which_any(["unzip", "unzip.exe"]),
            "apktool": which_any(["apktool", "apktool.bat"]),
            "aapt": which_any(["aapt", "aapt2", "aapt.exe", "aapt2.exe"]),
        }

        self.patterns = []
        for item in INDICATOR_PATTERNS:
            compiled = dict(item)
            compiled["compiled"] = re.compile(item["regex"], re.IGNORECASE)
            self.patterns.append(compiled)

        self.all_indicators: list[Indicator] = []
        self.summaries: list[ApkSummary] = []

    def scan_text(
        self,
        apk_path: Path,
        package: str,
        sha256: str,
        source: str,
        text: str,
        indicators: list[Indicator],
        per_pattern_limit: int = 3,
    ) -> None:
        for pat in self.patterns:
            count = 0
            for m in pat["compiled"].finditer(text):
                if count >= per_pattern_limit:
                    break
                indicators.append(
                    Indicator(
                        apk=str(apk_path),
                        package=package,
                        sha256=sha256,
                        severity=pat["severity"],
                        score=int(pat["score"]),
                        category=pat["category"],
                        pattern_id=pat["id"],
                        source=source,
                        match=snippet(m.group(0)),
                        description=pat["description"],
                    )
                )
                count += 1

    def scan_blob_strings(
        self,
        apk_path: Path,
        package: str,
        sha256: str,
        source: str,
        blob: bytes,
        indicators: list[Indicator],
    ) -> None:
        strings = extract_ascii_strings(blob) + extract_utf16le_strings(blob)

        # Limita para evitar explosão em APKs enormes/ofuscados.
        # Ainda assim preserva boa cobertura de strings úteis.
        if len(strings) > 200_000:
            strings = strings[:200_000]

        for s in strings:
            self.scan_text(
                apk_path=apk_path,
                package=package,
                sha256=sha256,
                source=source,
                text=s,
                indicators=indicators,
                per_pattern_limit=1,
            )

    def parse_package_with_aapt(self, apk_path: Path) -> tuple[str, str]:
        aapt = self.tools.get("aapt")
        if not aapt:
            return "", ""

        rc, out, err = run_cmd([aapt, "dump", "badging", str(apk_path)], timeout=60)
        package = ""
        badging = out + "\n" + err

        m = re.search(r"package:\s+name='([^']+)'", badging)
        if m:
            package = m.group(1)

        return package, badging

    def permissions_with_aapt(self, apk_path: Path) -> str:
        aapt = self.tools.get("aapt")
        if not aapt:
            return ""

        rc, out, err = run_cmd([aapt, "dump", "permissions", str(apk_path)], timeout=60)
        return out + "\n" + err

    def scan_zip(self, apk_path: Path, package: str, sha256: str, indicators: list[Indicator]) -> list[str]:
        permission_hits = []

        # unzip -l, se existir.
        unzip = self.tools.get("unzip")
        if unzip:
            rc, out, err = run_cmd([unzip, "-l", str(apk_path)], timeout=60)
            self.scan_text(apk_path, package, sha256, "unzip:list", out + "\n" + err, indicators)

        try:
            with zipfile.ZipFile(apk_path, "r") as zf:
                for info in zf.infolist():
                    name = info.filename
                    self.scan_text(apk_path, package, sha256, f"zip:name:{name}", name, indicators)

                    # Permissões podem aparecer na string pool do manifest binário.
                    for perm in PERMISSION_PATTERNS:
                        if perm.lower() in name.lower() and perm not in permission_hits:
                            permission_hits.append(perm)

                    if info.is_dir():
                        continue

                    if info.file_size > self.max_member_mb * 1024 * 1024:
                        continue

                    try:
                        blob = zf.read(info)
                    except Exception:
                        continue

                    # Procura permissões diretamente no blob.
                    lower_blob = blob.lower()
                    for perm in PERMISSION_PATTERNS:
                        if perm.lower().encode() in lower_blob and perm not in permission_hits:
                            permission_hits.append(perm)

                    # Escaneia strings de arquivos relevantes.
                    # Em APK ofuscado, classes.dex e libs .so são especialmente úteis.
                    ext = Path(name).suffix.lower()
                    relevant = (
                        name.endswith(".dex")
                        or name.endswith(".so")
                        or name.endswith(".xml")
                        or name.endswith(".json")
                        or name.startswith("assets/")
                        or name.startswith("res/")
                        or name == "AndroidManifest.xml"
                        or ext in TEXT_EXTENSIONS
                    )

                    if relevant:
                        self.scan_blob_strings(
                            apk_path=apk_path,
                            package=package,
                            sha256=sha256,
                            source=f"zip:strings:{name}",
                            blob=blob,
                            indicators=indicators,
                        )

        except zipfile.BadZipFile:
            indicators.append(
                Indicator(
                    apk=str(apk_path),
                    package=package,
                    sha256=sha256,
                    severity="LOW",
                    score=0,
                    category="error",
                    pattern_id="bad_zip",
                    source="zip",
                    match="APK inválido ou ZIP corrompido",
                    description="Não foi possível abrir o APK como ZIP.",
                )
            )

        return permission_hits

    def scan_decompiled_dir(
        self,
        apk_path: Path,
        package: str,
        sha256: str,
        decompiled_dir: Path,
        source_prefix: str,
        indicators: list[Indicator],
    ) -> None:
        for root, _, files in os.walk(decompiled_dir):
            root_path = Path(root)
            for fname in files:
                fpath = root_path / fname
                ext = fpath.suffix.lower()

                if ext not in TEXT_EXTENSIONS:
                    continue

                try:
                    if fpath.stat().st_size > 3 * 1024 * 1024:
                        continue
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                rel = safe_rel(fpath, decompiled_dir)
                self.scan_text(
                    apk_path=apk_path,
                    package=package,
                    sha256=sha256,
                    source=f"{source_prefix}:{rel}",
                    text=text,
                    indicators=indicators,
                    per_pattern_limit=5,
                )

    def run_jadx(self, apk_path: Path, package: str, sha256: str, work_dir: Path, indicators: list[Indicator]) -> str:
        jadx = self.tools.get("jadx")
        if self.jadx_mode == "never":
            return "jadx desativado"
        if not jadx:
            return "jadx não encontrado"
        if self.jadx_mode == "auto" and apk_path.stat().st_size > self.max_decompile_mb * 1024 * 1024:
            return f"jadx ignorado: APK > {self.max_decompile_mb} MB"

        out_dir = work_dir / "jadx"
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd_candidates = [
            [jadx, "-q", "--show-bad-code", "--no-imports", "-d", str(out_dir), str(apk_path)],
            [jadx, "-q", "-d", str(out_dir), str(apk_path)],
        ]

        last_msg = ""
        for cmd in cmd_candidates:
            rc, out, err = run_cmd(cmd, timeout=self.jadx_timeout)
            last_msg = f"jadx rc={rc}; {snippet((out + ' ' + err).strip(), 300)}"
            if rc == 0:
                self.scan_decompiled_dir(apk_path, package, sha256, out_dir, "jadx", indicators)
                return last_msg

        return last_msg

    def run_apktool(self, apk_path: Path, package: str, sha256: str, work_dir: Path, indicators: list[Indicator]) -> str:
        apktool = self.tools.get("apktool")
        if self.apktool_mode == "never":
            return "apktool desativado"
        if not apktool:
            return "apktool não encontrado"
        if self.apktool_mode == "auto" and apk_path.stat().st_size > self.max_decompile_mb * 1024 * 1024:
            return f"apktool ignorado: APK > {self.max_decompile_mb} MB"

        out_dir = work_dir / "apktool"
        cmd = [apktool, "d", "-f", "-q", "-o", str(out_dir), str(apk_path)]
        rc, out, err = run_cmd(cmd, timeout=self.apktool_timeout)
        msg = f"apktool rc={rc}; {snippet((out + ' ' + err).strip(), 300)}"

        if rc == 0:
            self.scan_decompiled_dir(apk_path, package, sha256, out_dir, "apktool", indicators)

        return msg

    def dedupe_indicators(self, indicators: list[Indicator]) -> list[Indicator]:
        seen = set()
        out = []
        for ind in indicators:
            key = (
                ind.apk,
                ind.pattern_id,
                ind.category,
                ind.source,
                ind.match.lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(ind)
        return out

    def scan_apk(self, apk_path: Path) -> None:
        apk_path = apk_path.resolve()
        print(f"[+] Analisando: {apk_path}")

        sha = sha256_file(apk_path)
        size_mb = round(apk_path.stat().st_size / (1024 * 1024), 2)
        package, badging = self.parse_package_with_aapt(apk_path)

        indicators: list[Indicator] = []
        notes = []

        if badging:
            self.scan_text(apk_path, package, sha, "aapt:badging", badging, indicators)

        aapt_perms = self.permissions_with_aapt(apk_path)
        permission_hits = []
        if aapt_perms:
            self.scan_text(apk_path, package, sha, "aapt:permissions", aapt_perms, indicators)
            for perm in PERMISSION_PATTERNS:
                if perm in aapt_perms and perm not in permission_hits:
                    permission_hits.append(perm)

        zip_permission_hits = self.scan_zip(apk_path, package, sha, indicators)
        for perm in zip_permission_hits:
            if perm not in permission_hits:
                permission_hits.append(perm)

        work_parent = self.out_dir / "_work"
        work_parent.mkdir(parents=True, exist_ok=True)

        if self.keep_work:
            work_dir = work_parent / f"{apk_path.stem}_{sha[:12]}"
            work_dir.mkdir(parents=True, exist_ok=True)
            cleanup_tmp = False
        else:
            tmp = tempfile.TemporaryDirectory(prefix=f"madscan_{apk_path.stem}_", dir=str(work_parent))
            work_dir = Path(tmp.name)
            cleanup_tmp = True

        try:
            notes.append(self.run_jadx(apk_path, package, sha, work_dir, indicators))
            notes.append(self.run_apktool(apk_path, package, sha, work_dir, indicators))
        finally:
            if cleanup_tmp:
                try:
                    tmp.cleanup()
                except Exception:
                    pass

        indicators = self.dedupe_indicators(indicators)

        score = sum(ind.score for ind in indicators if ind.score > 0)
        high_hits = sum(1 for ind in indicators if ind.severity == "HIGH")
        medium_hits = sum(1 for ind in indicators if ind.severity == "MEDIUM")
        low_hits = sum(1 for ind in indicators if ind.severity == "LOW")
        explicit_hits = sum(1 for ind in indicators if ind.category == "explicit_mad")

        confidence = confidence_from_score(score, explicit_hits, high_hits, medium_hits, low_hits)

        summary = ApkSummary(
            apk=str(apk_path),
            package=package,
            sha256=sha,
            size_mb=size_mb,
            confidence=confidence,
            score=score,
            high_hits=high_hits,
            medium_hits=medium_hits,
            low_hits=low_hits,
            explicit_mad_hits=explicit_hits,
            permission_hits=";".join(permission_hits),
            notes=" | ".join(n for n in notes if n),
        )

        self.summaries.append(summary)
        self.all_indicators.extend(indicators)

        print(
            f"    -> {confidence} | score={score} | "
            f"H={high_hits} M={medium_hits} L={low_hits} | pkg={package or '-'}"
        )

    def write_reports(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)

        summary_path = self.out_dir / "summary.tsv"
        indicators_path = self.out_dir / "indicators.tsv"
        json_path = self.out_dir / "report.json"

        with summary_path.open("w", newline="", encoding="utf-8") as f:
            fieldnames = list(asdict(self.summaries[0]).keys()) if self.summaries else [
                "apk", "package", "sha256", "size_mb", "confidence", "score",
                "high_hits", "medium_hits", "low_hits", "explicit_mad_hits",
                "permission_hits", "notes",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            for row in self.summaries:
                writer.writerow(asdict(row))

        with indicators_path.open("w", newline="", encoding="utf-8") as f:
            fieldnames = list(asdict(self.all_indicators[0]).keys()) if self.all_indicators else [
                "apk", "package", "sha256", "severity", "score", "category",
                "pattern_id", "source", "match", "description",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            for row in self.all_indicators:
                writer.writerow(asdict(row))

        with json_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "tools": self.tools,
                    "summaries": [asdict(x) for x in self.summaries],
                    "indicators": [asdict(x) for x in self.all_indicators],
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        print()
        print(f"[+] Relatórios gerados:")
        print(f"    {summary_path}")
        print(f"    {indicators_path}")
        print(f"    {json_path}")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def find_apks(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.apk") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Procura pistas de MAD / Mobile Application Defense em APKs."
    )
    parser.add_argument("path", help="Pasta raiz contendo APKs.")
    parser.add_argument("--out", default="mad_scan_results", help="Diretório de saída.")
    parser.add_argument(
        "--jadx",
        choices=["auto", "always", "never"],
        default="auto",
        help="Usar jadx para decompilar. auto usa se disponível e APK <= limite.",
    )
    parser.add_argument(
        "--apktool",
        choices=["auto", "always", "never"],
        default="auto",
        help="Usar apktool para decodificar recursos/manifest. auto usa se disponível e APK <= limite.",
    )
    parser.add_argument(
        "--max-decompile-mb",
        type=int,
        default=200,
        help="Tamanho máximo do APK para decompilar em modo auto.",
    )
    parser.add_argument(
        "--max-member-mb",
        type=int,
        default=80,
        help="Tamanho máximo de arquivo interno do APK para extração de strings.",
    )
    parser.add_argument(
        "--jadx-timeout",
        type=int,
        default=420,
        help="Timeout por APK para jadx, em segundos.",
    )
    parser.add_argument(
        "--apktool-timeout",
        type=int,
        default=300,
        help="Timeout por APK para apktool, em segundos.",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Mantém diretórios decompilados em mad_scan_results/_work.",
    )

    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists() or not root.is_dir():
        print(f"[!] Pasta inválida: {root}", file=sys.stderr)
        return 2

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    scanner = MadApkScanner(
        out_dir=out_dir,
        jadx_mode=args.jadx,
        apktool_mode=args.apktool,
        max_decompile_mb=args.max_decompile_mb,
        max_member_mb=args.max_member_mb,
        jadx_timeout=args.jadx_timeout,
        apktool_timeout=args.apktool_timeout,
        keep_work=args.keep_work,
    )

    print("[*] Ferramentas detectadas:")
    for name, path in scanner.tools.items():
        print(f"    {name}: {path or 'não encontrado'}")

    apks = find_apks(root)
    print(f"\n[*] APKs encontrados: {len(apks)}\n")

    if not apks:
        return 0

    for apk in apks:
        try:
            scanner.scan_apk(apk)
        except KeyboardInterrupt:
            print("\n[!] Interrompido pelo usuário.")
            break
        except Exception as exc:
            print(f"[!] Erro analisando {apk}: {exc}", file=sys.stderr)

    scanner.write_reports()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
