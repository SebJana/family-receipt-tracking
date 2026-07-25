from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from ..models import Category, ItemAllocation, Person, Receipt, ReceiptItem
from ..services import (
    build_settlement,
    build_stats,
    market_choices,
    normalize_market_name,
    parse_import_csv,
    parse_price_cents,
    split_item_allocations,
)
from ..templatetags.receipt_extras import (
    highlight_search,
    market_logo,
    market_logo_url,
    quantity_int,
)


SAMPLE_CSV = """Datum;Einkaufsladen;Artikel;Anzahl;Gesamtpreis;Käufer
03.07.2026;Example Market;Snack A;1;1,99 €;Buyer 1
03.07.2026;Example Market;Drink A;2;3,98 €;Buyer 1
03.07.2026;Example Market;Shared Item;2;1,00 €;Buyer 1
"""

from .base import ReceiptTestCase


class GermanParsingTests(ReceiptTestCase):
    def test_known_markets_are_canonicalized_but_unknown_markets_are_preserved(self):
        self.assertEqual(normalize_market_name("  rewe "), "REWE")
        self.assertEqual(normalize_market_name("McDonalds"), "McDonald's")
        self.assertEqual(normalize_market_name("my   local shop"), "my local shop")
        self.assertEqual(
            normalize_market_name("my local shop", ["My Local Shop"]),
            "My Local Shop",
        )

    def test_market_choices_include_canonical_and_existing_custom_markets(self):
        choices = market_choices(["rewe", "Corner Shop"])

        self.assertIn("REWE", choices)
        self.assertIn("Corner Shop", choices)
        self.assertNotIn("rewe", choices)

    def test_csv_import_canonicalizes_known_markets(self):
        csv_text = SAMPLE_CSV.replace("Example Market", "  rewe  ")

        rows = parse_import_csv(csv_text)

        self.assertTrue(all(row.market == "REWE" for row in rows))

    def test_single_person_assignment_has_no_factor_text(self):
        buyer = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(date="2026-07-03", market="Test", buyer=buyer)
        item = ReceiptItem.objects.create(
            receipt=receipt,
            article="Single assignment",
            quantity=1,
            total_price_cents=100,
        )
        ItemAllocation.objects.create(item=item, person=buyer, weight=Decimal("0.2500"))

        self.assertEqual(item.factor_text(), "")
        self.assertEqual(item.factor_breakdown(), [])
        self.assertEqual(item.allocation_short_text(), "Pe")

    def test_equal_normalized_allocations_have_no_factor_display(self):
        people = list(Person.objects.order_by("id")[:2])
        receipt = Receipt.objects.create(date="2026-07-03", market="Test", buyer=people[0])
        item = ReceiptItem.objects.create(receipt=receipt, article="Equal", quantity=1, total_price_cents=100)
        for person in people:
            ItemAllocation.objects.create(item=item, person=person, weight=Decimal("0.5000"))

        self.assertEqual(item.factor_text(), "")
        self.assertEqual(item.factor_breakdown(), [])

    def test_unequal_allocations_have_visual_percentages(self):
        people = list(Person.objects.order_by("id")[:2])
        receipt = Receipt.objects.create(date="2026-07-03", market="Test", buyer=people[0])
        item = ReceiptItem.objects.create(receipt=receipt, article="Weighted", quantity=1, total_price_cents=300)
        ItemAllocation.objects.create(item=item, person=people[0], weight=Decimal("0.6667"))
        ItemAllocation.objects.create(item=item, person=people[1], weight=Decimal("0.3333"))

        breakdown = item.factor_breakdown()
        self.assertEqual([part["percentage"] for part in breakdown], [67, 33])
        self.assertEqual([part["short_name"] for part in breakdown], ["Pe", "Pe"])

    def test_market_logo_matching_ignores_case_and_allows_location_suffix(self):
        self.assertEqual(market_logo("rEwE Berlin"), "rewe.svg")
        self.assertEqual(market_logo("ALDI SÜD"), "aldi.svg")
        self.assertEqual(market_logo("dm"), "dm.svg")
        self.assertEqual(market_logo("Edeka Center"), "edeka.svg")
        self.assertEqual(market_logo("McDonald's Berlin"), "mcdonalds.svg")
        self.assertEqual(market_logo("Mc Donalds Restaurant"), "mcdonalds.svg")
        self.assertEqual(market_logo("BURGER KING 1284"), "burger-king.svg")
        self.assertEqual(market_logo("Domino's Pizza"), "dominos.svg")
        self.assertEqual(market_logo("Dunkin Donuts"), "dunkin.svg")
        self.assertEqual(market_logo("Lieferando.de"), "lieferando.png")
        self.assertEqual(market_logo("Unbekannter Markt"), "")

    def test_market_logo_url_uses_static_asset_resolution(self):
        self.assertEqual(
            market_logo_url("REWE"), static("images/market-logos/rewe.svg")
        )
        self.assertEqual(market_logo_url("Unbekannter Markt"), "")

    def test_monthly_settlement_calculates_who_pays_whom(self):
        settlement = build_settlement(
            {"Person 1": 1000, "Person 2": 0},
            {"Person 1": 500, "Person 2": 500},
        )

        self.assertEqual(
            settlement["transfers"],
            [{"from": "Person 2", "to": "Person 1", "amount": "5,00 €"}],
        )
        rows = {row["name"]: row for row in settlement["rows"]}
        self.assertEqual(rows["Person 1"]["paid"], "10,00 €")
        self.assertEqual(rows["Person 2"]["owed"], "5,00 €")

    def test_search_highlight_matches_inside_word_and_ignores_case(self):
        highlighted = str(highlight_search("Große KAFFEEDose", "feeDo"))

        self.assertEqual(
            highlighted,
            'Große KAF<mark class="search-highlight">FEEDo</mark>se',
        )

    def test_parse_german_price_to_cents(self):
        self.assertEqual(parse_price_cents("1,99 €"), 199)
        self.assertEqual(parse_price_cents("0,00 €"), 0)
        self.assertEqual(parse_price_cents("-0,25 €"), -25)

    def test_quantity_display_is_integer(self):
        self.assertEqual(quantity_int(Decimal("2.00")), 2)
        self.assertEqual(quantity_int(Decimal("2.40")), 2)
        self.assertEqual(quantity_int(Decimal("2.50")), 3)

    def test_parse_import_csv_without_assignments(self):
        rows = parse_import_csv(SAMPLE_CSV)

        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.valid for row in rows))
        self.assertEqual(rows[0].date.isoformat(), "2026-07-03")
        self.assertEqual(rows[0].assigned_names, [])
        self.assertEqual(rows[0].weights_by_name, {})

    def test_import_ignores_legacy_assignment_columns(self):
        csv_text = """Datum;Einkaufsladen;Artikel;Anzahl;Gesamtpreis;Zuordnung;Käufer;Faktoren
03.07.2026;Example Market;Test;1;3,00 €;Unknown Person;Buyer 1;Unknown Person=2
"""
        rows = parse_import_csv(csv_text)

        self.assertTrue(rows[0].valid)
        self.assertEqual(rows[0].assigned_names, [])
        self.assertEqual(rows[0].weights_by_name, {})


