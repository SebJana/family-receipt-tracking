import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import StringIO

from django.db import transaction
from django.db.models import Prefetch

from .models import ItemAllocation, Person, Receipt, ReceiptItem


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


@dataclass(frozen=True)
class AllocationShare:
    person: Person
    weight: Decimal = Decimal("1")

    @property
    def person_id(self):
        return self.person.id


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


def parse_import_csv(text):
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

        row.market = raw.get("Einkaufsladen", "")
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
        row.quantity = parse_german_decimal(raw.get("Anzahl"), default=Decimal("1")).quantize(Decimal("0.01"))
    except ValueError as exc:
        row.errors.append("Anzahl: " + str(exc))
    try:
        row.total_price_cents = parse_price_cents(raw.get("Gesamtpreis"))
    except ValueError as exc:
        row.errors.append("Gesamtpreis: " + str(exc))
    if not row.buyer_name:
        row.errors.append("Käufer fehlt.")


def split_item_allocations(item, fallback_people=None):
    allocations = list(item.allocations.all())
    if not allocations:
        people = (
            fallback_people
            if fallback_people is not None
            else Person.objects.filter(active=True, is_deleted=False)
        )
        allocations = [AllocationShare(person=person) for person in people]
    cents = ItemAllocation.split_cents(item.total_price_cents, allocations)
    return list(zip(allocations, cents, strict=True))


def exact_item_allocations(item, fallback_people=None):
    allocations = list(item.allocations.all())
    if not allocations:
        people = (
            fallback_people
            if fallback_people is not None
            else Person.objects.filter(active=True, is_deleted=False)
        )
        allocations = [AllocationShare(person=person) for person in people]
    if not allocations:
        return []

    weights = [Decimal(str(allocation.weight)) for allocation in allocations]
    weight_sum = sum(weights, Decimal("0"))
    if item.total_price_cents == 0 or weight_sum <= 0:
        return [(allocation, Decimal("0")) for allocation in allocations]

    return [
        (allocation, Decimal(item.total_price_cents) * weight / weight_sum)
        for allocation, weight in zip(allocations, weights, strict=True)
    ]


