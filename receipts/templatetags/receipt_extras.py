from django import template
from django.templatetags.static import static
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import mark_safe
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import unicodedata

from receipts.services import format_euro


register = template.Library()

MARKET_LOGOS = {
    "kaufland": "kaufland.svg",
    "rewe": "rewe.svg",
    "norma": "norma.svg",
    "netto": "netto.svg",
    "lidl": "lidl.svg",
    "aldi": "aldi.svg",
    "penny": "penny.svg",
    "dm": "dm.svg",
    "rossmann": "rossmann.svg",
    "edeka": "edeka.svg",
    "mcdonald's": "mcdonalds.svg",
    "mcdonalds": "mcdonalds.svg",
    "mc donald's": "mcdonalds.svg",
    "mc donalds": "mcdonalds.svg",
    "burger king": "burger-king.svg",
    "kfc": "kfc.svg",
    "subway": "subway.svg",
    "domino's": "dominos.svg",
    "dominos": "dominos.svg",
    "pizza hut": "pizza-hut.svg",
    "five guys": "five-guys.svg",
    "dunkin'": "dunkin.svg",
    "dunkin": "dunkin.svg",
    "lieferando": "lieferando.png",
}


@register.filter
def cents_euro(value):
    return format_euro(value or 0)


@register.filter
def quantity_int(value):
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@register.filter
def is_assigned(row, person):
    return person.name in row.assigned_names


@register.filter
def weight_for(row, person):
    return row.weights_by_name.get(person.name, 1)


@register.filter
def html_decimal(value):
    if value in (None, ""):
        return ""
    return str(value).replace(",", ".")


@register.filter
def highlight_search(value, query):
    text = str(value or "")
    needle = unicodedata.normalize("NFKC", str(query or "")).casefold()
    if not needle:
        return conditional_escape(text)

    folded_parts = []
    source_positions = []
    for index, character in enumerate(text):
        folded_character = unicodedata.normalize("NFKC", character).casefold()
        folded_parts.append(folded_character)
        source_positions.extend([index] * len(folded_character))
    folded_text = "".join(folded_parts)

    parts = []
    source_cursor = 0
    search_cursor = 0
    while (match_start := folded_text.find(needle, search_cursor)) >= 0:
        match_end = match_start + len(needle)
        source_start = source_positions[match_start]
        source_end = source_positions[match_end - 1] + 1
        parts.append(conditional_escape(text[source_cursor:source_start]))
        parts.append(format_html('<mark class="search-highlight">{}</mark>', text[source_start:source_end]))
        source_cursor = source_end
        search_cursor = match_end
    if not parts:
        return conditional_escape(text)
    parts.append(conditional_escape(text[source_cursor:]))
    return mark_safe("".join(str(part) for part in parts))


@register.filter
def market_logo(value):
    market = unicodedata.normalize("NFKC", str(value or "")).casefold()
    for retailer, filename in MARKET_LOGOS.items():
        if re.search(rf"(?<!\w){re.escape(retailer)}(?!\w)", market):
            return filename
    return ""


@register.filter
def market_logo_url(value):
    filename = market_logo(value)
    return static(f"images/market-logos/{filename}") if filename else ""
