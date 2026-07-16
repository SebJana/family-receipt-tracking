from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import unicodedata

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, ProtectedError
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Category, ItemAllocation, Person, Receipt, ReceiptItem
from .templatetags.receipt_extras import market_logo
from .services import (
    ParsedImportRow,
    build_stats,
    format_euro,
    parse_german_date,
    parse_german_decimal,
    parse_import_csv,
    parse_price_cents,
    save_import_rows,
)


AVATAR_PRESETS = [
    {"value": value, "filename": f"avatar-{value.removeprefix('preset-')}.svg", "label": label}
    for value, label in Person.AVATAR_CHOICES
    if value.startswith("preset-")
]
RECEIPT_IMPORT_PROMPT = (
    Path(__file__).resolve().parent / "prompts" / "receipt_import_prompt.txt"
).read_text(encoding="utf-8").strip()
EMOJI_CHOICES = [
    ("🍎", "apfel obst"), ("🍐", "birne obst"), ("🍊", "orange obst"), ("🍋", "zitrone obst"),
    ("🍌", "banane obst"), ("🍉", "melone obst"), ("🍇", "trauben obst"), ("🍓", "erdbeere obst"),
    ("🍒", "kirsche obst"), ("🍍", "ananas obst"), ("🥝", "kiwi obst"), ("🍅", "tomate gemüse"),
    ("🥑", "avocado gemüse"), ("🥕", "karotte möhre gemüse"), ("🌽", "mais gemüse"), ("🫑", "paprika gemüse"),
    ("🥒", "gurke gemüse"), ("🥦", "brokkoli gemüse"), ("🥬", "salat gemüse"), ("🥔", "kartoffel gemüse"),
    ("🍞", "brot backwaren"), ("🥐", "croissant backwaren"), ("🧀", "käse milchprodukte"), ("🥛", "milch getränk"),
    ("🥚", "ei eier"), ("🥩", "fleisch steak"), ("🍗", "huhn fleisch"), ("🐟", "fisch"),
    ("🍝", "nudeln pasta"), ("🍚", "reis"), ("🍕", "pizza"), ("🍲", "suppe"), ("🥫", "konserve dose"),
    ("🍫", "schokolade süßigkeiten"), ("🍬", "bonbon süßigkeiten"), ("🍪", "keks süßigkeiten"),
    ("☕", "kaffee getränk"), ("🍵", "tee getränk"), ("💧", "wasser getränk"), ("🧃", "saft getränk"),
    ("🥤", "limonade getränk"), ("🍷", "wein alkohol"), ("🍺", "bier alkohol"), ("👶", "baby kind"),
    ("🐾", "tier haustier"), ("🐶", "hund tier"), ("🐱", "katze tier"), ("💊", "medizin gesundheit apotheke"),
    ("🩹", "pflaster gesundheit"), ("🧴", "pflege kosmetik"), ("🧼", "seife reinigung"), ("🪥", "zahnpflege"),
    ("🧻", "toilettenpapier haushalt"), ("🧹", "putzen reinigung"), ("👕", "wäsche kleidung"),
    ("👟", "schuhe kleidung"), ("🏠", "haus haushalt"), ("🌱", "garten pflanze"), ("🌸", "blume pflanze"),
    ("✏️", "büro schreiben"), ("📚", "buch zeitschrift"), ("🔌", "technik elektronik"),
    ("🔋", "batterie technik"), ("🚗", "auto mobilität"), ("🎁", "geschenk"),
    ("📦", "sonstiges paket"), ("🛒", "einkauf warenkorb"),
    ("🫐", "blaubeere beere obst"), ("🥭", "mango obst"), ("🍈", "honigmelone obst"),
    ("🍏", "grüner apfel obst"), ("🍑", "pfirsich obst"), ("🥥", "kokosnuss obst"),
    ("🫒", "olive gemüse"), ("🍆", "aubergine gemüse"), ("🧅", "zwiebel gemüse"),
    ("🧄", "knoblauch gemüse"), ("🍄", "pilz gemüse"), ("🫘", "bohnen hülsenfrüchte"),
    ("🫛", "erbsen gemüse"), ("🌶️", "chili scharf gewürz"), ("🫚", "ingwer gewürz"),
    ("🥖", "baguette brot backwaren"), ("🥨", "brezel backwaren"), ("🥯", "bagel backwaren"),
    ("🧇", "waffel backwaren"), ("🥞", "pfannkuchen backwaren"), ("🧈", "butter milchprodukte"),
    ("🍖", "fleisch rippe"), ("🥓", "speck fleisch"), ("🌭", "wurst hotdog fleisch"),
    ("🍔", "burger fastfood"), ("🥪", "sandwich snack"), ("🌮", "taco essen"),
    ("🥗", "salat essen"), ("🍜", "ramen nudelsuppe"), ("🍣", "sushi fisch"),
    ("🍤", "garnele meeresfrüchte"), ("🦐", "garnele meeresfrüchte"), ("🦀", "krabbe meeresfrüchte"),
    ("🧂", "salz gewürz"), ("🫙", "glas vorrat konserviert"), ("🍯", "honig süß"),
    ("🍰", "kuchen süßigkeiten"), ("🧁", "muffin süßigkeiten"), ("🍩", "donut süßigkeiten"),
    ("🍦", "eis süßigkeiten"), ("🍿", "popcorn snack"), ("🥜", "nüsse snack"),
    ("🧋", "bubble tea getränk"), ("🫖", "teekanne tee"), ("🍾", "sekt champagner alkohol"),
    ("🥂", "sekt alkohol"), ("🍼", "babyflasche kind"), ("🧸", "spielzeug kind"),
    ("🧷", "windel baby pflege"), ("🧑‍⚕️", "arzt gesundheit"), ("🩺", "arzt gesundheit"),
    ("🌡️", "thermometer gesundheit"), ("🧽", "schwamm putzen reinigung"), ("🪣", "eimer putzen"),
    ("🧺", "wäsche haushalt"), ("🧯", "feuerlöscher haushalt"), ("🪴", "zimmerpflanze garten"),
    ("🪻", "blume garten"), ("🌿", "kräuter garten"), ("💄", "makeup kosmetik"),
    ("💅", "nagelpflege kosmetik"), ("🪒", "rasierer pflege"), ("🪮", "kamm haarpflege"),
    ("🕯️", "kerze dekoration"), ("🛏️", "bett möbel haushalt"), ("🛋️", "sofa möbel"),
    ("🍽️", "geschirr küche"), ("🍴", "besteck küche"), ("🔪", "messer küche"),
    ("🫕", "topf küche"), ("🧊", "eis tiefkühl"), ("❄️", "tiefkühl gefroren"),
    ("📱", "handy technik elektronik"), ("💻", "computer technik elektronik"), ("🎧", "kopfhörer technik"),
    ("💡", "lampe licht technik"), ("🖨️", "drucker büro technik"), ("📎", "büro klammer"),
    ("📒", "notizbuch büro"), ("🖍️", "stifte basteln"), ("🎨", "kunst basteln"),
    ("⚽", "sport fußball freizeit"), ("🏀", "sport basketball freizeit"), ("🏋️", "fitness sport"),
    ("🎮", "gaming spiel freizeit"), ("🎲", "spiel freizeit"), ("🎬", "film kino freizeit"),
    ("🎵", "musik freizeit"), ("🚲", "fahrrad mobilität"), ("🚌", "bus mobilität"),
    ("🚆", "bahn zug mobilität"), ("⛽", "tanken benzin auto"), ("✈️", "reise flug"),
    ("🏖️", "urlaub reise"), ("💰", "geld finanzen"), ("🧾", "beleg rechnung"),
    ("🏷️", "angebot rabatt einkauf"), ("🔧", "werkzeug reparatur"), ("🪛", "werkzeug reparatur"),
    ("🔨", "hammer werkzeug reparatur"), ("🐦", "vogel tier"), ("🐰", "hase tier"),
    ("🐠", "fisch haustier"), ("🌾", "getreide bio natur"), ("♻️", "recycling nachhaltig"),
]