def round_exact_cents(values_by_key):
    rounded = {
        key: int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        for key, value in values_by_key.items()
    }
    target_total = int(
        sum(values_by_key.values(), Decimal("0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    difference = target_total - sum(rounded.values())
    if not difference:
        return rounded

    remainders = [
        (key, values_by_key[key] - Decimal(rounded[key]))
        for key in values_by_key
    ]
    remainders.sort(key=lambda pair: pair[1], reverse=difference > 0)
    step = 1 if difference > 0 else -1
    for key, _remainder in remainders[: abs(difference)]:
        rounded[key] += step
    return rounded


def save_import_rows(rows):
    with transaction.atomic():
        receipts_by_key = {}
        created_items = 0
        for row in rows:
            key = (row.date, row.market, row.buyer_name)
            receipt = receipts_by_key.get(key)
            if receipt is None:
                buyer, _created = Person.objects.get_or_create(
                    name=row.buyer_name,
                    defaults={"active": False, "is_deleted": False},
                )
                receipt = Receipt.objects.create(
                    date=row.date,
                    market=row.market,
                    buyer=buyer,
                )
                receipts_by_key[key] = receipt
            item = ReceiptItem.objects.create(
                receipt=receipt,
                article=row.article,
                quantity=row.quantity,
                total_price_cents=row.total_price_cents,
                imported_raw_row=row.raw_json(),
            )
            for name in row.assigned_names:
                person = Person.objects.get(name=name)
                ItemAllocation.objects.create(
                    item=item,
                    person=person,
                    weight=row.weights_by_name.get(name, Decimal("1")),
                )
            created_items += 1
    return created_items


def build_stats(filters):
    receipts = Receipt.objects.select_related("buyer").prefetch_related(
        Prefetch(
            "items",
            queryset=ReceiptItem.objects.prefetch_related("allocations__person"),
        )
    )
    if filters.get("date_from"):
        receipts = receipts.filter(date__gte=filters["date_from"])
    if filters.get("date_to"):
        receipts = receipts.filter(date__lte=filters["date_to"])
    if filters.get("market"):
        receipts = receipts.filter(market=filters["market"])
    if filters.get("buyer_id"):
        receipts = receipts.filter(buyer_id=filters["buyer_id"])
    monthly_exact = defaultdict(Decimal)
    market_totals_exact = defaultdict(Decimal)
    person_month_exact = defaultdict(lambda: defaultdict(Decimal))
    person_totals_exact = defaultdict(Decimal)
    article_totals_exact = defaultdict(Decimal)
    paid_totals = defaultdict(int)
    owed_totals_exact = defaultdict(Decimal)

    selected_person_id = filters.get("person_id")
    fallback_people = list(Person.objects.filter(active=True, is_deleted=False).order_by("name"))

    for receipt in receipts:
        month = receipt.date.strftime("%Y-%m")
        for item in receipt.items.all():
            paid_totals[receipt.buyer.name] += item.total_price_cents
            item_allocations = list(exact_item_allocations(item, fallback_people))
            for allocation, exact_cents in item_allocations:
                owed_totals_exact[allocation.person.name] += exact_cents
                if selected_person_id and allocation.person_id != selected_person_id:
                    continue
                monthly_exact[month] += exact_cents
                market_totals_exact[receipt.market] += exact_cents
                person_month_exact[allocation.person.name][month] += exact_cents
                person_totals_exact[allocation.person.name] += exact_cents
                article_totals_exact[item.article] += exact_cents

    monthly = round_exact_cents(monthly_exact)
    market_totals = round_exact_cents(market_totals_exact)
    person_totals = round_exact_cents(person_totals_exact)
    article_totals = round_exact_cents(article_totals_exact)

    months = sorted(monthly.keys())
    people = sorted(person_month_exact.keys())
    person_month = defaultdict(lambda: defaultdict(int))
    for month in months:
        rounded_month = round_exact_cents({
            person: person_month_exact[person][month]
            for person in people
            if person_month_exact[person][month] != 0
        })
        for person, cents in rounded_month.items():
            person_month[person][month] = cents

    top_articles = sorted(article_totals.items(), key=lambda pair: pair[1], reverse=True)[:15]
    settlement = build_settlement(paid_totals, round_exact_cents(owed_totals_exact))

    return {
        "monthly": {
            "labels": months,
            "values": [monthly[month] / 100 for month in months],
            "rows": [(month, format_euro(monthly[month])) for month in months],
            "total": format_euro(sum(monthly.values())),
        },
        "markets": {
            "labels": list(market_totals.keys()),
            "values": [value / 100 for value in market_totals.values()],
            "rows": [(market, format_euro(cents)) for market, cents in market_totals.items()],
        },
        "person_month": {
            "labels": months,
            "datasets": [
                {
                    "label": person,
                    "data": [person_month[person][month] / 100 for month in months],
                }
                for person in people
            ],
        },
        "people": {
            "labels": list(person_totals.keys()),
            "values": [value / 100 for value in person_totals.values()],
            "rows": [(person, format_euro(cents)) for person, cents in person_totals.items()],
        },
        "top_articles": [(article, format_euro(cents)) for article, cents in top_articles],
        "settlement": settlement,
    }


def build_settlement(paid_totals, owed_totals):
    names = sorted(set(paid_totals) | set(owed_totals))
    balances = {
        name: paid_totals.get(name, 0) - owed_totals.get(name, 0)
        for name in names
    }
    debtors = [[name, -balance] for name, balance in balances.items() if balance < 0]
    creditors = [[name, balance] for name, balance in balances.items() if balance > 0]
    transfers = []
    debtor_index = 0
    creditor_index = 0
    while debtor_index < len(debtors) and creditor_index < len(creditors):
        debtor, amount_due = debtors[debtor_index]
        creditor, amount_receivable = creditors[creditor_index]
        amount = min(amount_due, amount_receivable)
        if amount:
            transfers.append({"from": debtor, "to": creditor, "amount": format_euro(amount)})
        debtors[debtor_index][1] -= amount
        creditors[creditor_index][1] -= amount
        if debtors[debtor_index][1] == 0:
            debtor_index += 1
        if creditors[creditor_index][1] == 0:
            creditor_index += 1

    return {
        "rows": [
            {
                "name": name,
                "paid": format_euro(paid_totals.get(name, 0)),
                "owed": format_euro(owed_totals.get(name, 0)),
                "balance": format_euro(balances[name]),
                "balance_cents": balances[name],
            }
            for name in names
        ],
        "transfers": transfers,
    }
