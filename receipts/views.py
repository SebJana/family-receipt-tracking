from datetime import datetime, timedelta
from pathlib import Path

from django.contrib import messages
from django.db.models import Exists, OuterRef, Prefetch, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone

from .models import Category, Person, Receipt, ReceiptItem
from .page_views.categories import categories
from .page_views.people import people
from .templatetags.receipt_extras import market_logo
from .receipt_editor import (
    EditableRow,
    _assignable_people,
    _buyer_choices,
    _editable_from_parsed,
    _editable_rows_from_receipt,
    _market_choices,
    _parse_manual_receipt_request,
    _update_receipt_from_request,
)
from .services import build_stats, format_euro, parse_import_csv


RECEIPT_IMPORT_PROMPT = (
    Path(__file__).resolve().parent / "prompts" / "receipt_import_prompt.txt"
).read_text(encoding="utf-8").strip()

STATS_FILTER_SESSION_KEY = "receipt_tracker:stats_filters:v1"
STATS_FILTER_NAMES = (
    "date_from",
    "date_to",
    "market",
    "buyer",
    "person",
    "category",
)


def health(request):
    return HttpResponse("ok")


def receipt_list(request):
    today = timezone.localdate()
    detail_cutoff = min(today.replace(day=1), today - timedelta(days=31))
    receipts = (
        Receipt.objects.select_related("buyer")
        .annotate(list_total_cents=Sum("items__total_price_cents"))
        .order_by("-date", "-created_at")
    )
    market = request.GET.get("market", "").strip()
    buyer_id = request.GET.get("buyer", "").strip()
    article = request.GET.get("article", "").strip()
    if market:
        receipts = receipts.filter(market=market)
    if buyer_id:
        receipts = receipts.filter(buyer_id=buyer_id)
    if article:
        matching_items = ReceiptItem.objects.filter(
            receipt_id=OuterRef("pk"), article__icontains=article
        )
        receipts = receipts.filter(Exists(matching_items))

    item_queryset = ReceiptItem.objects.select_related("category").prefetch_related(
        "allocations__person"
    )
    if not article:
        item_queryset = item_queryset.filter(receipt__date__gte=detail_cutoff)
    receipts = list(
        receipts.prefetch_related(
            Prefetch("items", queryset=item_queryset, to_attr="list_items")
        )
    )
    for receipt in receipts:
        receipt.show_items = bool(article) or receipt.date >= detail_cutoff

    return render(
        request,
        "receipts/receipt_list.html",
        {
            "receipts": receipts,
            "people": _assignable_people(),
            "buyers": Person.objects.all(),
            "markets": Receipt.objects.order_by("market").values_list("market", flat=True).distinct(),
            "filters": {"market": market, "buyer": buyer_id, "article": article},
            "format_euro": format_euro,
        },
    )


def receipt_items(request, receipt_id):
    receipt = get_object_or_404(
        Receipt.objects.prefetch_related(
            "items__category", "items__allocations__person"
        ),
        pk=receipt_id,
    )
    return render(
        request,
        "receipts/_receipt_items.html",
        {"receipt": receipt, "items": receipt.items.all(), "article_search": ""},
    )


def receipt_create(request):
    people = list(_assignable_people())
    buyers = list(_buyer_choices())
    markets = _market_choices()
    if request.method == "POST":
        receipt, rows, errors = _parse_manual_receipt_request(request.POST, people, buyers)
        if not errors:
            messages.success(request, "Beleg wurde gespeichert.")
            return redirect("receipts:receipt_list")
        for error in errors:
            messages.error(request, error)
        return render(
            request,
            "receipts/receipt_form.html",
            {
                "buyers": buyers,
                "can_delete_items": False,
                "form_title": "Neuer Beleg",
                "people": people,
                "markets": markets,
                "receipt": receipt,
                "row_count": max(len(rows), 1),
                "rows": rows,
                "submit_label": "Beleg speichern",
            },
        )

    rows = [EditableRow(index=0)]
    return render(
        request,
        "receipts/receipt_form.html",
        {
            "buyers": buyers,
            "can_delete_items": False,
            "form_title": "Neuer Beleg",
            "people": people,
            "markets": markets,
            "receipt": {},
            "row_count": len(rows),
            "rows": rows,
            "submit_label": "Beleg speichern",
        },
    )


