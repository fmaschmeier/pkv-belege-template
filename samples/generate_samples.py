#!/usr/bin/env python3
"""
Synthetische Beispielbelege für den PKV-Belegprozess.

Erzeugt einen frei erfundenen Datensatz, der strukturell echten Einreichungen
entspricht, ohne echte Personen, Praxen, Beträge oder Bankverbindungen zu
enthalten:

  belege/        21 Belege mit Textebene (Arzt, Zahnarzt, Labor, Psychotherapie,
                 Klinik, Heilmittel, Apotheke, Pflege, Hilfsmittel)
  scans/         dieselben Belege als reine Bild-PDFs, wie ein Handy-Scan
                 (Eingabe für den Claude-Vision-Weg)
  abrechnungen/  drei Leistungsabrechnungen des (erfundenen) Versicherers, die
                 genau diese Belege erstatten, dazu ein Versichererbrief.
                 Je Abrechnung zwei Fixtures im Format der pdf.co-Ausgabe
                 (*.pdfco-header.txt, *.pdfco.csv), damit parser.py offline läuft.
  manifest.json  Soll-Werte je Dokument (Testorakel für beide Parser)

Aufruf:        python generate_samples.py [--no-scans]
Voraussetzung: pip install -r requirements.txt

Alle Beträge sind nachgerechnet: GOÄ-Punktwert 5,82873 Cent, GOZ-Punktwert
5,62421 Cent, Einzelbetrag = Punkte x Punktwert x Faktor, kaufmännisch gerundet.
Die IBANs sind prüfsummengültig, tragen aber die nicht vergebene Bankleitzahl
000 000 00 – eine Überweisung kann kein echtes Konto erreichen.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas as rl_canvas

HERE = Path(__file__).resolve().parent
DIR_BELEGE = HERE / "belege"
DIR_SCANS = HERE / "scans"
DIR_ABR = HERE / "abrechnungen"

D = Decimal
CENT = D("0.01")
PW_GOAE = D("0.0582873")
PW_GOZ = D("0.0562421")

INK = Color(0.1, 0.1, 0.12)
GREY = Color(0.45, 0.45, 0.48)
LIGHT = Color(0.8, 0.8, 0.82)
PEN = Color(0.12, 0.22, 0.62)   # "Kugelschreiber" für ausgefüllte Formularfelder

DISCLAIMER = ("Synthetisches Beispieldokument – Personen, Praxen, Beträge und "
              "Bankverbindungen sind frei erfunden.")

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


# --------------------------------------------------------------------------
# Formatierung
# --------------------------------------------------------------------------

def q(x) -> Decimal:
    return D(x).quantize(CENT, rounding=ROUND_HALF_UP)


def money(x: Decimal) -> str:
    """1234.5 -> '1.234,50'"""
    s = f"{q(x):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def de(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def de_long(d: date) -> str:
    return f"{d.day}. {MONATE[d.month - 1]} {d.year}"


def period_short(a: date, b: date) -> str:
    """Zeitraum im Format der Leistungsabrechnung: 12.05.-19.05.2026"""
    return f"{a.strftime('%d.%m.')}-{b.strftime('%d.%m.%Y')}"


def hours(x: Decimal) -> str:
    return f"{x:.1f}".replace(".", ",")


# --------------------------------------------------------------------------
# Erfundene Welt
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Person:
    first: str
    last: str
    born: date
    salutation: str  # Anrede im Adressfeld

    @property
    def full(self) -> str:
        return f"{self.first} {self.last}"

    @property
    def adult(self) -> bool:
        return self.born.year < 2008


JONAS = Person("Jonas", "Beispiel", date(1980, 3, 14), "Herrn")
MIRIAM = Person("Miriam", "Beispiel", date(1983, 9, 22), "Frau")
MILA = Person("Mila", "Beispiel", date(2013, 6, 5), "")
BEN = Person("Ben", "Beispiel", date(2016, 11, 17), "")
HELGA = Person("Helga", "Beispiel", date(1942, 2, 2), "Frau")
HOME = ("Musterweg 7", "12345 Musterstadt")


@dataclass(frozen=True)
class Org:
    name: str
    subtitle: tuple[str, ...]
    street: str
    phone: str
    email: str
    iban: str
    tax: str = "Steuer-Nr. 123/456/78901"
    city: str = "12345 Musterstadt"

    @property
    def iban_spaced(self) -> str:
        return " ".join(self.iban[i:i + 4] for i in range(0, len(self.iban), 4))


def iban_de(account: int, blz: str = "00000000") -> str:
    """Prüfsummengültige deutsche IBAN. Die Bankleitzahl 000 000 00 ist nicht vergeben."""
    bban = blz + f"{account:010d}"
    check = 98 - int(bban + "131400") % 97
    return f"DE{check:02d}{bban}"


# Je Zahlungsempfänger eine eigene IBAN, damit der Zahlungsabgleich eindeutig bleibt
IBANS = [iban_de(4711000100 + i * 1111) for i in range(18)]
FAMILY_IBAN = iban_de(4711999900)

KINDERARZT = Org("Kinderarztpraxis Dr. med. Clara Sonnberg",
                 ("Fachärztin für Kinder- und Jugendmedizin",),
                 "Gartenstraße 4", "0123 4561-20", "praxis@sonnberg.example", IBANS[0])
HNO = Org("HNO-Praxis Dr. med. Felix Adler", ("Facharzt für Hals-Nasen-Ohrenheilkunde",),
          "Bahnhofstraße 18", "0123 4562-30", "info@hno-adler.example", IBANS[9])
PVS = Org("Privatärztliche Verrechnungsstelle Musterland GmbH",
          ("Abrechnung privatärztlicher Leistungen",),
          "Am Rechenzentrum 3", "0123 4500-0", "service@pvs-musterland.example", IBANS[1],
          tax="Amtsgericht Musterstadt HRB 0000")
HAUSARZT = Org("Hausarztpraxis am Lindenplatz",
               ("Dr. med. Tobias Reuter", "Facharzt für Allgemeinmedizin"),
               "Lindenplatz 9", "0123 4563-40", "praxis@lindenplatz.example", IBANS[2])
LABOR = Org("MVZ Labordiagnostik Musterstadt GmbH", ("Laboratoriumsmedizin · Mikrobiologie",),
            "Industriestraße 40", "0123 4564-0", "abrechnung@labor-musterstadt.example",
            IBANS[3], tax="Amtsgericht Musterstadt HRB 0001")
ZAHNARZT = Org("Zahnarztpraxis Dr. med. dent. Jan Petersen", ("Zahnheilkunde · Prophylaxe",),
               "Marktstraße 21", "0123 4565-50", "praxis@zahn-petersen.example", IBANS[16])
DENTABR = Org("DentAbrechnung Musterland GmbH", ("Factoring und Abrechnung für Zahnarztpraxen",),
              "Kanalweg 5", "0123 4566-0", "service@dentabrechnung.example", IBANS[7],
              tax="Amtsgericht Musterstadt HRB 0002")
PSYCHO = Org("Praxis für Psychotherapie Hanna Wiesner",
             ("Dipl.-Psych. Hanna Wiesner", "Psychologische Psychotherapeutin (Verhaltenstherapie)"),
             "Uferweg 2", "0123 4567-10", "kontakt@wiesner-psychotherapie.example", IBANS[5])
ERGO = Org("Praxis für Ergotherapie Lindner", ("Sabine Lindner, Ergotherapeutin",),
           "Schulstraße 11", "0123 4568-60", "info@ergo-lindner.example", IBANS[6])
OPTIK = Org("Optik am Markt GmbH", ("Augenoptikermeisterbetrieb",),
            "Markt 3", "0123 4569-70", "service@optik-am-markt.example", IBANS[4],
            tax="Amtsgericht Musterstadt HRB 0003")
AUGENARZT = Org("Augenarztpraxis Dr. med. Ines Brandt", ("Fachärztin für Augenheilkunde",),
                "Rosenstraße 14", "0123 4570-80", "praxis@augen-brandt.example", IBANS[8])
KLINIKUM = Org("Klinikum Musterstadt – Klinik für Kinderchirurgie",
               ("Chefarzt Prof. Dr. med. Lukas Haverkamp",),
               "Klinikallee 1", "0123 4000-0", "kinderchirurgie@klinikum-musterstadt.example",
               IBANS[10])
ABRDIENST = Org("Abrechnungsdienst Musterstadt GmbH", ("Abrechnung wahlärztlicher Leistungen",),
                "Klinikallee 1a", "0123 4001-0", "info@abrechnungsdienst.example", IBANS[11],
                tax="Amtsgericht Musterstadt HRB 0004")
APOTHEKE = Org("Linden-Apotheke", ("Inh. Apothekerin Katrin Vogt e.K.",),
               "Lindenplatz 2", "0123 4571-90", "info@linden-apotheke.example", IBANS[12])
FED = Org("Familienentlastender Dienst Musterstadt e.V.",
          ("Angebote zur Unterstützung im Alltag (anerkannt nach § 45a SGB XI)",),
          "Kirchgasse 6", "0123 4572-00", "abrechnung@fed-musterstadt.example", IBANS[13],
          tax="Vereinsregister Musterstadt VR 0000")
PFLEGEDIENST = Org("Pflegedienst Sonnenschein GmbH", ("Ambulante Pflege · Beratungsbesuche",),
                   "Sonnenstraße 30", "0123 4573-10", "buero@pflegedienst-sonnenschein.example",
                   IBANS[14], tax="Amtsgericht Musterstadt HRB 0005")
SANI = Org("Sanitätshaus Musterstadt GmbH", ("Reha-Technik · Orthopädietechnik",),
           "Gewerbering 8", "0123 4574-20", "info@sanitaetshaus-musterstadt.example", IBANS[15],
           tax="Amtsgericht Musterstadt HRB 0006")
VERSICHERER = Org("Beispiel Krankenversicherung a.G.", ("Leistungsservice",),
                  "Musterallee 1", "0123 9876-0", "leistung@beispiel-kv.example", IBANS[17],
                  tax="Amtsgericht Musterstadt HRB 0007")


# --------------------------------------------------------------------------
# Positionen
# --------------------------------------------------------------------------

@dataclass
class FeeLine:
    """Position nach GOÄ oder GOZ."""
    day: date
    code: str
    text: str
    points: int
    factor: Decimal
    count: int = 1
    schedule: str = "GOÄ"
    reason: str | None = None  # Begründung bei Überschreiten des Schwellenwerts

    @property
    def single(self) -> Decimal:
        pw = PW_GOZ if self.schedule == "GOZ" else PW_GOAE
        return q(D(self.points) * pw * self.factor)

    @property
    def amount(self) -> Decimal:
        return self.single * self.count

    def at_factor(self, factor: Decimal) -> Decimal:
        pw = PW_GOZ if self.schedule == "GOZ" else PW_GOAE
        return q(D(self.points) * pw * factor) * self.count


@dataclass
class PriceLine:
    day: date | None
    text: str
    qty: Decimal
    unit_price: Decimal
    unit: str = "x"
    pzn: str | None = None

    @property
    def amount(self) -> Decimal:
        return q(self.qty * self.unit_price)


@dataclass
class CareLine:
    """Einsatz der Ersatzpflegeperson (Verhinderungspflege)."""
    day: date
    start: str
    end: str
    hours: Decimal
    rate: Decimal

    @property
    def amount(self) -> Decimal:
        return q(self.hours * self.rate)


@dataclass
class Part:
    """Ein Tarifanteil eines Belegs in der Leistungsabrechnung."""
    tariff: str
    portion: Decimal | None = None    # None = ganzer Beleg
    rate: Decimal = D(1)
    corrected: Decimal | None = None
    deferred: Decimal | None = None
    deductible: bool = False           # tarifliche Selbstbeteiligung anwenden


@dataclass
class Receipt:
    key: str
    nnn: int
    tag: str
    person: Person
    kind: str               # fee | priced | pharmacy | care_form
    receipt_type: str       # arzt | rezept | pflege | hilfsmittel
    provider: Org
    invoice_date: date
    lines: list
    invoice_number: str | None = None
    payee: Org | None = None
    diagnosis: str | None = None
    due_days: int | None = 30   # None: keine ausdrückliche Fälligkeit auf dem Beleg
    title: str = "Rechnung"
    intro: list[str] = field(default_factory=list)
    outro: list[str] = field(default_factory=list)
    description: str = ""
    settlement_desc: str = ""
    parts: list[Part] = field(default_factory=list)
    notes: list[tuple[str, str]] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def amount(self) -> Decimal:
        return sum((ln.amount for ln in self.lines), D(0))

    @property
    def days(self) -> list[date]:
        """Leistungstage; bei Apothekenquittungen ohne Positionsdatum das Belegdatum."""
        return sorted({ln.day for ln in self.lines if ln.day}) or [self.invoice_date]

    @property
    def period(self) -> str | None:
        ds = self.days
        if not ds:
            return None
        return de(ds[0]) if ds[0] == ds[-1] else f"{de(ds[0])} - {de(ds[-1])}"

    @property
    def due_date(self) -> date | None:
        return self.invoice_date + timedelta(days=self.due_days) if self.due_days else None

    @property
    def recipient(self) -> Person:
        return self.person if self.person.adult else JONAS

    @property
    def filename(self) -> str:
        return f"{self.nnn}_{self.tag}_{self.amount:.2f}_{self.person.first}_PKVB.pdf"


def goae(day, code, text, points, factor="2.3", count=1, reason=None):
    return FeeLine(day, code, text, points, D(factor), count, "GOÄ", reason)


def goz(day, code, text, points, factor="2.3", count=1):
    return FeeLine(day, code, text, points, D(factor), count, "GOZ")


def d(s: str) -> date:
    dd, mm_, yy = s.split(".")
    return date(int(yy), int(mm_), int(dd))


# --------------------------------------------------------------------------
# Datensatz
# --------------------------------------------------------------------------

def build_receipts() -> list[Receipt]:
    R: list[Receipt] = []

    # ---- Einreichung 301 (Mai/Juni 2026) -> Leistungsabrechnung R/26/117 ----
    R.append(Receipt(
        "kinderarzt-mila", 301, "PVS-Kinderarzt", MILA, "fee", "arzt", KINDERARZT,
        d("02.06.2026"), payee=PVS, invoice_number="PV-26-081533",
        diagnosis="J03.9 Akute Tonsillitis, nicht näher bezeichnet",
        lines=[
            goae(d("12.05.2026"), "1", "Beratung, auch mittels Fernsprecher", 80),
            goae(d("12.05.2026"), "5", "Symptombezogene Untersuchung", 80),
            goae(d("19.05.2026"), "1", "Beratung, auch mittels Fernsprecher", 80),
            goae(d("19.05.2026"), "5", "Symptombezogene Untersuchung", 80),
            goae(d("19.05.2026"), "70", "Kurze Bescheinigung (Schulbescheinigung)", 40),
        ],
        settlement_desc="Dr. C. Sonnberg (PVS), Arztrechnung",
        parts=[Part("KA1")]))

    R.append(Receipt(
        "apotheke-mila", 301, "Apotheke", MILA, "pharmacy", "rezept", APOTHEKE,
        d("12.05.2026"), due_days=None, extra={"beleg": "0512-0137", "time": "16:42"},
        lines=[
            PriceLine(None, "Amoxicillin 250 mg/5 ml Trockensaft, 100 ml", D(1), D("14.82")),
            PriceLine(None, "Ibuprofen 4 % Kindersaft, 100 ml", D(1), D("5.49")),
        ],
        settlement_desc="Linden-Apotheke, Rezept/Quittung",
        parts=[Part("KA1")]))

    R.append(Receipt(
        "hno-ben", 301, "PVS-HNO", BEN, "fee", "arzt", HNO,
        d("15.06.2026"), payee=PVS, invoice_number="PV-26-084102",
        diagnosis="H65.9 Nichteitrige Otitis media, nicht näher bezeichnet",
        lines=[
            goae(d("20.05.2026"), "1", "Beratung, auch mittels Fernsprecher", 80, "3.5",
                 reason="Erhöhter Zeitaufwand: ängstliches Kind, Untersuchung nur mit "
                        "mehreren Unterbrechungen möglich."),
            goae(d("20.05.2026"), "6", "Vollständige Untersuchung des gesamten HNO-Bereichs", 100),
            goae(d("03.06.2026"), "1", "Beratung, auch mittels Fernsprecher", 80),
            goae(d("03.06.2026"), "6", "Vollständige Untersuchung des gesamten HNO-Bereichs", 100),
        ],
        settlement_desc="Dr. F. Adler (PVS), Arztrechnung",
        parts=[Part("KA1")],  # korrigierter Betrag wird unten aus Faktor 2,3 berechnet
        notes=[("156", "Der Steigerungssatz über dem Schwellenwert ist nicht ausreichend "
                       "begründet. Wir haben bis zum 2,3-fachen Satz erstattet.")]))

    R.append(Receipt(
        "hausarzt-jonas", 301, "Hausarzt", JONAS, "fee", "arzt", HAUSARZT,
        d("08.06.2026"), invoice_number="2026-0412",
        diagnosis="Z00.0 Allgemeine ärztliche Untersuchung",
        lines=[
            goae(d("26.05.2026"), "29", "Gesundheitsuntersuchung zur Früherkennung von "
                                        "Krankheiten bei einem Erwachsenen", 440),
            goae(d("26.05.2026"), "250", "Blutentnahme mittels Spritze oder Kanüle aus der Vene", 40),
            goae(d("26.05.2026"), "410", "Ultraschalluntersuchung eines Organs (Leber)", 200),
            goae(d("26.05.2026"), "420", "Ultraschalluntersuchung weiterer Organe "
                                         "(Gallenblase, Nieren), je Organ", 80, count=2),
            goae(d("02.06.2026"), "1", "Beratung (Befundbesprechung)", 80),
        ],
        settlement_desc="Dr. T. Reuter, Arztrechnung",
        parts=[Part("AMB1", deductible=True)]))

    R.append(Receipt(
        "labor-jonas", 301, "Labor", JONAS, "fee", "arzt", LABOR,
        d("04.06.2026"), invoice_number="L26-0087341", title="Rechnung für Laborleistungen",
        intro=["Einsender: Hausarztpraxis am Lindenplatz, Dr. med. Tobias Reuter"],
        lines=[
            goae(d("26.05.2026"), "3550", "Blutbild (kleines Blutbild)", 60, "1.15"),
            goae(d("26.05.2026"), "3560", "Glukose", 40, "1.15"),
            goae(d("26.05.2026"), "3562.H1", "Cholesterin gesamt", 40, "1.15"),
            goae(d("26.05.2026"), "3565.H1", "Triglyceride", 40, "1.15"),
            goae(d("26.05.2026"), "3585.H1", "Kreatinin", 40, "1.15"),
            goae(d("26.05.2026"), "4030", "Thyreoidea stimulierendes Hormon (TSH)", 250, "1.15"),
        ],
        settlement_desc="MVZ Labordiagnostik, Laborrechnung",
        parts=[Part("AMB1", deductible=True)],
        extra={"person_label": "Patient"}))

    R.append(Receipt(
        "zahnarzt-miriam", 301, "Zahnarzt", MIRIAM, "fee", "arzt", ZAHNARZT,
        d("16.06.2026"), payee=DENTABR, invoice_number="DA-26-55120", title="Liquidation",
        lines=[
            goae(d("09.06.2026"), "Ä1", "Beratung, auch mittels Fernsprecher", 80),
            goz(d("09.06.2026"), "0010", "Eingehende Untersuchung zur Feststellung von Zahn-, "
                                         "Mund- und Kiefererkrankungen", 100),
            goz(d("09.06.2026"), "1040", "Professionelle Zahnreinigung, je Zahn", 28, count=28),
        ],
        settlement_desc="Dr. J. Petersen (DentAbr.), Zahnarztrechnung",
        parts=[Part("ZE1"), Part("AMB1", deductible=True)]))  # GOZ- und GOÄ-Anteil, siehe settle()

    R.append(Receipt(
        "psychotherapie-miriam", 301, "Psychotherapie", MIRIAM, "fee", "arzt", PSYCHO,
        d("01.06.2026"), invoice_number="PT-2026-031",
        diagnosis="F43.2 Anpassungsstörung",
        intro=["Abrechnung nach der Gebührenordnung für Psychotherapeuten (GOP) "
               "in Verbindung mit der GOÄ"],
        lines=[goae(d(x), "870", "Verhaltenstherapie, Einzelbehandlung, Dauer mindestens "
                                 "50 Minuten", 750)
               for x in ("07.05.2026", "14.05.2026", "21.05.2026", "28.05.2026")],
        settlement_desc="H. Wiesner, Psychotherapie",
        parts=[Part("AMB1", rate=D("0.8"), deductible=True)],
        notes=[("402", "Psychotherapie erstatten wir tariflich zu 80 %. Im Kalenderjahr "
                       "bisher abgerechnete Sitzungen: 4 von 30.")]))

    R.append(Receipt(
        "ergotherapie-ben", 301, "Ergotherapie", BEN, "priced", "arzt", ERGO,
        d("18.06.2026"), invoice_number="ER-26-118", due_days=None,
        intro=["Ärztliche Verordnung vom 28.04.2026 (Kinderarztpraxis Dr. med. Clara Sonnberg)",
               "Heilmittel: Ergotherapie, sensomotorisch-perzeptive Behandlung, 45 Minuten"],
        outro=["Zahlbar innerhalb von 14 Tagen ohne Abzug.",
               "Heilmittelleistungen sind gemäß § 4 Nr. 14 UStG von der Umsatzsteuer befreit."],
        lines=[PriceLine(d("05.05.2026"), "Ergotherapeutische Befunderhebung", D(1), D("44.60"))] +
              [PriceLine(d(x), "Sensomotorisch-perzeptive Behandlung, Einzelbehandlung 45 Min.",
                         D(1), D("61.40"))
               for x in ("12.05.2026", "19.05.2026", "26.05.2026", "02.06.2026",
                         "09.06.2026", "16.06.2026")],
        extra={"number_label": "Rechnungsnummer", "total_label": "Gesamtbetrag"},
        settlement_desc="Ergotherapie Lindner, Heilmittel",
        parts=[Part("KA1", corrected=D("40.00") + 6 * D("52.50"))],
        notes=[("318", "Heilmittel erstatten wir bis zu den Höchstbeträgen des tariflichen "
                       "Heilmittelverzeichnisses.")]))

    R.append(Receipt(
        "optiker-mila", 301, "Optiker", MILA, "priced", "hilfsmittel", OPTIK,
        d("10.06.2026"), invoice_number="OM-26-3317", due_days=14,
        intro=["Brillenglasbestimmung vom 27.05.2026: R sph -1,25 cyl -0,50 A 180° / "
               "L sph -1,00"],
        outro=["Im Gesamtbetrag sind 19 % MwSt. enthalten: 45,18 €."],
        lines=[
            PriceLine(d("10.06.2026"), "Einstärkenglas Kunststoff 1,6, superentspiegelt, gehärtet",
                      D(2), D("89.50")),
            PriceLine(d("10.06.2026"), "Kinderfassung Titan flex, Modell Lotta 46-16", D(1),
                      D("104.00")),
        ],
        extra={"total_label": "Gesamtbetrag"},
        settlement_desc="Optik am Markt, Sehhilfe",
        parts=[Part("KA1", corrected=D("150.00"))],
        notes=[("210", "Für Sehhilfen erstatten wir tariflich bis zu 150,00 EUR innerhalb von "
                       "zwei Kalenderjahren.")]))

    # ---- Einreichung 302 (Juli 2026) -> Leistungsabrechnung R/26/129 ----
    R.append(Receipt(
        "augenarzt-jonas", 302, "Augenarzt", JONAS, "fee", "arzt", AUGENARZT,
        d("07.07.2026"), invoice_number="A-26-2291", diagnosis="H52.1 Myopie",
        lines=[
            goae(d("30.06.2026"), "1", "Beratung, auch mittels Fernsprecher", 80),
            goae(d("30.06.2026"), "6", "Vollständige Untersuchung aller Augenabschnitte", 100),
            goae(d("30.06.2026"), "1201", "Subjektive Refraktionsbestimmung mit "
                                          "sphärisch-zylindrischen Gläsern", 89),
            goae(d("30.06.2026"), "1240", "Spaltlampenmikroskopie der vorderen und mittleren "
                                          "Augenabschnitte", 74),
        ],
        settlement_desc="Dr. I. Brandt, Arztrechnung",
        parts=[Part("AMB1", deductible=True)]))

    R.append(Receipt(
        "klinikum-ben", 302, "Klinikum", BEN, "fee", "arzt", KLINIKUM,
        d("20.07.2026"), payee=ABRDIENST, invoice_number="KA-26-40771",
        title="Rechnung über wahlärztliche Leistungen (ambulant)",
        diagnosis="S63.5 Verstauchung und Zerrung des Handgelenkes",
        lines=[
            goae(d("04.07.2026"), "1", "Beratung, auch mittels Fernsprecher", 80),
            goae(d("04.07.2026"), "7", "Vollständige körperliche Untersuchung der Stütz- und "
                                       "Bewegungsorgane", 160),
            goae(d("04.07.2026"), "410", "Ultraschalluntersuchung (Handgelenk rechts)", 200),
            goae(d("04.07.2026"), "70", "Kurze Bescheinigung (Sportbefreiung)", 40),
        ],
        settlement_desc="Prof. Dr. L. Haverkamp (Abr.-Dienst), Klinik",
        parts=[Part("KA1")]))

    R.append(Receipt(
        "apotheke-jonas", 302, "Apotheke", JONAS, "pharmacy", "rezept", APOTHEKE,
        d("07.07.2026"), due_days=None, extra={"beleg": "0707-0211", "time": "09:15"},
        lines=[
            PriceLine(None, "Cetirizin 10 mg Filmtabletten, 50 St.", D(1), D("9.97")),
            PriceLine(None, "Mometason Nasenspray 50 µg/Sprühstoß, 18 g", D(1), D("21.36")),
        ],
        settlement_desc="Linden-Apotheke, Rezept/Quittung",
        parts=[Part("AMB1", rate=D("0.8"), deductible=True)],
        notes=[("312", "Arzneimittel erstatten wir tariflich zu 80 %.")]))

    R.append(Receipt(
        "apotheke-ben", 302, "Apotheke", BEN, "pharmacy", "rezept", APOTHEKE,
        d("04.07.2026"), due_days=None, extra={"beleg": "0704-0098", "time": "18:03"},
        lines=[
            PriceLine(None, "Ibuprofen 4 % Kindersaft, 100 ml", D(1), D("5.62")),
            PriceLine(None, "Kühlkompressen, wiederverwendbar, 2 St.", D(1), D("6.95")),
        ],
        settlement_desc="Linden-Apotheke, Rezept/Quittung",
        parts=[Part("KA1", corrected=D("5.62"))],
        notes=[("305", "Kühlkompressen sind als Mittel des täglichen Bedarfs nicht "
                       "erstattungsfähig.")]))

    R.append(Receipt(
        "kinderarzt-ben", 302, "PVS-Kinderarzt", BEN, "fee", "arzt", KINDERARZT,
        d("28.07.2026"), payee=PVS, invoice_number="PV-26-091266",
        diagnosis="Z00.1 Gesundheitsvorsorgeuntersuchung eines Kindes; "
                  "Z24.1 Impfung gegen FSME",
        lines=[
            goae(d("14.07.2026"), "26", "Untersuchung zur Früherkennung von Krankheiten bei "
                                        "einem Kind (U11)", 450),
            goae(d("14.07.2026"), "375", "Schutzimpfung (intramuskulär), FSME", 80),
        ],
        settlement_desc="Dr. C. Sonnberg (PVS), Arztrechnung",
        parts=[Part("KA1")]))

    R.append(Receipt(
        "apotheke-impfstoff-ben", 302, "Apotheke-Impfstoff", BEN, "pharmacy", "rezept",
        APOTHEKE, d("13.07.2026"), due_days=None, extra={"beleg": "0713-0164", "time": "11:27"},
        lines=[PriceLine(None, "FSME-Impfstoff für Kinder 0,25 ml, 1 Fertigspritze", D(1),
                         D("44.86"))],
        settlement_desc="Linden-Apotheke, Rezept/Quittung",
        parts=[Part("KA1")]))

    # ---- Einreichung 303 (Juli/August 2026, Pflege) -> Leistungsabrechnung R/26/134 ----
    rate_vp = D("17.50")
    R.append(Receipt(
        "vp-juli-helga", 303, "Verhinderungspflege", HELGA, "care_form", "pflege",
        Org("Erika Musterfrau", (), "Ahornweg 12", "", "", ""), d("06.07.2026"), due_days=None,
        extra={"signed": d("31.07.2026"), "reason": "sonstige",
               "span": (d("06.07.2026"), d("24.07.2026"))},
        lines=[CareLine(d("06.07.2026"), "09:00", "13:00", D("4.0"), rate_vp),
               CareLine(d("08.07.2026"), "14:00", "17:30", D("3.5"), rate_vp),
               CareLine(d("13.07.2026"), "09:00", "12:00", D("3.0"), rate_vp),
               CareLine(d("15.07.2026"), "14:00", "18:00", D("4.0"), rate_vp),
               CareLine(d("20.07.2026"), "09:00", "13:00", D("4.0"), rate_vp),
               CareLine(d("24.07.2026"), "10:00", "12:30", D("2.5"), rate_vp)],
        description="Verhinderungspflege §39 SGB XI",
        settlement_desc="E. Musterfrau, Verhinderungspflege",
        parts=[Part("PPV")]))

    R.append(Receipt(
        "vp-august-helga", 303, "Verhinderungspflege", HELGA, "care_form", "pflege",
        Org("Erika Musterfrau", (), "Ahornweg 12", "", "", ""), d("03.08.2026"), due_days=None,
        extra={"signed": d("28.08.2026"), "reason": "krankheit",
               "span": (d("03.08.2026"), d("24.08.2026"))},
        lines=[CareLine(d("03.08.2026"), "09:00", "12:00", D("3.0"), rate_vp),
               CareLine(d("10.08.2026"), "13:00", "17:00", D("4.0"), rate_vp),
               CareLine(d("17.08.2026"), "09:00", "12:30", D("3.5"), rate_vp),
               CareLine(d("24.08.2026"), "15:00", "17:30", D("2.5"), rate_vp)],
        description="Verhinderungspflege §39 SGB XI",
        settlement_desc="E. Musterfrau, Verhinderungspflege",
        parts=[Part("PPV")]))

    rate_fed = D("38.50")
    R.append(Receipt(
        "entlastung-juli-helga", 303, "Entlastung", HELGA, "priced", "pflege", FED,
        d("03.08.2026"), invoice_number="EL-26-00417", due_days=None,
        extra={"title_style": "number_in_title", "person_style": "betreute",
               "total_style": "insgesamt_euro", "unit_col": "Std.", "price_col": "Satz €"},
        intro=["Pflegeleistung nach § 45b SGB XI (Entlastungsbetrag)",
               "Leistungszeitraum: 01.07.2026 - 31.07.2026"],
        outro=["Wir rechnen auf Wunsch direkt mit Ihrer Pflegeversicherung ab. Andernfalls "
               "bitten wir um Überweisung innerhalb von 14 Tagen.",
               "Die Leistungen sind gemäß § 4 Nr. 16 UStG umsatzsteuerfrei."],
        lines=[PriceLine(d(x), "Betreuung und Begleitung im Alltag", D(h), rate_fed, "Std.")
               for x, h in (("02.07.2026", "1.5"), ("09.07.2026", "1.0"),
                            ("16.07.2026", "1.0"), ("30.07.2026", "1.0"))],
        description="Entlastungsleistungen §45b SGB XI",
        settlement_desc="Familienentl. Dienst, Entlastungsleistung",
        parts=[Part("PPV", deferred=D("42.25"))],
        notes=[("421", "Der Entlastungsbetrag beträgt 131,00 EUR monatlich. Den übersteigenden "
                       "Betrag haben wir zurückgestellt; er wird mit nicht verbrauchten Beträgen "
                       "des Kalenderjahres verrechnet.")]))

    R.append(Receipt(
        "entlastung-august-helga", 303, "Entlastung", HELGA, "priced", "pflege", FED,
        d("02.09.2026"), invoice_number="EL-26-00463", due_days=None,
        extra={"title_style": "number_in_title", "person_style": "betreute",
               "total_style": "insgesamt_euro", "unit_col": "Std.", "price_col": "Satz €"},
        intro=["Pflegeleistung nach § 45b SGB XI (Entlastungsbetrag)",
               "Leistungszeitraum: 01.08.2026 - 31.08.2026"],
        outro=["Wir rechnen auf Wunsch direkt mit Ihrer Pflegeversicherung ab. Andernfalls "
               "bitten wir um Überweisung innerhalb von 14 Tagen.",
               "Die Leistungen sind gemäß § 4 Nr. 16 UStG umsatzsteuerfrei."],
        lines=[PriceLine(d(x), "Betreuung und Begleitung im Alltag", D("1.0"), rate_fed, "Std.")
               for x in ("06.08.2026", "13.08.2026", "27.08.2026")],
        description="Entlastungsleistungen §45b SGB XI",
        settlement_desc="Familienentl. Dienst, Entlastungsleistung",
        parts=[Part("PPV")]))

    R.append(Receipt(
        "pflegeberatung-helga", 303, "Pflegeberatung", HELGA, "priced", "pflege", PFLEGEDIENST,
        d("18.08.2026"), invoice_number="PB-26-0311", due_days=None,
        extra={"title_style": "number_in_title", "total_label": "Gesamtbetrag"},
        intro=["Beratungseinsatz gemäß § 37 Abs. 3 SGB XI"],
        outro=["Der Nachweis über den Beratungseinsatz wurde an die Pflegeversicherung "
               "übermittelt.",
               "Die Leistung ist gemäß § 4 Nr. 16 UStG umsatzsteuerfrei."],
        lines=[PriceLine(d("17.08.2026"), "Beratungseinsatz Pflegegrad 3, Hausbesuch", D(1),
                         D("72.00"))],
        settlement_desc="Pflegedienst Sonnenschein, Beratungseinsatz",
        parts=[Part("PPV")]))

    R.append(Receipt(
        "sanitaetshaus-helga", 303, "Sanitaetshaus", HELGA, "priced", "hilfsmittel", SANI,
        d("14.08.2026"), invoice_number="SH-26-2207", due_days=None,
        extra={"title_style": "number_in_title", "total_label": "Gesamtbetrag"},
        intro=["Kostenzusage Ihrer Krankenversicherung vom 06.08.2026 liegt vor."],
        outro=["Preise inkl. gesetzlicher Mehrwertsteuer. Zahlbar innerhalb von 14 Tagen."],
        lines=[PriceLine(d("12.08.2026"), "Rollator Leichtgewicht, faltbar, mit Sitz, Korb und "
                                          "Stockhalter", D(1), D("179.90")),
               PriceLine(d("12.08.2026"), "Lieferung, Anpassung und Einweisung", D(1),
                         D("15.00"))],
        settlement_desc="Sanitätshaus Musterstadt, Hilfsmittel",
        parts=[Part("AMB2")]))

    return R


# --------------------------------------------------------------------------
# Zeichnen
# --------------------------------------------------------------------------

_WATERMARK: Image.Image | None = None


def watermark() -> Image.Image:
    """'MUSTER' als Bild, damit es nicht in die Textebene gerät."""
    global _WATERMARK
    if _WATERMARK is None:
        font = ImageFont.load_default(size=260)
        img = Image.new("RGBA", (1500, 360), (255, 255, 255, 0))
        ImageDraw.Draw(img).text((30, 20), "MUSTER", font=font, fill=(150, 150, 160, 34))
        _WATERMARK = img.rotate(32, expand=True, resample=Image.BICUBIC)
    return _WATERMARK


class Pg:
    """Zeichenhilfe mit Koordinaten in mm ab oben links."""

    def __init__(self, c: rl_canvas.Canvas, size):
        self.c = c
        self.w, self.h = size

    def Y(self, y):
        return self.h - y * mm

    def t(self, x, y, s, size=9, font="Helvetica", color=INK, align="l"):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        if align == "r":
            self.c.drawRightString(x * mm, self.Y(y), s)
        elif align == "c":
            self.c.drawCentredString(x * mm, self.Y(y), s)
        else:
            self.c.drawString(x * mm, self.Y(y), s)

    def wrap(self, x, y, s, width, size=9, font="Helvetica", color=INK, lead=None):
        lead = lead or size * 0.45
        for ln in simpleSplit(s, font, size, width * mm):
            self.t(x, y, ln, size, font, color)
            y += lead
        return y

    def hline(self, x1, x2, y, width=0.4, color=GREY):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.line(x1 * mm, self.Y(y), x2 * mm, self.Y(y))

    def box(self, x, y, w, h, width=0.5, color=GREY):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.rect(x * mm, self.Y(y + h), w * mm, h * mm, stroke=1, fill=0)

    def check(self, x, y, checked):
        self.box(x, y - 2.6, 3, 3, 0.5, INK)
        if checked:
            self.t(x + 0.55, y - 0.1, "X", 9, "Helvetica-Bold", PEN)

    def signature(self, x, y, w, seed):
        rnd = random.Random(seed)
        c = self.c
        c.setStrokeColor(PEN)
        c.setLineWidth(0.8)
        p = c.beginPath()
        px, py = x * mm, self.Y(y)
        p.moveTo(px, py)
        for _ in range(5):
            nx = px + w * mm / 5
            p.curveTo(px + rnd.uniform(2, 8), py + rnd.uniform(4, 10),
                      nx - rnd.uniform(2, 8), py - rnd.uniform(3, 9), nx, py + rnd.uniform(-2, 2))
            px = nx
        c.drawPath(p, stroke=1, fill=0)

    def watermark(self, width_mm):
        img = watermark()
        h_mm = width_mm * img.height / img.width
        self.c.drawImage(ImageReader(img), (self.w / mm - width_mm) / 2 * mm,
                         self.h / 2 - h_mm * mm / 2, width_mm * mm, h_mm * mm, mask="auto")

    def disclaimer(self, y=None):
        y = y if y is not None else self.h / mm - 5
        self.t(self.w / mm / 2, y, DISCLAIMER, 6.5, "Helvetica-Oblique", GREY, "c")


def letterhead(pg: Pg, org: Org, top=16):
    pg.t(190, top, org.name, 11, "Helvetica-Bold", align="r")
    y = top + 4.6
    for s in org.subtitle:
        pg.t(190, y, s, 8.5, align="r")
        y += 3.8
    pg.t(190, y, f"{org.street} · {org.city}", 8, color=GREY, align="r")
    pg.t(190, y + 3.6, f"Tel. {org.phone} · {org.email}", 8, color=GREY, align="r")


def address(pg: Pg, sender: Org, person: Person, y=48):
    pg.t(20, y, f"{sender.name} · {sender.street} · {sender.city}", 6.5, color=GREY)
    pg.hline(20, 105, y + 1, 0.3, LIGHT)
    lines = ([person.salutation] if person.salutation else []) + [person.full, *HOME]
    yy = y + 6
    for s in lines:
        pg.t(20, yy, s, 10)
        yy += 4.6


def info_block(pg: Pg, rows: list[tuple[str, str]], y=54):
    for label, value in rows:
        pg.t(125, y, label, 8.5, color=GREY)
        pg.t(190, y, value, 8.5, align="r")
        y += 4.4


def footer(pg: Pg, org: Org):
    y = 274
    pg.hline(20, 190, y - 4, 0.3, LIGHT)
    cols = [
        [org.name, org.street, org.city],
        ["Bankverbindung: Musterbank Musterstadt", f"IBAN: {org.iban_spaced}",
         "Verwendungszweck: Rechnungsnummer"],
        [f"Telefon: {org.phone}", f"E-Mail: {org.email}", org.tax],
    ]
    for i, col in enumerate(cols):
        for j, s in enumerate(col):
            pg.t(20 + i * 58, y + j * 3.4, s, 6.5, color=GREY)


def new_canvas(path: Path, size=A4) -> tuple[rl_canvas.Canvas, Pg]:
    c = rl_canvas.Canvas(str(path), pagesize=size, invariant=1)
    return c, Pg(c, size)


# ---- Rechnung nach GOÄ/GOZ ----

def render_fee(r: Receipt, path: Path):
    c, pg = new_canvas(path)
    head = r.payee or r.provider
    letterhead(pg, head)
    address(pg, head, r.recipient)
    rows = [("Rechnungs-Nr.:", r.invoice_number), ("Rechnungsdatum:", de(r.invoice_date)),
            ("Patienten-Nr.:", str(10000 + len(r.key) * 311))]
    info_block(pg, rows)

    y = 94
    pg.t(20, y, r.title, 13, "Helvetica-Bold")
    y += 7
    if r.payee:
        y = pg.wrap(20, y, f"Leistungserbringer: {r.provider.name}, {', '.join(r.provider.subtitle)}, "
                           f"{r.provider.street}, {r.provider.city}", 170, 8.5)
        pg.t(20, y, "Abrechnung im Auftrag und für Rechnung der behandelnden Praxis.", 8.5,
             color=GREY)
        y += 5
    label = r.extra.get("person_label", "Behandelte Person")
    pg.t(20, y, f"{label}: {r.person.full}, Geburtsdatum: {de(r.person.born)}", 9)
    y += 4.6
    for s in r.intro:
        y = pg.wrap(20, y, s, 170, 8.5)
    if r.diagnosis:
        pg.t(20, y, f"Diagnose: {r.diagnosis}", 9)
        y += 4.6
    days = r.days
    if len(days) > 1:
        pg.t(20, y, f"Behandlungszeitraum: {de(days[0])} - {de(days[-1])}", 9)
    else:
        pg.t(20, y, f"Behandlungstag: {de(days[0])}", 9)
    y += 8

    cols = [("Datum", 20, "l"), ("Nr.", 40, "l"), ("Leistung", 56, "l"), ("Punkte", 146, "r"),
            ("Faktor", 160, "r"), ("Anz.", 170, "r"), ("Betrag €", 190, "r")]
    for name, x, al in cols:
        pg.t(x, y, name, 8, "Helvetica-Bold", align=al)
    pg.hline(20, 190, y + 1.6)
    y += 6
    reasons = []
    for ln in r.lines:
        pg.t(20, y, de(ln.day), 8)
        pg.t(40, y, ln.code, 8)
        pg.t(146, y, str(ln.points), 8, align="r")
        pg.t(160, y, f"{ln.factor:.2f}".replace(".", ","), 8, align="r")
        pg.t(170, y, str(ln.count), 8, align="r")
        pg.t(190, y, money(ln.amount), 8, align="r")
        y = pg.wrap(56, y, ln.text + ("*" if ln.reason else ""), 76, 8, lead=3.7) + 1.2
        if ln.reason:
            reasons.append((ln, ln.reason))
    pg.hline(20, 190, y - 1.5)
    y += 3
    pg.t(190, y, f"Rechnungsbetrag: {money(r.amount)} €", 10, "Helvetica-Bold", align="r")
    y += 8
    for ln, why in reasons:
        f = f"{ln.factor:.1f}".replace(".", ",")
        y = pg.wrap(20, y, f"* Begründung zu Nr. {ln.code} (Faktor {f}): {why}", 170, 8,
                    "Helvetica-Oblique")
        y += 1.5
    if r.due_date:
        pg.t(20, y, f"Zahlbar bis: {de(r.due_date)}", 9, "Helvetica-Bold")
        y += 5
    payee = r.payee or r.provider
    y = pg.wrap(20, y, "Bitte überweisen Sie den Rechnungsbetrag unter Angabe der Rechnungsnummer "
                       f"auf das Konto von {payee.name} (IBAN {payee.iban_spaced}).", 170, 8.5)
    y += 1.5
    schedules = sorted({ln.schedule for ln in r.lines}, key=["GOÄ", "GOZ"].index)
    pw = {"GOÄ": "GOÄ-Punktwert 5,82873 Cent", "GOZ": "GOZ-Punktwert 5,62421 Cent"}
    pg.wrap(20, y, "Abrechnung nach " + " und ".join(schedules) + " (" +
            "; ".join(pw[s] for s in schedules) + "). Umsatzsteuerfrei gemäß § 4 Nr. 14 UStG.",
            170, 8, color=GREY)

    footer(pg, payee)
    pg.watermark(165)
    pg.disclaimer()
    c.showPage()
    c.save()


# ---- Rechnung mit Preisen (Heilmittel, Pflege, Hilfsmittel) ----

def render_priced(r: Receipt, path: Path):
    c, pg = new_canvas(path)
    letterhead(pg, r.provider)
    address(pg, r.provider, r.recipient)
    ex = r.extra
    rows = []
    if ex.get("title_style") != "number_in_title":
        rows.append((ex.get("number_label", "Rechnungs-Nr.") + ":", r.invoice_number))
        rows.append(("Rechnungsdatum:", de(r.invoice_date)))
    rows.append(("Kundennummer:", str(2000 + len(r.key) * 17)))
    info_block(pg, rows)

    y = 94
    if ex.get("title_style") == "number_in_title":
        pg.t(20, y, f"Rechnung {r.invoice_number} vom {de(r.invoice_date)}", 13, "Helvetica-Bold")
    else:
        pg.t(20, y, r.title, 13, "Helvetica-Bold")
    y += 7
    if ex.get("person_style") == "betreute":
        pg.t(20, y, f"Betreute: {r.person.last}, {r.person.first} geb. {de(r.person.born)}", 9)
    else:
        pg.t(20, y, f"für {r.person.full}, Geburtsdatum: {de(r.person.born)}", 9)
    y += 4.6
    for s in r.intro:
        y = pg.wrap(20, y, s, 170, 9)
    y += 4

    unit_col = ex.get("unit_col", "Menge")
    price_col = ex.get("price_col", "Einzelpreis €")
    cols = [("Datum", 20, "l"), ("Leistung / Artikel", 42, "l"), (unit_col, 146, "r"),
            (price_col, 168, "r"), ("Betrag €", 190, "r")]
    for name, x, al in cols:
        pg.t(x, y, name, 8, "Helvetica-Bold", align=al)
    pg.hline(20, 190, y + 1.6)
    y += 6
    for ln in r.lines:
        pg.t(20, y, de(ln.day) if ln.day else "", 8)
        qty = hours(ln.qty) if ln.unit == "Std." else f"{int(ln.qty)}"
        pg.t(146, y, qty, 8, align="r")
        pg.t(168, y, money(ln.unit_price), 8, align="r")
        pg.t(190, y, money(ln.amount), 8, align="r")
        y = pg.wrap(42, y, ln.text, 92, 8, lead=3.7) + 1.2
    pg.hline(20, 190, y - 1.5)
    y += 3
    if ex.get("total_style") == "insgesamt_euro":
        pg.t(190, y, f"Insgesamt {money(r.amount)} Euro", 10, "Helvetica-Bold", align="r")
    else:
        pg.t(190, y, f"{ex.get('total_label', 'Rechnungsbetrag')}: {money(r.amount)} €", 10,
             "Helvetica-Bold", align="r")
    y += 9
    if r.due_date:
        pg.t(20, y, f"Zahlbar bis: {de(r.due_date)}", 9, "Helvetica-Bold")
        y += 5
    for s in r.outro:
        y = pg.wrap(20, y, s, 170, 8.5) + 1

    footer(pg, r.provider)
    pg.watermark(165)
    pg.disclaimer()
    c.showPage()
    c.save()


# ---- Apothekenquittung (Kassenbon, schmal) ----

def render_pharmacy(r: Receipt, path: Path):
    width = 80
    body: list[tuple[str, str, str]] = []  # (text, align, font)
    sep = ("-" * 42, "l", "Courier")
    body += [(r.provider.name, "c", "Courier-Bold"), (r.provider.subtitle[0], "c", "Courier"),
             (r.provider.street, "c", "Courier"), (r.provider.city, "c", "Courier"),
             (f"Tel. {r.provider.phone}", "c", "Courier"), sep,
             ("Quittung zum Privatrezept", "l", "Courier-Bold"),
             (f"Datum: {de(r.invoice_date)}  Zeit: {r.extra['time']}", "l", "Courier"),
             (f"Beleg-Nr.: {r.extra['beleg']}   Kasse 2", "l", "Courier"),
             (f"Für {r.person.full}, Geburtsdatum: {de(r.person.born)}", "l", "Courier"), sep]
    for ln in r.lines:
        body.append((f"PZN {ln.pzn}", "l", "Courier"))
        for part in simpleSplit(ln.text, "Courier", 7.5, (width - 10) * mm):
            body.append((part, "l", "Courier"))
        body.append((f"{int(ln.qty)} x {money(ln.unit_price)} €".rjust(30) +
                     f"{money(ln.amount)} €".rjust(12), "l", "Courier"))
    mwst = q(r.amount * D(19) / D(119))
    body += [sep, (f"Summe: {money(r.amount)} €".rjust(42), "l", "Courier-Bold"),
             (f"Gegeben EC-Karte {money(r.amount)} €".rjust(42), "l", "Courier"), sep,
             (f"enth. MwSt. 19 %: {money(mwst)} €".rjust(42), "l", "Courier"),
             ("", "l", "Courier"), ("Vielen Dank für Ihren Besuch!", "c", "Courier"),
             ("Gute Besserung!", "c", "Courier")]
    height = 20 + len(body) * 3.5 + 12
    size = (width * mm, height * mm)
    c, pg = new_canvas(path, size)
    y = 10
    for text, align, font in body:
        if align == "c":
            pg.t(width / 2, y, text, 7.5, font, align="c")
        else:
            pg.t(5, y, text, 7.5, font)
        y += 3.5
    pg.watermark(70)
    c.setFont("Helvetica-Oblique", 5)
    c.setFillColor(GREY)
    for i, part in enumerate(simpleSplit(DISCLAIMER, "Helvetica-Oblique", 5, (width - 8) * mm)):
        c.drawCentredString(width / 2 * mm, (7 - i * 2.2) * mm, part)
    c.showPage()
    c.save()


# ---- Formular Verhinderungspflege ----

def render_care_form(r: Receipt, path: Path):
    c, pg = new_canvas(path)
    carer = r.provider
    pg.t(20, 18, VERSICHERER.name, 12, "Helvetica-Bold")
    pg.t(20, 23, "Private Pflegepflichtversicherung", 9)
    pg.t(190, 18, "Formular PV-39", 8, color=GREY, align="r")
    pg.t(105, 38, "Nachweis über Verhinderungspflege", 14, "Helvetica-Bold", align="c")
    pg.t(105, 44, "nach § 39 SGB XI – bitte je Kalendermonat einen Nachweis einreichen", 8.5,
         color=GREY, align="c")

    def section(y, title, h):
        pg.box(18, y, 174, h)
        pg.t(21, y + 5, title, 9.5, "Helvetica-Bold")

    y = 52
    section(y, "1. Pflegebedürftige Person", 24)
    pg.t(21, y + 11, "Name, Vorname:", 8.5, color=GREY)
    pg.t(52, y + 11, f"{r.person.last}, {r.person.first}", 10, "Helvetica-Oblique", PEN)
    pg.t(118, y + 11, "geb. am:", 8.5, color=GREY)
    pg.t(134, y + 11, de(r.person.born), 10, "Helvetica-Oblique", PEN)
    pg.t(21, y + 18, "Versicherungsnummer:", 8.5, color=GREY)
    pg.t(58, y + 18, "40067890", 10, "Helvetica-Oblique", PEN)
    pg.t(118, y + 18, "Pflegegrad:", 8.5, color=GREY)
    pg.t(137, y + 18, "3", 10, "Helvetica-Oblique", PEN)

    y = 80
    span = r.extra["span"]
    section(y, "2. Verhinderung der Pflegeperson", 30)
    pg.t(21, y + 11, "Die private Pflegeperson war verhindert wegen:", 8.5)
    for i, (key, label) in enumerate((("urlaub", "Erholungsurlaub"), ("krankheit", "Krankheit"),
                                      ("sonstige", "sonstiger Gründe (stundenweise)"))):
        pg.check(21 + i * 45, y + 17, r.extra["reason"] == key)
        pg.t(26 + i * 45, y + 17, label, 8.5)
    pg.t(21, y + 23, f"Zeitraum der Verhinderung: {de(span[0])} - {de(span[1])}", 8.5)
    pg.t(21, y + 28, f"Ich habe die Verhinderungspflege bei {r.person.full} in diesem Zeitraum "
                     "übernommen.", 8.5)

    y = 114
    section(y, "3. Ersatzpflegeperson", 30)
    pg.t(21, y + 11, f"Vor- und Zuname der Ersatzpflegeperson: {carer.name}", 8.5)
    pg.t(21, y + 17, f"Anschrift: {carer.street}, {carer.city}", 8.5)
    pg.t(21, y + 23, "Bis zum 2. Grad verwandt oder verschwägert:", 8.5)
    pg.check(95, y + 23, False)
    pg.t(100, y + 23, "ja", 8.5)
    pg.check(110, y + 23, True)
    pg.t(115, y + 23, "nein", 8.5)
    pg.t(21, y + 28, "In häuslicher Gemeinschaft lebend:", 8.5)
    pg.check(95, y + 28, False)
    pg.t(100, y + 28, "ja", 8.5)
    pg.check(110, y + 28, True)
    pg.t(115, y + 28, "nein", 8.5)

    y = 148
    rows = len(r.lines)
    section(y, "4. Einsatzzeiten der Ersatzpflegeperson", 32 + rows * 5.2)
    cols = [("Datum", 22, "l"), ("von", 55, "l"), ("bis", 75, "l"), ("Stunden", 112, "r"),
            ("Stundensatz", 145, "r"), ("Betrag", 185, "r")]
    for name, x, al in cols:
        pg.t(x, y + 11, name, 8, "Helvetica-Bold", align=al)
    pg.hline(21, 189, y + 12.8)
    yy = y + 18
    for ln in r.lines:
        pg.t(22, yy, de(ln.day), 9.5, "Helvetica-Oblique", PEN)
        pg.t(55, yy, ln.start, 9.5, "Helvetica-Oblique", PEN)
        pg.t(75, yy, ln.end, 9.5, "Helvetica-Oblique", PEN)
        pg.t(112, yy, hours(ln.hours), 9.5, "Helvetica-Oblique", PEN, "r")
        pg.t(145, yy, f"{money(ln.rate)} €", 9.5, "Helvetica-Oblique", PEN, "r")
        pg.t(185, yy, f"{money(ln.amount)} €", 9.5, "Helvetica-Oblique", PEN, "r")
        yy += 5.2
    pg.hline(21, 189, yy - 3.2)
    total_h = sum((ln.hours for ln in r.lines), D(0))
    pg.t(22, yy + 1, "Summe", 8.5, "Helvetica-Bold")
    pg.t(112, yy + 1, hours(total_h), 9.5, "Helvetica-Oblique", PEN, "r")
    pg.t(185, yy + 1, f"{money(r.amount)} €", 9.5, "Helvetica-Oblique", PEN, "r")
    pg.t(22, yy + 8, f"Ich bestätige, für die Verhinderungspflege insgesamt {money(r.amount)} EUR "
                     "erhalten zu haben.", 8.5)

    y = 148 + 32 + rows * 5.2 + 7
    pg.t(20, y, "Fahrkosten und Verdienstausfall: keine", 8.5)
    y += 14
    signed = r.extra["signed"]
    pg.t(20, y - 2, f"Musterstadt, {de(signed)}", 10, "Helvetica-Oblique", PEN)
    pg.signature(62, y - 1, 36, r.key + "a")
    pg.hline(20, 100, y + 1.5, 0.4, INK)
    pg.t(20, y + 5, "Ort, Datum, Unterschrift der Ersatzpflegeperson", 7.5, color=GREY)
    pg.t(110, y - 2, f"Musterstadt, {de(signed)}", 10, "Helvetica-Oblique", PEN)
    pg.signature(152, y - 1, 34, r.key + "b")
    pg.hline(110, 190, y + 1.5, 0.4, INK)
    pg.t(110, y + 5, "Ort, Datum, Unterschrift pflegebedürftige Person / Bevollmächtigte", 7.5,
         color=GREY)

    pg.wrap(20, 272, f"Bitte senden Sie den Nachweis mit Ihren übrigen Belegen an: "
                     f"{VERSICHERER.name}, Leistungsservice Pflege, {VERSICHERER.street}, "
                     f"{VERSICHERER.city}.", 170, 7.5, color=GREY)
    pg.watermark(165)
    pg.disclaimer()
    c.showPage()
    c.save()


RENDER = {"fee": render_fee, "priced": render_priced, "pharmacy": render_pharmacy,
          "care_form": render_care_form}


# --------------------------------------------------------------------------
# Leistungsabrechnung
# --------------------------------------------------------------------------

@dataclass
class SRow:
    receipt: Receipt | None
    number: str
    tariff: str
    invoice_amount: Decimal | None   # nur in der ersten Zeile eines Belegs
    portion: Decimal
    corrected: Decimal | None
    deferred: Decimal | None
    reimbursable: Decimal
    own: Decimal | None
    deductible: Decimal | None
    reimbursed: Decimal


@dataclass
class Settlement:
    number: str
    when: date
    vn: str
    addressee: Person
    doc_id: str
    receipts: list[Receipt]
    rows: list[SRow] = field(default_factory=list)
    item_notes: dict = field(default_factory=dict)

    @property
    def total_reimbursed(self) -> Decimal:
        return sum((r.reimbursed for r in self.rows), D(0))

    @property
    def total_invoiced(self) -> Decimal:
        return sum((r.invoice_amount or D(0) for r in self.rows), D(0))

    @property
    def filename(self) -> str:
        return f"{self.when:%Y%m%d}_{self.vn}_Leistungsinformationen_{self.doc_id}.pdf"


SB_PER_YEAR = D("150.00")


def settle(s: Settlement, first_receipt_no: int, sb_left: dict):
    no = first_receipt_no
    for r in s.receipts:
        number = f"B/26/{no}"
        no += 1
        r.extra["receipt_number"] = number
        r.extra["settlement_number"] = s.number
        notes = list(r.notes)
        # Tarifanteile bestimmen
        parts = r.parts
        if r.key == "zahnarzt-miriam":
            goae_part = sum((ln.amount for ln in r.lines if ln.schedule == "GOÄ"), D(0))
            portions = [r.amount - goae_part, goae_part]
        else:
            portions = [p.portion if p.portion is not None else r.amount for p in parts]
        if r.key == "hno-ben":
            parts = [Part("KA1", corrected=sum((ln.at_factor(min(ln.factor, D("2.3")))
                                                for ln in r.lines), D(0)))]
        ded_used = D(0)
        for i, (p, portion) in enumerate(zip(parts, portions)):
            base = p.corrected if p.corrected is not None else portion
            reimbursable = base - (p.deferred or D(0))
            own = q(reimbursable * (1 - p.rate)) if p.rate < 1 else None
            ded = None
            if p.deductible:
                left = sb_left[r.person.first]
                ded = min(left, reimbursable - (own or D(0)))
                sb_left[r.person.first] = left - ded
                ded_used += ded
                ded = ded if ded > 0 else None
            reimbursed = reimbursable - (own or D(0)) - (ded or D(0))
            s.rows.append(SRow(r, number, p.tariff, r.amount if i == 0 else None, portion,
                               p.corrected, p.deferred, reimbursable, own, ded, reimbursed))
        if ded_used > 0:
            used = SB_PER_YEAR - sb_left[r.person.first]
            notes.append(("920", f"Die tarifliche Selbstbeteiligung 2026 beträgt "
                                 f"{money(SB_PER_YEAR)} EUR. Davon sind bisher {money(used)} EUR "
                                 f"verbraucht."))
        s.item_notes[number] = notes
    return no


def build_settlements(receipts: list[Receipt]) -> list[Settlement]:
    by_batch = {}
    for r in receipts:
        by_batch.setdefault(r.nnn, []).append(r)
    order = [JONAS, MIRIAM, MILA, BEN, HELGA]

    def ordered(rs):
        return sorted(rs, key=lambda r: (order.index(r.person), r.invoice_date))

    s1 = Settlement("R/26/117", date(2026, 7, 17), "40012345", JONAS, "7100117", ordered(by_batch[301]))
    s2 = Settlement("R/26/129", date(2026, 8, 21), "40012345", JONAS, "7100129", ordered(by_batch[302]))
    s3 = Settlement("R/26/134", date(2026, 9, 18), "40067890", HELGA, "7100134", ordered(by_batch[303]))
    sb_left = {"Jonas": SB_PER_YEAR, "Miriam": SB_PER_YEAR}
    settle(s1, 1201, sb_left)
    settle(s2, 1301, sb_left)
    settle(s3, 1401, {})
    return [s1, s2, s3]


def _m(x):
    return money(x) if x is not None else ""


def settlement_table(s: Settlement) -> list[list[str]]:
    """Tabelle als 13 Spalten, so wie pdf.co die Anlage als CSV ausgibt."""
    E = ""
    out = [[f"Einzelaufstellung zu Ihrer Leistungsabrechnung {s.number} vom {de_long(s.when)}"]
           + [E] * 12,
           [E] * 9 + [f"Versicherungsnummer: {s.vn}", E, E, E],
           ["Beleg-", "Leistungserbringer", "Behandlungs-", "Rechnungs-", "Tarif", "Beleg-",
            "korrigierter", "zurück-", "erstattungs-", "tariflicher", "Selbst-", "Erstattung", E],
           ["Nr.", "Belegart", "zeitraum", "betrag", E, "anteil", "Betrag", "gestellt", "fähig",
            "Eigenanteil", "beteiligung", "EUR", E]]
    persons = []
    for row in s.rows:
        if row.receipt.person not in persons:
            persons.append(row.receipt.person)
    for p in persons:
        out.append([f"{p.full}, geb. {de(p.born)}"] + [E] * 12)
        rows = [r for r in s.rows if r.receipt.person == p]
        seen = set()
        for r in rows:
            rc = r.receipt
            first = r.number not in seen
            seen.add(r.number)
            period = period_short(rc.days[0], rc.days[-1]) if rc.days else ""
            out.append([r.number if first else E, rc.settlement_desc if first else E,
                        period if first else E, _m(r.invoice_amount), r.tariff, _m(r.portion),
                        _m(r.corrected), _m(r.deferred), _m(r.reimbursable), _m(r.own),
                        _m(r.deductible), _m(r.reimbursed), E])
            is_last_row_of_item = r is [x for x in rows if x.number == r.number][-1]
            if is_last_row_of_item and s.item_notes.get(r.number):
                out.append([E, f"Information zur Position {r.number}:"] + [E] * 11)
                for code, text in s.item_notes[r.number]:
                    out.append([E, f"{code}:", text] + [E] * 10)
        inv = sum((r.invoice_amount or D(0) for r in rows), D(0))
        rei = sum((r.reimbursed for r in rows), D(0))
        out.append([f"Gesamtsumme für {p.full}", E, E, money(inv)] + [E] * 7 + [money(rei), E])
    out.append(["Gesamt:", E, E, money(s.total_invoiced)] + [E] * 4 +
               ["Wir überweisen Ihnen", E, E, money(s.total_reimbursed), E])
    out.append([E] * 4 + ["Seite 2"] + [E] * 8)
    return out


def render_settlement(s: Settlement, path: Path):
    c, pg = new_canvas(path)
    letterhead(pg, VERSICHERER)
    address(pg, VERSICHERER, s.addressee)
    info_block(pg, [("Ihr Ansprechpartner:", "Leistungsservice"),
                    ("Telefon:", VERSICHERER.phone),
                    ("Dokument-Nr.:", s.doc_id)])
    pg.t(190, 82, f"Musterstadt, {de_long(s.when)}", 9, align="r")
    y = 96
    pg.t(20, y, f"Ihre Leistungsabrechnung {s.number}", 12, "Helvetica-Bold")
    pg.t(20, y + 5.5, f"Versicherungsnummer {s.vn}", 9)
    y += 16
    anrede = "Sehr geehrter Herr" if s.addressee.salutation == "Herrn" else "Sehr geehrte Frau"
    pg.t(20, y, f"{anrede} {s.addressee.last},", 10)
    y += 8
    iban = f"{FAMILY_IBAN[:4]} **** **** **** **{FAMILY_IBAN[-4:-2]} {FAMILY_IBAN[-2:]}"
    for para in [
        "vielen Dank für die Einreichung Ihrer Belege. Wir haben sie geprüft und",
        f"überweisen heute {money(s.total_reimbursed)} EUR auf Ihr Konto IBAN {iban}.",
        "",
        "Wie sich der Betrag zusammensetzt, sehen Sie in der Einzelaufstellung auf der nächsten "
        "Seite. Zu einzelnen Positionen haben wir Ihnen dort Hinweise gegeben.",
        "",
        "Bitte bewahren Sie diese Abrechnung zusammen mit Ihren Unterlagen auf.",
        "",
        "Freundliche Grüße",
        f"Ihr Leistungsservice der {VERSICHERER.name}",
    ]:
        y = pg.wrap(20, y, para, 170, 10, lead=5) if para else y + 3
    footer(pg, VERSICHERER)
    pg.watermark(165)
    pg.disclaimer()
    c.showPage()

    # Seite 2: Einzelaufstellung (quer)
    size = landscape(A4)
    c.setPageSize(size)
    pg = Pg(c, size)
    table = settlement_table(s)
    pg.t(12, 14, table[0][0], 10, "Helvetica-Bold")
    pg.t(285, 14, table[1][9], 9, align="r")
    xs = [(12, "l"), (30, "l"), (93, "l"), (140, "r"), (144, "l"), (175, "r"), (196, "r"),
          (214, "r"), (234, "r"), (252, "r"), (268, "r"), (285, "r")]
    y = 24
    for hdr in table[2:4]:
        for (x, al), val in zip(xs, hdr):
            pg.t(x, y, val, 6.8, "Helvetica-Bold", align=al)
        y += 3.2
    pg.hline(12, 285, y - 1.8)
    y += 2.5
    for row in table[4:-1]:
        col0 = row[0]
        if ", geb. " in col0:
            y += 1.5
            pg.t(12, y, col0, 8, "Helvetica-Bold")
            y += 4.6
        elif col0.startswith("Gesamtsumme") or col0 == "Gesamt:":
            pg.hline(128, 285, y - 3, 0.3)
            bold = "Helvetica-Bold"
            pg.t(12, y, col0, 7.5, bold)
            pg.t(140, y, row[3], 7.5, bold, align="r")
            if row[8]:
                pg.t(234, y, row[8], 7.5, bold, align="r")
            pg.t(285, y, row[11], 7.5, bold, align="r")
            y += 6
        elif col0 == "" and row[1].startswith("Information zur Position"):
            pg.t(30, y, row[1], 6.8, "Helvetica-Oblique", GREY)
            y += 3.4
        elif col0 == "" and row[1].endswith(":") and row[1][:-1].isdigit():
            y = pg.wrap(30, y, f"{row[1]} {row[2]}", 200, 6.8, "Helvetica-Oblique", GREY,
                        lead=3.2) + 0.4
        else:
            for (x, al), val in zip(xs, row):
                pg.t(x, y, val, 7, align=al)
            y += 4.2
    pg.t(148, 200, "Seite 2", 7, color=GREY, align="c")
    pg.watermark(200)
    pg.disclaimer(205)
    c.showPage()
    c.save()


def render_insurer_letter(path: Path, when: date):
    c, pg = new_canvas(path)
    letterhead(pg, Org(VERSICHERER.name, ("Private Pflegepflichtversicherung",),
                       VERSICHERER.street, VERSICHERER.phone, VERSICHERER.email, VERSICHERER.iban))
    address(pg, VERSICHERER, HELGA)
    info_block(pg, [("Versicherungsnummer:", "40067890"), ("Dokument-Nr.:", "7100098")])
    pg.t(190, 82, f"Musterstadt, {de_long(when)}", 9, align="r")
    y = 96
    pg.t(20, y, "Pflegepflichtversicherung: Ihr Entlastungsbetrag nach § 45b SGB XI", 11,
         "Helvetica-Bold")
    y += 10
    for para in [
        "Sehr geehrte Frau Beispiel,",
        "",
        "als pflegebedürftige Person mit Pflegegrad 3 steht Ihnen ein Entlastungsbetrag von "
        "131,00 EUR monatlich zu. Sie können ihn für anerkannte Angebote zur Unterstützung im "
        "Alltag einsetzen, zum Beispiel für Betreuung und Begleitung.",
        "",
        "Beträge, die Sie in einem Kalenderjahr nicht verbrauchen, werden in das folgende "
        "Kalenderhalbjahr übertragen und verfallen, wenn sie bis zum 30. Juni des Folgejahres "
        "nicht genutzt sind.",
        "",
        "Stand Ihres Guthabens zum 31. Mai 2026: 655,00 EUR.",
        "",
        "Reichen Sie Rechnungen anerkannter Anbieter einfach mit Ihren übrigen Belegen ein. "
        "Wir erstatten direkt auf Ihr Konto.",
        "",
        "Freundliche Grüße",
        f"Ihre {VERSICHERER.name}",
    ]:
        y = pg.wrap(20, y, para, 170, 10, lead=5) if para else y + 3
    footer(pg, VERSICHERER)
    pg.watermark(165)
    pg.disclaimer()
    c.showPage()
    c.save()


# --------------------------------------------------------------------------
# Metadaten, Scans
# --------------------------------------------------------------------------

def set_metadata(path: Path, title: str, created: date, producer: str):
    reader = PdfReader(str(path))
    writer = PdfWriter()
    writer.append(reader)
    stamp = f"D:{created:%Y%m%d}120000+02'00'"
    writer.add_metadata({"/Title": title, "/Producer": producer,
                         "/Creator": "samples/generate_samples.py",
                         "/CreationDate": stamp, "/ModDate": stamp})
    with open(path, "wb") as f:
        writer.write(f)


def make_scan(src: Path, dst: Path, created: date, seed: str):
    """Rastert ein PDF und verfremdet es wie einen Handy-Scan (ohne Textebene)."""
    import pypdfium2 as pdfium

    rnd = random.Random(seed)
    pdf = pdfium.PdfDocument(str(src))
    pages = []
    for page in pdf:
        img = page.render(scale=150 / 72).to_pil().convert("RGB")
        paper = Image.new("RGB", img.size, (247, 244, 236))
        img = Image.blend(img, paper, 0.06)
        noise = Image.frombytes("L", img.size, rnd.randbytes(img.width * img.height))
        img = Image.blend(img, noise.convert("RGB"), 0.05)
        img = img.rotate(rnd.uniform(-0.9, 0.9), resample=Image.BICUBIC,
                         fillcolor=(247, 244, 236), expand=False)
        img = img.filter(ImageFilter.GaussianBlur(0.45))
        pages.append(img)
    pdf.close()
    pages[0].save(str(dst), "PDF", resolution=150, save_all=True, append_images=pages[1:],
                  quality=72)
    set_metadata(dst, dst.stem, created, "synthetischer Scan (samples/generate_samples.py)")


def pzn_for(rnd: random.Random) -> str:
    while True:
        digits = [rnd.randint(0, 9) for _ in range(7)]
        check = sum(dg * (i + 1) for i, dg in enumerate(digits)) % 11
        if check < 10:
            return "".join(map(str, digits)) + str(check)


def page_text(path: Path, page: int) -> str:
    return PdfReader(str(path)).pages[page].extract_text(extraction_mode="layout")


# --------------------------------------------------------------------------
# Hauptprogramm
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-scans", action="store_true", help="keine Scan-Varianten erzeugen")
    args = ap.parse_args()

    for folder in (DIR_BELEGE, DIR_SCANS, DIR_ABR):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)

    rnd = random.Random(20260929)
    receipts = build_receipts()
    for r in receipts:
        for ln in r.lines:
            if isinstance(ln, PriceLine) and r.kind == "pharmacy":
                ln.pzn = pzn_for(rnd)
    settlements = build_settlements(receipts)

    manifest = {
        "hinweis": DISCLAIMER + " Die IBANs tragen die nicht vergebene Bankleitzahl "
                                "000 000 00.",
        "insured_persons": ["Jonas", "Miriam", "Mila", "Ben", "Helga"],
        "receipts": [], "settlements": [], "other_documents": [],
    }

    for r in receipts:
        path = DIR_BELEGE / r.filename
        RENDER[r.kind](r, path)
        submitted = {301: date(2026, 6, 22), 302: date(2026, 7, 31), 303: date(2026, 9, 5)}[r.nnn]
        set_metadata(path, path.stem, submitted, "synthetisch (samples/generate_samples.py)")
        scan = None
        if not args.no_scans:
            scan = DIR_SCANS / r.filename
            make_scan(path, scan, submitted, r.key)
        payee = r.payee or (r.provider if r.kind != "care_form" else None)
        manifest["receipts"].append({
            "file": f"belege/{r.filename}",
            "scan_file": f"scans/{r.filename}" if scan else None,
            "submission_date": submitted.isoformat(),
            "filename_person": r.person.first,
            "filename_provider": r.tag,
            "receipt_type": r.receipt_type,
            "provider_name": r.provider.name,
            "payment_recipient": payee.name if payee else None,
            "payment_iban": payee.iban if payee and payee.iban else None,
            "invoice_number": r.invoice_number,
            "invoice_date": (r.days[0] if r.kind == "care_form" else r.invoice_date).isoformat(),
            "invoice_amount": float(r.amount),
            "insured_person": r.person.full,
            "insured_birthdate": r.person.born.isoformat(),
            "treatment_period": r.period,
            "due_date": r.due_date.isoformat() if r.due_date else None,
            "description": r.description or None,
            "settlement_number": r.extra.get("settlement_number"),
            "receipt_number": r.extra.get("receipt_number"),
        })

    for s in settlements:
        path = DIR_ABR / s.filename
        render_settlement(s, path)
        set_metadata(path, path.stem, s.when, "synthetisch (samples/generate_samples.py)")
        header_file = path.with_suffix(".pdfco-header.txt")
        csv_file = path.with_suffix(".pdfco.csv")
        header_file.write_text(page_text(path, 0), encoding="utf-8")
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            csv.writer(f, lineterminator="\n").writerows(settlement_table(s))
        items = []
        for number in dict.fromkeys(r.number for r in s.rows):
            rows = [r for r in s.rows if r.number == number]
            rc = rows[0].receipt
            items.append({
                "receipt_number": number,
                "receipt_file": f"belege/{rc.filename}",
                "insured_person": rc.person.full,
                "insured_birthdate": rc.person.born.isoformat(),
                "description": rc.settlement_desc,
                "treatment_period": period_short(rc.days[0], rc.days[-1]),
                "invoice_amount": float(rc.amount),
                "tariffs": [r.tariff for r in rows],
                "receipt_portion": float(sum((r.portion for r in rows), D(0))),
                "reimbursable_amount": float(sum((r.reimbursable for r in rows), D(0))),
                "reimbursed_amount": float(sum((r.reimbursed for r in rows), D(0))),
                "notes": [f"{c}: {t}" for c, t in s.item_notes.get(number, [])],
            })
        manifest["settlements"].append({
            "file": f"abrechnungen/{s.filename}",
            "pdfco_header_fixture": f"abrechnungen/{header_file.name}",
            "pdfco_csv_fixture": f"abrechnungen/{csv_file.name}",
            "settlement_number": s.number,
            "settlement_date": s.when.isoformat(),
            "insurance_number": s.vn,
            "total_invoiced": float(s.total_invoiced),
            "total_reimbursed": float(s.total_reimbursed),
            "items": items,
        })

    letter_date = date(2026, 6, 12)
    letter = DIR_ABR / f"{letter_date:%Y%m%d}_40067890_Schreiben_7100098.pdf"
    render_insurer_letter(letter, letter_date)
    set_metadata(letter, letter.stem, letter_date, "synthetisch (samples/generate_samples.py)")
    letter_header = letter.with_suffix(".pdfco-header.txt")
    letter_header.write_text(page_text(letter, 0), encoding="utf-8")
    manifest["other_documents"].append({
        "file": f"abrechnungen/{letter.name}",
        "pdfco_header_fixture": f"abrechnungen/{letter_header.name}",
        "expected_doc_type": "Entlastungsleistungen-Brief",
    })

    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    n_scans = 0 if args.no_scans else len(receipts)
    print(f"{len(receipts)} Belege, {n_scans} Scans, {len(settlements)} Leistungsabrechnungen, "
          f"1 Versichererbrief -> {HERE}")
    for s in settlements:
        print(f"  {s.number}: {len(dict.fromkeys(r.number for r in s.rows))} Positionen, "
              f"erstattet {money(s.total_reimbursed)} EUR")


if __name__ == "__main__":
    main()
