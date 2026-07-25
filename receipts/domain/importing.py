import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import StringIO

from .markets import normalize_market_name


EXPECTED_COLUMNS = [
    "Datum",
    "Einkaufsladen",
    "Artikel",
    "Anzahl",
    "Gesamtpreis",
    "Käufer",
]


@dataclass
class ParsedImportRow:
    row_number: int
    raw: dict
    date: object = None
    market: str = ""
    article: str = ""
    quantity: Decimal = Decimal("1")
    total_price_cents: int = 0
    buyer_name: str = ""
    assigned_names: list[str] = field(default_factory=list)
    weights_by_name: dict[str, Decimal] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self):
        return not self.errors

    def raw_json(self):
        return json.loads(json.dumps(self.raw, ensure_ascii=False))


def parse_german_date(value):
    value = (value or "").strip()
    if not value:
        raise ValueError("Datum fehlt.")
    try:
        return datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError as exc:
        raise ValueError("Datum muss im Format TT.MM.JJJJ vorliegen.") from exc


def parse_german_decimal(value, default=None):
    value = (value or "").strip()
    if not value:
        if default is not None:
            return default
        raise ValueError("Zahl fehlt.")
    cleaned = value.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("Zahl konnte nicht gelesen werden.") from exc


def parse_price_cents(value):
    amount = parse_german_decimal(value)
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_euro(cents):
    amount = Decimal(cents) / Decimal("100")
    return f"{amount:.2f}".replace(".", ",") + " €"


def parse_import_csv(text, known_markets=()):
    text = (text or "").lstrip("\ufeff")
    reader = csv.DictReader(StringIO(text), delimiter=";")
    rows = []

    if not reader.fieldnames:
        return [ParsedImportRow(row_number=0, raw={}, errors=["CSV enthält keine Kopfzeile."])]

    normalized_headers = [header.strip() for header in reader.fieldnames if header]
    missing_columns = [column for column in EXPECTED_COLUMNS if column not in normalized_headers]

    for index, raw in enumerate(reader, start=2):
        raw = {key.strip() if key else key: (value or "").strip() for key, value in raw.items()}
        row = ParsedImportRow(row_number=index, raw=raw)
        if missing_columns:
            row.errors.append("Fehlende Spalten: " + ", ".join(missing_columns))
            rows.append(row)
            continue

        row.market = normalize_market_name(raw.get("Einkaufsladen", ""), known_markets)
        row.article = raw.get("Artikel", "")
        row.buyer_name = raw.get("Käufer", "")

        _parse_row_values(row, raw)
        rows.append(row)

    if not rows:
        rows.append(ParsedImportRow(row_number=0, raw={}, errors=["CSV enthält keine Datenzeilen."]))
    return rows


def _parse_row_values(row, raw):
    try:
        row.date = parse_german_date(raw.get("Datum"))
    except ValueError as exc:
        row.errors.append(str(exc))
    if not row.market:
        row.errors.append("Einkaufsladen fehlt.")
    if not row.article:
        row.errors.append("Artikel fehlt.")
    try:
        row.quantity = parse_german_decimal(raw.get("Anzahl"), default=Decimal("1")).quantize(
            Decimal("0.01")
        )
    except ValueError as exc:
        row.errors.append("Anzahl: " + str(exc))
    try:
        row.total_price_cents = parse_price_cents(raw.get("Gesamtpreis"))
    except ValueError as exc:
        row.errors.append("Gesamtpreis: " + str(exc))
    if not row.buyer_name:
        row.errors.append("Käufer fehlt.")