def receipt_edit(request, receipt_id):
    receipt = get_object_or_404(
        Receipt.objects.select_related("buyer").prefetch_related("items__allocations__person"),
        pk=receipt_id,
    )
    people = list(_assignable_people())
    buyers = list(_buyer_choices(receipt.buyer))
    markets = _market_choices()
    item_id = request.GET.get("item", "").strip()
    selected_item = None
    if item_id:
        selected_item = get_object_or_404(receipt.items.all(), pk=item_id)
    item_only = selected_item is not None
    if request.method == "POST":
        receipt_data, rows, errors = _update_receipt_from_request(receipt, request.POST, people, buyers)
        if not errors:
            messages.success(request, "Beleg wurde aktualisiert.")
            return redirect("receipts:receipt_list")
        for error in errors:
            messages.error(request, error)
        return render(
            request,
            "receipts/receipt_form.html",
            {
                "buyers": buyers,
                "can_delete_items": True,
                "form_title": "Artikel bearbeiten" if item_only else "Beleg bearbeiten",
                "item_only": item_only,
                "people": people,
                "markets": markets,
                "receipt": receipt_data,
                "receipt_object": receipt,
                "row_count": max(len(rows), 1),
                "rows": rows or [EditableRow(index=0)],
                "submit_label": "Änderungen speichern",
            },
        )

    rows = _editable_rows_from_receipt(receipt)
    if item_only:
        rows = [row for row in rows if row.item_id == selected_item.id]
        # A focused editor submits a one-row form. Reindex the selected receipt
        # row so its field names match row_count=1 and the parser reads item-0-*.
        rows[0].index = 0
    return render(
        request,
        "receipts/receipt_form.html",
        {
            "buyers": buyers,
            "can_delete_items": True,
            "form_title": "Artikel bearbeiten" if item_only else "Beleg bearbeiten",
            "item_only": item_only,
            "people": people,
            "markets": markets,
            "receipt": {
                "date": receipt.date.isoformat(),
                "market": receipt.market,
                "buyer": str(receipt.buyer_id),
            },
            "receipt_object": receipt,
            "row_count": len(rows),
            "rows": rows,
            "submit_label": "Änderungen speichern",
        },
    )


def receipt_delete(request, receipt_id):
    receipt = get_object_or_404(Receipt, pk=receipt_id)
    if request.method != "POST":
        return redirect("receipts:receipt_edit", receipt_id=receipt.id)
    receipt.delete()
    messages.success(request, "Beleg wurde gelöscht.")
    return redirect("receipts:receipt_list")


def import_receipts(request):
    buyers = list(_buyer_choices())
    people = list(_assignable_people())
    markets = _market_choices()
    if request.method == "POST" and request.POST.get("mode") == "save_manual":
        receipt_data, rows, errors = _parse_manual_receipt_request(
            request.POST, people, buyers
        )
        if not errors:
            messages.success(request, "Importierter Beleg wurde gespeichert.")
            return redirect("receipts:receipt_list")
        for error in errors:
            messages.error(request, error)
        return render(
            request,
            "receipts/receipt_form.html",
            {
                "buyers": buyers,
                "can_delete_items": False,
                "form_title": "Import prüfen",
                "import_review": True,
                "people": people,
                "markets": markets,
                "receipt": receipt_data,
                "row_count": max(len(rows), 1),
                "rows": rows or [EditableRow(index=0)],
                "submit_label": "Import speichern",
            },
        )

    if request.method == "POST":
        csv_text = request.POST.get("csv_text", "")
        rows = parse_import_csv(csv_text, markets)
        preview_rows = [_editable_from_parsed(index, row) for index, row in enumerate(rows)]
        if any(row.errors for row in preview_rows):
            messages.warning(request, "Einige Zeilen brauchen Korrekturen vor dem Speichern.")
        receipt_keys = {
            (row.date, row.market.casefold(), row.buyer_name.casefold())
            for row in rows
            if row.date and row.market and row.buyer_name
        }
        if len(receipt_keys) > 1:
            messages.error(
                request,
                "Eine CSV-Vorschau kann nur einen Beleg enthalten. Bitte jeden Beleg separat importieren.",
            )
            return render(
                request,
                "receipts/import.html",
                {
                    "buyers": buyers,
                    "markets": markets,
                    "receipt_import_prompt": RECEIPT_IMPORT_PROMPT,
                    "csv_text": csv_text,
                },
            )

        first_row = rows[0] if rows else ParsedImportRow(row_number=1, raw={})
        buyer = next(
            (
                person
                for person in buyers
                if person.name.casefold() == first_row.buyer_name.casefold()
            ),
            None,
        )
        for row in preview_rows:
            for error in row.errors:
                messages.error(request, f"Zeile {row.index + 1}: {error}")
        return render(
            request,
            "receipts/receipt_form.html",
            {
                "buyers": buyers,
                "can_delete_items": False,
                "form_title": "Import prüfen",
                "import_review": True,
                "people": people,
                "markets": markets,
                "receipt": {
                    "date": first_row.date.isoformat() if first_row.date else "",
                    "market": first_row.market,
                    "buyer": str(buyer.id) if buyer else "",
                },
                "row_count": len(preview_rows),
                "rows": preview_rows or [EditableRow(index=0)],
                "submit_label": "Import speichern",
            },
        )

    return render(
        request,
        "receipts/import.html",
        {"buyers": buyers, "markets": markets, "receipt_import_prompt": RECEIPT_IMPORT_PROMPT},
    )


