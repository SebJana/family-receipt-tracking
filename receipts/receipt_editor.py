from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count

from .models import ItemAllocation, Person, Receipt, ReceiptItem
from .services import (
    format_euro,
    market_choices,
    normalize_market_name,
    parse_german_decimal,
    parse_price_cents,
)


@dataclass
class EditableRow:
    index: int
    item_id: int | None = None
    date: object = None
    market: str = ""
    article: str = ""
    quantity: Decimal = Decimal("1")
    price: str = ""
    buyer_name: str = ""
    assigned_names: list[str] = None
    weights_by_name: dict[str, Decimal] = None
    locked_allocations: list = None
    delete: bool = False
    errors: list[str] = None
    raw: dict = None

    def __post_init__(self):
        self.assigned_names = self.assigned_names or []
        self.weights_by_name = self.weights_by_name or {}
        self.locked_allocations = self.locked_allocations or []
        self.errors = self.errors or []
        self.raw = self.raw or {}

    def weight_for(self, person):
        return self.weights_by_name.get(person.name, Decimal("1"))


def _parse_manual_receipt_request(post, people, buyers):
    errors = []
    receipt_data = {
        "date": post.get("date", ""),
        "market": normalize_market_name(post.get("market", ""), _market_choices()),
        "buyer": post.get("buyer", ""),
    }
    try:
        receipt_date = datetime.strptime(receipt_data["date"], "%Y-%m-%d").date()
    except ValueError:
        errors.append("Datum fehlt oder ist ungültig.")
        receipt_date = None
    if not receipt_data["market"]:
        errors.append("Einkaufsladen fehlt.")
    people_by_id = _people_by_id(people)
    buyer = _people_by_id(buyers).get(receipt_data["buyer"])
    if buyer is None:
        errors.append("Käufer fehlt oder ist ungültig.")

    rows, row_errors = _parse_item_rows(post, people_by_id, skip_empty=True)
    errors.extend(row_errors)
    if not rows:
        errors.append("Mindestens eine Artikelzeile ist erforderlich.")

    if errors:
        return receipt_data, rows or [EditableRow(index=0)], errors

    with transaction.atomic():
        receipt = Receipt.objects.create(date=receipt_date, market=receipt_data["market"], buyer=buyer)
        _create_items_for_receipt(receipt, rows, people_by_id)
    return receipt_data, rows, []


def _assignable_people():
    return Person.objects.filter(active=True, is_deleted=False).order_by("name")


def _buyer_choices(current_buyer=None):
    choices = list(Person.objects.filter(is_deleted=False).order_by("name"))
    if current_buyer and current_buyer not in choices:
        choices.append(current_buyer)
    return choices


def _market_choices():
    existing = [
        row["market"]
        for row in Receipt.objects.values("market").annotate(count=Count("id")).order_by("-count", "market")
    ]
    return market_choices(existing)


def _update_receipt_from_request(receipt, post, people, buyers):
    receipt_data = {
        "date": post.get("date", ""),
        "market": normalize_market_name(post.get("market", ""), _market_choices()),
        "buyer": post.get("buyer", ""),
    }
    errors = []
    try:
        receipt_date = datetime.strptime(receipt_data["date"], "%Y-%m-%d").date()
    except ValueError:
        errors.append("Datum fehlt oder ist ungültig.")
        receipt_date = None
    if not receipt_data["market"]:
        errors.append("Einkaufsladen fehlt.")
    buyer = _people_by_id(buyers).get(receipt_data["buyer"])
    if buyer is None:
        errors.append("Käufer fehlt oder ist ungültig.")

    people_by_id = _people_by_id(people)
    locked_people_by_id = _people_by_id(Person.objects.filter(is_deleted=True))
    rows, row_errors = _parse_item_rows(post, people_by_id, skip_empty=True)
    _apply_locked_allocations(rows, post, locked_people_by_id)
    errors.extend(row_errors)
    remaining_rows = [row for row in rows if not row.delete]
    if not remaining_rows:
        errors.append("Mindestens eine Artikelzeile ist erforderlich.")
    if errors:
        return receipt_data, rows, errors

    with transaction.atomic():
        receipt.date = receipt_date
        receipt.market = receipt_data["market"]
        receipt.buyer = buyer
        receipt.save()
        _sync_items_for_receipt(receipt, rows, people_by_id)
    return receipt_data, rows, []


