CANONICAL_MARKETS = (
    "ALDI",
    "Burger King",
    "dm",
    "Domino's",
    "Dunkin'",
    "EDEKA",
    "Five Guys",
    "Kaufland",
    "KFC",
    "Lidl",
    "Lieferando",
    "McDonald's",
    "Netto",
    "NORMA",
    "PENNY",
    "Pizza Hut",
    "REWE",
    "ROSSMANN",
    "Subway",
)


def _market_key(value):
    return " ".join((value or "").strip().split()).casefold()


MARKET_ALIASES = {
    _market_key(alias): canonical
    for canonical, aliases in {
        "ALDI": ("ALDI", "Aldi"),
        "Burger King": ("Burger King",),
        "dm": ("dm", "dm-drogerie markt", "dm drogerie markt"),
        "Domino's": ("Domino's", "Dominos", "Domino's Pizza", "Dominos Pizza"),
        "Dunkin'": ("Dunkin'", "Dunkin", "Dunkin' Donuts", "Dunkin Donuts"),
        "EDEKA": ("EDEKA", "Edeka"),
        "Five Guys": ("Five Guys",),
        "Kaufland": ("Kaufland",),
        "KFC": ("KFC",),
        "Lidl": ("Lidl",),
        "Lieferando": ("Lieferando", "Lieferando.de"),
        "McDonald's": ("McDonald's", "McDonalds", "Mc Donald's", "Mc Donalds"),
        "Netto": ("Netto", "Netto Marken-Discount", "Netto Marken Discount"),
        "NORMA": ("NORMA", "Norma"),
        "PENNY": ("PENNY", "Penny"),
        "Pizza Hut": ("Pizza Hut",),
        "REWE": ("REWE", "Rewe"),
        "ROSSMANN": ("ROSSMANN", "Rossmann"),
        "Subway": ("Subway",),
    }.items()
    for alias in aliases
}


def normalize_market_name(value, known_markets=()):
    """Return a canonical known name, while preserving genuinely new market names."""
    cleaned = " ".join((value or "").strip().split())
    if not cleaned:
        return ""
    key = _market_key(cleaned)
    if key in MARKET_ALIASES:
        return MARKET_ALIASES[key]
    existing_by_key = {}
    for market in known_markets:
        if market:
            existing_by_key.setdefault(_market_key(market), market)
    return existing_by_key.get(key, cleaned)


def market_choices(existing_markets=()):
    choices = {
        normalize_market_name(market, existing_markets)
        for market in (*CANONICAL_MARKETS, *existing_markets)
        if market
    }
    return sorted(choices, key=str.casefold)