def stats(request):
    today = timezone.localdate()
    current_month_start = today.replace(day=1)
    next_month_start = (current_month_start + timedelta(days=32)).replace(day=1)
    current_month_end = next_month_start - timedelta(days=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)

    filter_query = request.GET.copy()
    has_explicit_filters = any(name in request.GET for name in STATS_FILTER_NAMES)
    if not has_explicit_filters:
        saved_filters = request.session.get(STATS_FILTER_SESSION_KEY)
        if isinstance(saved_filters, dict):
            for name in STATS_FILTER_NAMES:
                if name in saved_filters:
                    filter_query[name] = str(saved_filters[name])

    if "date_from" not in filter_query and "date_to" not in filter_query:
        filter_query["date_from"] = current_month_start.isoformat()
        filter_query["date_to"] = current_month_end.isoformat()

    if has_explicit_filters:
        request.session[STATS_FILTER_SESSION_KEY] = {
            name: filter_query.get(name, "") for name in STATS_FILTER_NAMES
        }

    filters = _stats_filters(filter_query)
    stats_data = build_stats(filters)
    stats_data["markets"]["logo_keys"] = [
        market_logo(label) for label in stats_data["markets"]["labels"]
    ]
    stats_data["markets"]["logos"] = [
        static(f"images/market-logos/{filename}") if filename else ""
        for filename in stats_data["markets"]["logo_keys"]
    ]
    avatar_names = set(stats_data["people"]["labels"])
    avatar_names.update(row["name"] for row in stats_data["settlement"]["rows"])
    people_by_name = {person.name: person for person in Person.objects.filter(name__in=avatar_names)}

    def avatar_data(name):
        person = people_by_name.get(name)
        if not person:
            return {"url": "", "initials": name[:2].upper(), "color": "#1d6f5f", "chart_color": "#1d6f5f", "background": "#ffffff", "is_preset": False}
        return {
            "url": person.avatar_image_url,
            "initials": person.avatar_initials,
            "color": person.avatar_color,
            "chart_color": person.avatar_chart_color,
            "background": person.avatar_background,
            "is_preset": person.avatar_is_preset,
        }

    stats_data["people"]["avatars"] = [avatar_data(name) for name in stats_data["people"]["labels"]]
    stats_data["people"]["colors"] = [avatar_data(name)["chart_color"] for name in stats_data["people"]["labels"]]
    stats_data["person_month"]["colors"] = [
        avatar_data(dataset["label"])["chart_color"] for dataset in stats_data["person_month"]["datasets"]
    ]
    stats_data["people_table_rows"] = [
        {"label": label, "value": value, "avatar": avatar_data(label)}
        for label, value in stats_data["people"]["rows"]
    ]
    for row in stats_data["settlement"]["rows"]:
        row["avatar"] = avatar_data(row["name"])
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    single_month = (
        date_from
        if date_from and date_to and (date_from.year, date_from.month) == (date_to.year, date_to.month)
        else None
    )
    date_preset = {
        (current_month_start, current_month_end): "current",
        (previous_month_start, previous_month_end): "previous",
    }.get((date_from, date_to), "")
    show_settlement = bool(date_preset)
    return render(
        request,
        "receipts/stats.html",
        {
            "people": _assignable_people(),
            "buyers": Person.objects.all(),
            "categories": Category.objects.all(),
            "markets": Receipt.objects.order_by("market").values_list("market", flat=True).distinct(),
            "filters": filter_query,
            "date_preset": date_preset,
            "month_presets": {
                "current_from": current_month_start.isoformat(),
                "current_to": current_month_end.isoformat(),
                "previous_from": previous_month_start.isoformat(),
                "previous_to": previous_month_end.isoformat(),
            },
            "single_month": single_month,
            "show_settlement": show_settlement,
            "stats": stats_data,
        },
    )


def _stats_filters(query):
    filters = {
        "market": query.get("market", "").strip(),
        "buyer_id": int(query["buyer"]) if query.get("buyer") else None,
        "person_id": int(query["person"]) if query.get("person") else None,
        "category": query.get("category", "").strip(),
    }
    for key, param in [("date_from", "date_from"), ("date_to", "date_to")]:
        value = query.get(param, "")
        if value:
            try:
                filters[key] = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                filters[key] = None
        else:
            filters[key] = None
    return filters