def _parse_item_rows(post, people_by_id, skip_empty):
    rows = []
    errors = []
    row_count = int(post.get("row_count", "0") or 0)
    for index in range(row_count):
        prefix = f"item-{index}"
        item_id_raw = post.get(f"{prefix}-id", "").strip()
        delete = post.get(f"{prefix}-delete") == "on"
        article = post.get(f"{prefix}-article", "").strip()
        price = post.get(f"{prefix}-price", "").strip()
        quantity_raw = post.get(f"{prefix}-quantity", "").strip() or "1"
        if skip_empty and not item_id_raw and not any([article, price, post.getlist(f"{prefix}-persons")]):
            continue
        row = EditableRow(
            index=index,
            item_id=int(item_id_raw) if item_id_raw.isdigit() else None,
            article=article,
            quantity=quantity_raw,
            price=price,
            delete=delete,
        )
        if delete and row.item_id:
            rows.append(row)
            continue
        if not article:
            row.errors.append("Artikel fehlt.")
        try:
            row.quantity = parse_german_decimal(quantity_raw, default=Decimal("1")).quantize(Decimal("0.01"))
        except ValueError as exc:
            row.errors.append("Anzahl: " + str(exc))
        try:
            row.total_price_cents = parse_price_cents(price)
        except ValueError as exc:
            row.errors.append("Gesamtpreis: " + str(exc))
        selected_ids = post.getlist(f"{prefix}-persons")
        for person_id in selected_ids:
            person = people_by_id.get(person_id)
            if person is None:
                row.errors.append("Zuordnung enthält eine unbekannte Person.")
                continue
            row.assigned_names.append(person.name)
            weight_raw = post.get(f"{prefix}-weight-{person_id}", "1")
            try:
                weight = parse_german_decimal(weight_raw, default=Decimal("1")).quantize(Decimal("0.0001"))
                if weight <= 0:
                    raise ValueError("Faktor muss größer als 0 sein.")
                row.weights_by_name[person.name] = weight
            except ValueError as exc:
                row.errors.append(f"Faktor für {person.name}: {exc}")
        _normalize_row_weights(row)
        if row.errors:
            errors.extend([f"Zeile {index + 1}: {error}" for error in row.errors])
        rows.append(row)
    return rows, errors


def _normalize_row_weights(row):
    if not row.assigned_names:
        return

    quantum = Decimal("0.0001")
    total = sum(
        (row.weights_by_name.get(name, Decimal("1")) for name in row.assigned_names),
        Decimal("0"),
    )
    if total <= 0:
        equal = Decimal("1") / Decimal(len(row.assigned_names))
        raw_shares = [equal for _name in row.assigned_names]
    else:
        raw_shares = [
            row.weights_by_name.get(name, Decimal("1")) / total for name in row.assigned_names
        ]

    min_share = quantum if len(row.assigned_names) > 1 else Decimal("0")
    shares = [
        max(share.quantize(quantum, rounding=ROUND_HALF_UP), min_share)
        for share in raw_shares
    ]
    difference_units = int((Decimal("1.0000") - sum(shares)) / quantum)

    while difference_units > 0:
        index = max(range(len(shares)), key=lambda idx: raw_shares[idx] - shares[idx])
        shares[index] += quantum
        difference_units -= 1

    while difference_units < 0:
        candidates = [idx for idx, share in enumerate(shares) if share > min_share]
        if not candidates:
            break
        index = max(candidates, key=lambda idx: shares[idx])
        shares[index] -= quantum
        difference_units += 1

    for name, share in zip(row.assigned_names, shares):
        row.weights_by_name[name] = share