def _has_supported_image_signature(upload):
    header = upload.read(16)
    upload.seek(0)
    return (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
        or header.startswith((b"GIF87a", b"GIF89a"))
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    )


def _is_single_category_symbol(value):
    # A category icon stays compact in receipts and charts, while joined emoji sequences
    # still count as one visible symbol for users.
    if len(value) == 1 and value.isalpha() and value == value.upper():
        return True
    if not value or any(character.isspace() or character.isalnum() for character in value):
        return False
    codepoints = [ord(character) for character in value]
    emoji_ranges = ((0x1F1E6, 0x1F1FF), (0x1F300, 0x1FAFF), (0x2600, 0x27BF), (0x2300, 0x23FF))
    emoji_bases = [codepoint for codepoint in codepoints if any(start <= codepoint <= end for start, end in emoji_ranges)]
    if not emoji_bases:
        return False
    regional = [codepoint for codepoint in codepoints if 0x1F1E6 <= codepoint <= 0x1F1FF]
    if regional:
        return len(regional) == 2 and len(emoji_bases) == 2
    return len(emoji_bases) == 1 or 0x200D in codepoints


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


def health(request):
    return HttpResponse("ok")


def categories(request):
    # Sonstiges is always available as a deliberate fallback and must not depend on
    # a user visiting the application immediately after a migration.
    Category.objects.get_or_create(
        name=Category.DEFAULT_NAME, defaults={"emoji": Category.DEFAULT_EMOJI}
    )
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "create":
            name = request.POST.get("name", "").strip()
            emoji = request.POST.get("emoji", "").strip()
            if not name or not emoji:
                messages.error(request, "Name und Emoji sind erforderlich.")
            elif not _is_single_category_symbol(emoji):
                messages.error(request, "Das Symbol muss genau ein Emoji oder ein Großbuchstabe sein.")
            elif Category.objects.filter(name__iexact=name).exists():
                messages.error(request, "Diese Kategorie gibt es bereits.")
            else:
                Category.objects.create(name=name, emoji=emoji)
                messages.success(request, "Kategorie wurde erstellt.")
        elif action == "edit":
            category = get_object_or_404(Category, pk=request.POST.get("category_id"))
            name = request.POST.get("name", "").strip()
            emoji = request.POST.get("emoji", "").strip()
            if category.is_default:
                name = Category.DEFAULT_NAME
            if not name or not emoji:
                messages.error(request, "Name und Emoji sind erforderlich.")
            elif not _is_single_category_symbol(emoji):
                messages.error(request, "Das Symbol muss genau ein Emoji oder ein Großbuchstabe sein.")
            elif Category.objects.filter(name__iexact=name).exclude(pk=category.pk).exists():
                messages.error(request, "Diese Kategorie gibt es bereits.")
            else:
                category.name = name
                category.emoji = emoji
                category.save(update_fields=["name", "emoji"])
                messages.success(request, "Kategorie wurde aktualisiert.")
        elif action in {"assign", "clear"}:
            article = request.POST.get("article", "").strip()
            category = None
            if action == "assign":
                category = get_object_or_404(Category, pk=request.POST.get("category_id"))
            # Categories describe products rather than individual purchases, so every
            # case-insensitive occurrence of an article is kept consistent.
            changed = ReceiptItem.objects.filter(article__iexact=article).update(category=category)
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                open_items = ReceiptItem.objects.filter(category__isnull=True).values("article").distinct()
                remaining = open_items.count()
                # Random order keeps repetitive categorization from feeling like a long
                # alphabetical data-cleanup task.
                next_item = open_items.order_by("?").first()
                return JsonResponse({"ok": True, "changed": changed, "remaining": remaining, "next_article": next_item["article"] if next_item else ""})
        elif action == "skip" and request.headers.get("x-requested-with") == "XMLHttpRequest":
            article = request.POST.get("article", "").strip()
            open_items = ReceiptItem.objects.filter(category__isnull=True).values("article").distinct()
            # Skipping changes presentation only, so assignments and undo history remain intact.
            next_item = open_items.exclude(article__iexact=article).order_by("?").first()
            if not next_item:
                next_item = open_items.filter(article__iexact=article).first()
            return JsonResponse({"ok": True, "next_article": next_item["article"] if next_item else ""})
        elif action == "delete":
            category = get_object_or_404(Category, pk=request.POST.get("category_id"))
            if category.is_default:
                messages.error(request, "Die Kategorie Sonstiges kann nicht gelöscht werden.")
            else:
                category.delete()
                messages.success(request, "Kategorie wurde gelöscht; ihre Artikel sind wieder offen.")
        return redirect("receipts:categories")

    category_list = list(Category.objects.all())
    for category in category_list:
        category.grouped_items = list(
            ReceiptItem.objects.filter(category=category)
            .values("article").annotate(count=Count("id")).order_by("article")
        )
    unassigned = list(
        ReceiptItem.objects.filter(category__isnull=True)
        .values("article").annotate(count=Count("id")).order_by("article")
    )
    random_item = ReceiptItem.objects.filter(category__isnull=True).values("article").distinct().order_by("?").first()
    return render(request, "receipts/categories.html", {
        "categories": category_list,
        "unassigned": unassigned,
        "unassigned_count": len(unassigned),
        "random_item": random_item,
        "emoji_choices": EMOJI_CHOICES,
    })


