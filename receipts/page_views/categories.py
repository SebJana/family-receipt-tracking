from django.contrib import messages
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..models import Category, ReceiptItem


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