class AllocationTests(ReceiptTestCase):
    def test_equal_split_rounds_to_total(self):
        buyer = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(date="2026-07-03", market="Example Market", buyer=buyer)
        item = ReceiptItem.objects.create(
            receipt=receipt,
            article="Tomatoes",
            quantity=Decimal("1"),
            total_price_cents=100,
        )
        allocations = [
            ItemAllocation.objects.create(item=item, person=Person.objects.get(name="Person 1"), weight=1),
            ItemAllocation.objects.create(item=item, person=Person.objects.get(name="Person 2"), weight=1),
            ItemAllocation.objects.create(item=item, person=Person.objects.get(name="Person 3"), weight=1),
        ]

        split = ItemAllocation.split_cents(100, allocations)

        self.assertEqual(sum(split), 100)
        self.assertEqual(sorted(split), [33, 33, 34])

    def test_weighted_split(self):
        buyer = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(date="2026-07-03", market="Example Market", buyer=buyer)
        item = ReceiptItem.objects.create(
            receipt=receipt,
            article="Drink",
            quantity=Decimal("1"),
            total_price_cents=300,
        )
        allocations = [
            ItemAllocation.objects.create(item=item, person=Person.objects.get(name="Person 1"), weight=2),
            ItemAllocation.objects.create(item=item, person=Person.objects.get(name="Person 2"), weight=1),
        ]

        self.assertEqual(ItemAllocation.split_cents(300, allocations), [200, 100])

    def test_negative_split(self):
        buyer = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(date="2026-07-03", market="Example Market", buyer=buyer)
        item = ReceiptItem.objects.create(
            receipt=receipt,
            article="Deposit Return",
            quantity=Decimal("1"),
            total_price_cents=-300,
        )
        allocations = [
            ItemAllocation.objects.create(item=item, person=Person.objects.get(name="Person 1"), weight=2),
            ItemAllocation.objects.create(item=item, person=Person.objects.get(name="Person 2"), weight=1),
        ]

        self.assertEqual(ItemAllocation.split_cents(-300, allocations), [-200, -100])

    def test_unassigned_item_splits_across_all_active_people(self):
        buyer = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(date="2026-07-03", market="Example Market", buyer=buyer)
        item = ReceiptItem.objects.create(
            receipt=receipt,
            article="Shared Item",
            quantity=Decimal("1"),
            total_price_cents=300,
        )
        people = list(Person.objects.filter(active=True).order_by("name"))

        split = split_item_allocations(item, people)

        self.assertEqual([(allocation.person.name, cents) for allocation, cents in split], [
            ("Person 1", 100),
            ("Person 2", 100),
            ("Person 3", 100),
        ])

    def test_stats_round_unassigned_items_after_aggregating(self):
        buyer = Person.objects.get(name="Person 1")
        Person.objects.create(name="Person 4", active=True)
        receipt = Receipt.objects.create(date="2026-07-03", market="Example Market", buyer=buyer)
        for index in range(101):
            ReceiptItem.objects.create(
                receipt=receipt,
                article=f"Cent Item {index}",
                quantity=Decimal("1"),
                total_price_cents=1,
            )

        stats = build_stats({})
        cents = [round(value * 100) for value in stats["people"]["values"]]

        self.assertEqual(sum(cents), 101)
        self.assertLessEqual(max(cents) - min(cents), 1)