def receipt_list(request):
    receipts = (
        Receipt.objects.select_related("buyer")
        .prefetch_related("items__category", "items__allocations__person")
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
        needle = _normalize_search_text(article)
        receipts = [
            receipt
            for receipt in receipts
            if any(needle in _normalize_search_text(item.article) for item in receipt.items.all())
        ]

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


def receipt_create(request):
    people = list(_assignable_people())
    buyers = list(_buyer_choices())
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
                "form_title": "Beleg bearbeiten",
                "people": people,
                "receipt": receipt_data,
                "receipt_object": receipt,
                "row_count": max(len(rows), 1),
                "rows": rows or [EditableRow(index=0)],
                "submit_label": "Änderungen speichern",
            },
        )

    rows = _editable_rows_from_receipt(receipt)
    return render(
        request,
        "receipts/receipt_form.html",
        {
            "buyers": buyers,
            "can_delete_items": True,
            "form_title": "Beleg bearbeiten",
            "people": people,
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
    if request.method == "POST" and request.POST.get("mode") == "save":
        rows, errors = _parse_import_save_request(request.POST)
        if not errors:
            count = save_import_rows(rows)
            messages.success(request, f"{count} Import-Zeilen wurden gespeichert.")
            return redirect("receipts:receipt_list")
        for error in errors:
            messages.error(request, error)
        return render(
            request,
            "receipts/import.html",
            {
                "buyers": buyers,
                "receipt_import_prompt": RECEIPT_IMPORT_PROMPT,
                "preview_rows": [_editable_from_parsed(index, row) for index, row in enumerate(rows)],
                "row_count": len(rows),
                "import_total": format_euro(sum((row.total_price_cents or 0) for row in rows)),
            },
        )

    if request.method == "POST":
        csv_text = request.POST.get("csv_text", "")
        rows = parse_import_csv(csv_text)
        preview_rows = [_editable_from_parsed(index, row) for index, row in enumerate(rows)]
        if any(row.errors for row in preview_rows):
            messages.warning(request, "Einige Zeilen brauchen Korrekturen vor dem Speichern.")
        return render(
            request,
            "receipts/import.html",
            {
                "buyers": buyers,
                "receipt_import_prompt": RECEIPT_IMPORT_PROMPT,
                "preview_rows": preview_rows,
                "row_count": len(preview_rows),
                "csv_text": csv_text,
                "import_total": format_euro(sum((row.total_price_cents or 0) for row in rows)),
            },
        )

    return render(
        request,
        "receipts/import.html",
        {"buyers": buyers, "receipt_import_prompt": RECEIPT_IMPORT_PROMPT},
    )


def stats(request):
    filters = _stats_filters(request.GET)
    stats_data = build_stats(filters)
    stats_data["markets"]["logos"] = [
        market_logo(label) for label in stats_data["markets"]["labels"]
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
    today = timezone.localdate()
    current_month_start = today.replace(day=1)
    next_month_start = (current_month_start + timedelta(days=32)).replace(day=1)
    current_month_end = next_month_start - timedelta(days=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    show_settlement = (date_from, date_to) in {
        (current_month_start, current_month_end),
        (previous_month_start, previous_month_end),
    }
    return render(
        request,
        "receipts/stats.html",
        {
            "people": _assignable_people(),
            "buyers": Person.objects.all(),
            "categories": Category.objects.all(),
            "markets": Receipt.objects.order_by("market").values_list("market", flat=True).distinct(),
            "filters": request.GET,
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


def people(request):
    if request.method == "POST":
        if request.POST.get("delete_person"):
            person = get_object_or_404(Person, pk=request.POST.get("delete_person"))
            person.active = False
            person.is_deleted = True
            person.save()
            messages.success(request, "Person wurde gelöscht. Bestehende Zuordnungen bleiben erhalten.")
            return redirect("receipts:people")

        action = request.POST.get("action")
        if action == "add":
            name = request.POST.get("name", "").strip()
            if not name:
                messages.error(request, "Name fehlt.")
            else:
                try:
                    person, created = Person.objects.get_or_create(
                        name=name,
                        defaults={"active": True, "is_deleted": False},
                    )
                    if created:
                        messages.success(request, "Person wurde angelegt.")
                    elif person.is_deleted:
                        person.active = True
                        person.is_deleted = False
                        person.save()
                        messages.success(request, "Person wurde wiederhergestellt.")
                    else:
                        messages.error(request, "Diese Person existiert bereits.")
                except IntegrityError:
                    messages.error(request, "Diese Person existiert bereits.")
        elif action == "save":
            try:
                with transaction.atomic():
                    used_presets = {
                        person.avatar_choice: person.name
                        for person in Person.objects.filter(
                            is_deleted=True, avatar_choice__startswith="preset-"
                        )
                    }
                    for person in Person.objects.filter(is_deleted=False):
                        new_name = request.POST.get(f"name-{person.id}", "").strip()
                        if new_name:
                            person.name = new_name
                        person.active = request.POST.get(f"active-{person.id}") == "on"
                        avatar_choice = request.POST.get(f"avatar-choice-{person.id}", "initials")
                        valid_avatar_choices = {value for value, _label in Person.AVATAR_CHOICES}
                        if avatar_choice not in valid_avatar_choices:
                            avatar_choice = "initials"
                        if avatar_choice.startswith("preset-"):
                            if avatar_choice in used_presets:
                                raise ValidationError(
                                    f"Das Tieravatar ist bereits für {used_presets[avatar_choice]} ausgewählt."
                                )
                            used_presets[avatar_choice] = person.name
                        avatar_upload = request.FILES.get(f"avatar-upload-{person.id}")
                        if avatar_upload:
                            if avatar_upload.size > 5 * 1024 * 1024:
                                raise ValidationError(f"Avatar für {person.name} darf maximal 5 MB groß sein.")
                            if avatar_upload.content_type not in {
                                "image/png", "image/jpeg", "image/gif", "image/webp"
                            }:
                                raise ValidationError(f"Avatar für {person.name} muss PNG, JPG, GIF oder WebP sein.")
                            if not _has_supported_image_signature(avatar_upload):
                                raise ValidationError(f"Avatar für {person.name} enthält keine gültigen Bilddaten.")
                            Person._meta.get_field("avatar_upload").run_validators(avatar_upload)
                            previous_upload = person.avatar_upload.name
                            person.avatar_upload = avatar_upload
                            avatar_choice = "upload"
                            if previous_upload:
                                storage = person.avatar_upload.storage
                                transaction.on_commit(
                                    lambda name=previous_upload, file_storage=storage: file_storage.delete(name)
                                )
                        if avatar_choice == "upload" and not person.avatar_upload:
                            raise ValidationError(f"Für {person.name} wurde noch kein eigenes Avatarbild hochgeladen.")
                        person.avatar_choice = avatar_choice
                        person.save()
                messages.success(request, "Personen wurden gespeichert.")
            except IntegrityError:
                messages.error(request, "Personennamen und Tieravatare müssen eindeutig sein.")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        elif action == "delete":
            person = get_object_or_404(Person, pk=request.POST.get("person_id"))
            person.active = False
            person.is_deleted = True
            person.save()
            messages.success(request, "Person wurde gelöscht. Bestehende Zuordnungen bleiben erhalten.")
        elif action == "restore":
            person = get_object_or_404(Person, pk=request.POST.get("person_id"))
            person.active = True
            person.is_deleted = False
            person.save()
            messages.success(request, "Person wurde wiederhergestellt.")
        elif action == "hard_delete":
            person = get_object_or_404(Person, pk=request.POST.get("person_id"), is_deleted=True)
            try:
                avatar_name = person.avatar_upload.name
                avatar_storage = person.avatar_upload.storage
                person.delete()
                if avatar_name:
                    avatar_storage.delete(avatar_name)
                messages.success(request, "Person wurde endgültig gelöscht.")
            except ProtectedError:
                messages.error(
                    request,
                    "Person kann nicht endgültig gelöscht werden, weil sie noch in Belegen oder Zuordnungen verwendet wird.",
                )
        return redirect("receipts:people")
    preset_owners = {
        person.avatar_choice: person
        for person in Person.objects.filter(avatar_choice__startswith="preset-")
    }
    avatar_presets = [
        {
            **preset,
            "owner_id": preset_owners[preset["value"]].id if preset["value"] in preset_owners else None,
            "owner_name": preset_owners[preset["value"]].name if preset["value"] in preset_owners else "",
        }
        for preset in AVATAR_PRESETS
    ]
    return render(
        request,
        "receipts/people.html",
        {
            "active_people": Person.objects.filter(is_deleted=False),
            "avatar_presets": avatar_presets,
            "deleted_people": Person.objects.filter(is_deleted=True),
        },
    )


def _parse_manual_receipt_request(post, people, buyers):
    errors = []
    receipt_data = {
        "date": post.get("date", ""),
        "market": post.get("market", "").strip(),
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


def _update_receipt_from_request(receipt, post, people, buyers):
    receipt_data = {
        "date": post.get("date", ""),
        "market": post.get("market", "").strip(),
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


def _create_items_for_receipt(receipt, rows, people_by_id):
    people_by_name = {person.name: person for person in people_by_id.values()}
    for row in rows:
        item = ReceiptItem.objects.create(
            receipt=receipt,
            article=row.article,
            quantity=row.quantity,
            total_price_cents=row.total_price_cents,
            imported_raw_row=row.raw or None,
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


def _parse_import_save_request(post):
    rows = []
    errors = []
    row_count = int(post.get("row_count", "0") or 0)
    for index in range(row_count):
        prefix = f"row-{index}"
        raw = {
            "Datum": post.get(f"{prefix}-date", ""),
            "Einkaufsladen": post.get(f"{prefix}-market", ""),
            "Artikel": post.get(f"{prefix}-article", ""),
            "Anzahl": post.get(f"{prefix}-quantity", "1"),
            "Gesamtpreis": post.get(f"{prefix}-price", ""),
            "Käufer": post.get(f"{prefix}-buyer", ""),
        }
        row = ParsedImportRow(
            row_number=index + 1,
            raw=raw,
            market=raw["Einkaufsladen"].strip(),
            article=raw["Artikel"].strip(),
            buyer_name=raw["Käufer"].strip(),
        )
        try:
            row.date = parse_german_date(datetime.strptime(raw["Datum"], "%Y-%m-%d").strftime("%d.%m.%Y"))
        except ValueError:
            row.errors.append("Datum fehlt oder ist ungültig.")
        if not row.market:
            row.errors.append("Einkaufsladen fehlt.")
        if not row.article:
            row.errors.append("Artikel fehlt.")
        try:
            row.quantity = parse_german_decimal(raw["Anzahl"], default=Decimal("1")).quantize(Decimal("0.01"))
        except ValueError as exc:
            row.errors.append("Anzahl: " + str(exc))
        try:
            row.total_price_cents = parse_price_cents(raw["Gesamtpreis"])
        except ValueError as exc:
            row.errors.append("Gesamtpreis: " + str(exc))
        if not row.buyer_name:
            row.errors.append("Käufer fehlt.")
        if row.errors:
            errors.extend([f"Import-Zeile {index + 1}: {error}" for error in row.errors])
        rows.append(row)
    return rows, errors


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


def _normalize_search_text(value):
    return unicodedata.normalize("NFKC", value).casefold()
