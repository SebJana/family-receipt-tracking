from collections import defaultdict
from decimal import Decimal

from django.db.models import Prefetch

from .domain.allocations import (
    AllocationShare,
    exact_item_allocations,
    round_exact_cents,
    split_item_allocations,
)
from .domain.importing import (
    EXPECTED_COLUMNS,
    ParsedImportRow,
    format_euro,
    parse_german_date,
    parse_german_decimal,
    parse_import_csv,
    parse_price_cents,
)
from .domain.markets import (
    CANONICAL_MARKETS,
    MARKET_ALIASES,
    market_choices,
    normalize_market_name,
)
from .models import Person, Receipt, ReceiptItem


__all__ = [
    "AllocationShare",
    "CANONICAL_MARKETS",
    "EXPECTED_COLUMNS",
    "MARKET_ALIASES",
    "ParsedImportRow",
    "build_settlement",
    "build_stats",
    "exact_item_allocations",
    "format_euro",
    "market_choices",
    "normalize_market_name",
    "parse_german_date",
    "parse_german_decimal",
    "parse_import_csv",
    "parse_price_cents",
    "round_exact_cents",
    "split_item_allocations",
]


def build_stats(filters):
    receipts = Receipt.objects.select_related("buyer").prefetch_related(
        Prefetch(
            "items",
            queryset=ReceiptItem.objects.select_related("category").prefetch_related("allocations__person"),
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
    category_totals_exact = defaultdict(Decimal)
    paid_totals = defaultdict(int)
    owed_totals_exact = defaultdict(Decimal)
    contributing_receipt_ids = set()

    selected_person_id = filters.get("person_id")
    fallback_people = list(Person.objects.filter(active=True, is_deleted=False).order_by("name"))

    for receipt in receipts:
        month = receipt.date.strftime("%Y-%m")
        for item in receipt.items.all():
            # Item-level filtering happens before allocation so every chart and table
            # represents the same category selection.
            selected_category = filters.get("category")
            if selected_category == "unknown" and item.category_id is not None:
                continue
            if selected_category and selected_category != "unknown" and str(item.category_id) != selected_category:
                continue
            paid_totals[receipt.buyer.name] += item.total_price_cents
            # Exact decimal shares are aggregated before rounding to avoid losing cents
            # when many small purchases are split between several people.
            item_allocations = list(exact_item_allocations(item, fallback_people))
            for allocation, exact_cents in item_allocations:
                owed_totals_exact[allocation.person.name] += exact_cents
                if selected_person_id and allocation.person_id != selected_person_id:
                    continue
                contributing_receipt_ids.add(receipt.id)
                monthly_exact[month] += exact_cents
                market_totals_exact[receipt.market] += exact_cents
                person_month_exact[allocation.person.name][month] += exact_cents
                person_totals_exact[allocation.person.name] += exact_cents
                article_totals_exact[item.article] += exact_cents
                category_label = f"{item.category.emoji} {item.category.name}" if item.category else "? Unbekannt"
                category_totals_exact[category_label] += exact_cents

    monthly = round_exact_cents(monthly_exact)
    market_totals = round_exact_cents(market_totals_exact)
    person_totals = round_exact_cents(person_totals_exact)
    article_totals = round_exact_cents(article_totals_exact)
    category_totals = round_exact_cents(category_totals_exact)
    sorted_markets = sorted(market_totals.items(), key=lambda pair: (-pair[1], pair[0].casefold()))
    sorted_people = sorted(person_totals.items(), key=lambda pair: (-pair[1], pair[0].casefold()))
    # Largest categories lead both the legend and the table so the main spending drivers
    # remain easy to scan.
    sorted_categories = sorted(category_totals.items(), key=lambda pair: pair[1], reverse=True)

    def category_emoji(label):
        return "?" if label == "? Unbekannt" else label.split(" ", 1)[0]

    category_palette = ["#e85d5d", "#ed8b32", "#e0b52f", "#65a94c", "#2f9d88", "#3f91c9", "#7569c7", "#b05eae", "#9b6b4f"]

    def category_color(label):
        emoji = category_emoji(label)
        # Familiar emoji colors make slices recognizable before the legend is read.
        # A deterministic fallback keeps custom symbols stable between page loads.
        color_groups = [
            ("🍎🍓🍒🍅🌶️🍷🥩🩹", "#df4b4b"),
            ("🍊🥕🥭🍑🧡", "#ed842f"),
            ("🍋🍌🌽🧀🍯🍺🌻⭐", "#dfb72f"),
            ("🍐🍏🥝🥑🥒🥦🥬🫑🫒🫛🌱🌿♻️", "#57a653"),
            ("🐟🐠💧🧊🥛🫐🚙", "#3f91c9"),
            ("🍇🍆☂️🔮💜", "#7966bd"),
            ("🍬🧁🌸🪷💄🎀", "#d75b9b"),
            ("📦🥔🍞🥐🥨🥯🍪🥜☕🧸", "#9b7050"),
            ("?🧻🧼🔌🔋🛒🧾", "#87919f"),
        ]
        for emojis, color in color_groups:
            if emoji in emojis:
                return color
        return category_palette[sum(ord(character) for character in emoji) % len(category_palette)]

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
        "purchase_count": len(contributing_receipt_ids),
        "monthly": {
            "labels": months,
            "values": [monthly[month] / 100 for month in months],
            "rows": [(month, format_euro(monthly[month])) for month in months],
            "total": format_euro(sum(monthly.values())),
        },
        "markets": {
            "labels": [market for market, _cents in sorted_markets],
            "values": [cents / 100 for _market, cents in sorted_markets],
            "rows": [(market, format_euro(cents)) for market, cents in sorted_markets],
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
            "labels": [person for person, _cents in sorted_people],
            "values": [cents / 100 for _person, cents in sorted_people],
            "rows": [(person, format_euro(cents)) for person, cents in sorted_people],
        },
        "top_articles": [(article, format_euro(cents)) for article, cents in top_articles],
        "categories": {
            "labels": [label for label, _value in sorted_categories],
            "values": [value / 100 for _label, value in sorted_categories],
            "colors": [category_color(label) for label, _value in sorted_categories],
            "badges": [{"initials": category_emoji(label), "emoji": True, "background": "#ffffff"} for label, _value in sorted_categories],
            "rows": [(label, format_euro(value)) for label, value in sorted_categories],
        },
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
