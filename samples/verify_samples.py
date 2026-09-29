#!/usr/bin/env python3
"""
Prüft die synthetischen Beispieldateien gegen die Parser dieses Repos – offline,
ohne pdf.co und ohne Supabase.

- Belege: Text der PDF (pypdf, Layout-Modus) als Ersatz für die pdf.co-Textausgabe
  -> receipt_parser.parse_receipt() -> Vergleich mit manifest.json
- Leistungsabrechnungen: pdf.co-Fixtures aus abrechnungen/
  -> parser.parse_settlement_with_text() -> Vergleich mit manifest.json
- Versichererbrief: muss als Nicht-Abrechnung erkannt werden
- Scans: dürfen keine Textebene haben (wie echte Handy-Scans)

Beide Parser lesen pdf.co-Ergebnisse aus ihrem Cache (Dateiname = Hash der PDF).
Das Skript legt die Fixtures in einem temporären Cache ab, daher kein Netzaufruf.

Aufruf:  python samples/verify_samples.py [--strict]
Exit 1, wenn Abrechnungen, Brief oder Scans abweichen; mit --strict auch bei Belegen.
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

for var in ("PDFCO_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.pop(var, None)
os.environ["INSURED_PERSONS"] = "Jonas,Miriam,Mila,Ben,Helga"

import parser as settlement_parser  # noqa: E402  (parser.py dieses Repos)
import receipt_parser  # noqa: E402
from pypdf import PdfReader  # noqa: E402


def file_hash(path: Path, algo: str) -> str:
    return hashlib.new(algo, path.read_bytes()).hexdigest()


def plant(cache: Path, key: str, kind: str, text: str):
    (cache / f"{key}_{kind}.txt").write_text(text, encoding="utf-8")


def mark(ok: bool) -> str:
    return "ok " if ok else "XX "


def check_receipts(manifest, cache) -> tuple[int, int, list[str]]:
    fields = ["receipt_type", "invoice_amount", "invoice_date", "insured_person",
              "invoice_number", "provider"]
    hits = {f: 0 for f in fields}
    counted = {f: 0 for f in fields}
    lines, details = [], []
    for exp in manifest["receipts"]:
        pdf = HERE / exp["file"]
        text = "\n".join(p.extract_text(extraction_mode="layout") for p in PdfReader(pdf).pages[:1])
        plant(cache, file_hash(pdf, "sha256"), "receipt_text", text)
        got = receipt_parser.parse_receipt(str(pdf))
        wanted = [n.lower() for n in (exp["provider_name"], exp["payment_recipient"]) if n]
        res = {
            "receipt_type": got.receipt_type == exp["receipt_type"],
            "invoice_amount": got.invoice_amount is not None
                              and abs(got.invoice_amount - exp["invoice_amount"]) < 0.005,
            "invoice_date": got.invoice_date == exp["invoice_date"],
            "insured_person": (got.insured_person or "").strip() == exp["insured_person"],
            "invoice_number": None if exp["invoice_number"] is None
                              else got.invoice_number == exp["invoice_number"],
            "provider": any(w in (got.provider_name or "").lower() for w in wanted),
        }
        row = []
        for f in fields:
            if res[f] is None:
                row.append(" - ")
                continue
            counted[f] += 1
            hits[f] += res[f]
            row.append(mark(res[f]))
            if not res[f]:
                value = {"provider": got.provider_name}.get(f, getattr(got, f, None))
                expected = exp.get(f, exp["provider_name"])
                details.append(f"  {Path(exp['file']).name}: {f} = {value!r}, Soll {expected!r}")
        lines.append(" ".join(row) + " " + Path(exp["file"]).name)
    print("Belege (regelbasierter Parser, receipt_parser.py)")
    print("Typ Btr Dat Per Nr  Anb Datei")
    print("\n".join(lines))
    print("Treffer je Feld: " + ", ".join(f"{f} {hits[f]}/{counted[f]}" for f in fields))
    if details:
        print("Abweichungen:")
        print("\n".join(details))
    person, provider = receipt_parser.parse_filename(Path(manifest["receipts"][0]["file"]).name)
    print(f"Dateiname-Parser: {Path(manifest['receipts'][0]['file']).name} -> "
          f"Person {person!r}, Anbieter {provider!r}")
    total = sum(counted.values())
    return sum(hits.values()), total, details


def check_settlements(manifest, cache) -> list[str]:
    errors = []
    print("\nLeistungsabrechnungen (parser.py, pdf.co-Fixtures)")
    for exp in manifest["settlements"]:
        pdf = HERE / exp["file"]
        key = file_hash(pdf, "md5")
        plant(cache, key, "header", (HERE / exp["pdfco_header_fixture"]).read_text("utf-8"))
        plant(cache, key, "csv", (HERE / exp["pdfco_csv_fixture"]).read_text("utf-8"))
        with contextlib.redirect_stdout(io.StringIO()):
            got, _ = settlement_parser.parse_settlement_with_text(str(pdf))
        errs = []
        for f in ("settlement_number", "settlement_date", "insurance_number"):
            if getattr(got, f) != exp[f]:
                errs.append(f"{f} = {getattr(got, f)!r}, Soll {exp[f]!r}")
        for f in ("total_invoiced", "total_reimbursed"):
            if abs((getattr(got, f) or 0) - exp[f]) >= 0.005:
                errs.append(f"{f} = {getattr(got, f)!r}, Soll {exp[f]!r}")
        if len(got.items) != len(exp["items"]):
            errs.append(f"{len(got.items)} Positionen, Soll {len(exp['items'])}")
        notes_exp = notes_codes = notes_texts = 0
        for gi, ei in zip(got.items, exp["items"]):
            notes_exp += len(ei["notes"])
            codes = [n.split(":")[0] for n in gi.notes]
            notes_codes += sum(1 for n in ei["notes"] if n.split(":")[0] in codes)
            notes_texts += sum(1 for n in gi.notes if len(n.split(":", 1)[-1].strip()) > 3)
            for f in ("receipt_number", "insured_person", "insured_birthdate"):
                if getattr(gi, f) != ei[f]:
                    errs.append(f"{ei['receipt_number']} {f} = {getattr(gi, f)!r}, Soll {ei[f]!r}")
            for f in ("invoice_amount", "receipt_portion", "reimbursable_amount",
                      "reimbursed_amount"):
                if abs((getattr(gi, f) or 0) - ei[f]) >= 0.005:
                    errs.append(f"{ei['receipt_number']} {f} = {getattr(gi, f)!r}, Soll {ei[f]!r}")
        print(f"{mark(not errs)}{exp['settlement_number']}: {len(got.items)} Positionen, "
              f"erstattet {got.total_reimbursed:.2f} EUR, Hinweis-Codes {notes_codes}/{notes_exp}, "
              f"Hinweis-Texte {notes_texts}/{notes_exp}")
        errors += [f"  {exp['settlement_number']}: {e}" for e in errs]
    for exp in manifest["other_documents"]:
        pdf = HERE / exp["file"]
        plant(cache, file_hash(pdf, "md5"), "header",
              (HERE / exp["pdfco_header_fixture"]).read_text("utf-8"))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                settlement_parser.parse_settlement_with_text(str(pdf))
            errors.append(f"  {pdf.name}: als Abrechnung geparst, Soll {exp['expected_doc_type']}")
            ok = False
        except settlement_parser.NotASettlementError as e:
            ok = e.doc_type == exp["expected_doc_type"]
            if not ok:
                errors.append(f"  {pdf.name}: {e.doc_type}, Soll {exp['expected_doc_type']}")
        print(f"{mark(ok)}{pdf.name}: als Nicht-Abrechnung erkannt ({exp['expected_doc_type']})")
    return errors


def check_scans(manifest) -> list[str]:
    errors = []
    scans = [HERE / r["scan_file"] for r in manifest["receipts"] if r["scan_file"]]
    for scan in scans:
        text = "".join(p.extract_text() or "" for p in PdfReader(scan).pages).strip()
        if text:
            errors.append(f"  {scan.name}: Scan hat eine Textebene ({len(text)} Zeichen)")
    print(f"\n{mark(not errors)}Scans ohne Textebene: {len(scans) - len(errors)}/{len(scans)}")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="auch bei Beleg-Abweichungen scheitern")
    args = ap.parse_args()
    manifest = json.loads((HERE / "manifest.json").read_text("utf-8"))
    with tempfile.TemporaryDirectory(prefix="pkv-samples-cache-") as tmp:
        cache = Path(tmp)
        receipt_parser.CACHE_DIR = cache
        settlement_parser.CACHE_DIR = cache
        hits, total, receipt_diffs = check_receipts(manifest, cache)
        errors = check_settlements(manifest, cache)
    errors += check_scans(manifest)
    if errors:
        print("\nFehler:")
        print("\n".join(errors))
    print(f"\nBelege: {hits}/{total} Felder getroffen. "
          f"Abrechnungen/Brief/Scans: {'ok' if not errors else f'{len(errors)} Fehler'}.")
    sys.exit(1 if errors or (args.strict and receipt_diffs) else 0)


if __name__ == "__main__":
    main()