def _apply_locked_allocations(rows, post, locked_people_by_id):
    rows_by_index = {row.index: row for row in rows}
    row_count = int(post.get("row_count", "0") or 0)
    for index in range(row_count):
        row = rows_by_index.get(index)
        if row is None or row.delete:
            continue
        prefix = f"item-{index}"
        for person_id in post.getlist(f"{prefix}-locked-persons"):
            person = locked_people_by_id.get(person_id)
            if person is None or person.name in row.assigned_names:
                continue
            weight = parse_german_decimal(
                post.get(f"{prefix}-locked-weight-{person_id}", "1"),
                default=Decimal("1"),
            ).quantize(Decimal("0.0001"))
            row.assigned_names.append(person.name)
            row.weights_by_name[person.name] = weight
            row.locked_allocations.append({"person": person, "weight": weight})


def _people_by_id(people):
    return {str(person.id): person for person in people}


def _known_category_id(article):
    return (
        ReceiptItem.objects.filter(
            article__iexact=article,
            category__isnull=False,
        )
        .order_by("-receipt__date", "-id")
        .values_list("category_id", flat=True)
        .first()
    )


def _create_items_for_receipt(receipt, rows, people_by_id):
    people_by_name = {person.name: person for person in people_by_id.values()}
    for row in rows:
        item = ReceiptItem.objects.create(
            receipt=receipt,
            article=row.article,
            quantity=row.quantity,
            total_price_cents=row.total_price_cents,
            imported_raw_row=row.raw or None,
            category_id=_known_category_id(row.article),
        )
        for name in row.assigned_names:
            ItemAllocation.objects.create(
                item=item,
                person=people_by_name[name],
                weight=row.weights_by_name.get(name, Decimal("1")),
            )


def _sync_items_for_receipt(receipt, rows, people_by_id):
    people_by_name = {person.name: person for person in Person.objects.all()}
    existing_items = {item.id: item for item in receipt.items.all()}
    seen_ids = set()
    for row in rows:
        if row.item_id:
            item = existing_items.get(row.item_id)
            if item is None:
                continue
            seen_ids.add(row.item_id)
            if row.delete:
                item.delete()
                continue
        else:
            if row.delete:
                continue
            item = ReceiptItem(receipt=receipt)

        item.article = row.article
        item.quantity = row.quantity
        item.total_price_cents = row.total_price_cents
        item.category_id = _known_category_id(row.article)
        item.save()

        item.allocations.all().delete()
        for name in row.assigned_names:
            ItemAllocation.objects.create(
                item=item,
                person=people_by_name[name],
                weight=row.weights_by_name.get(name, Decimal("1")),
            )


def _editable_rows_from_receipt(receipt):
    rows = []
    for index, item in enumerate(receipt.items.all()):
        allocations = list(item.allocations.all())
        visible_allocations = [
            allocation for allocation in allocations if not allocation.person.is_deleted
        ]
        locked_allocations = [
            allocation for allocation in allocations if allocation.person.is_deleted
        ]
        rows.append(
            EditableRow(
                index=index,
                item_id=item.id,
                article=item.article,
                quantity=item.quantity,
                price=format_euro(item.total_price_cents),
                assigned_names=[allocation.person.name for allocation in visible_allocations],
                weights_by_name={
                    allocation.person.name: allocation.weight for allocation in visible_allocations
                },
                locked_allocations=locked_allocations,
            )
        )
    if not rows:
        rows.append(EditableRow(index=0))
    return rows


def _editable_from_parsed(index, row):
    price = format_euro(row.total_price_cents) if row.total_price_cents else row.raw.get("Gesamtpreis", "")
    editable = EditableRow(
        index=index,
        date=row.date,
        market=row.market,
        article=row.article,
        quantity=row.quantity,
        price=price,
        buyer_name=row.buyer_name,
        assigned_names=row.assigned_names,
        weights_by_name=row.weights_by_name,
        errors=row.errors,
        raw=row.raw,
    )
    return editable
