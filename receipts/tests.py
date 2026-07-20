from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Category, ItemAllocation, Person, Receipt, ReceiptItem
from .services import (
    build_settlement,
    build_stats,
    market_choices,
    normalize_market_name,
    parse_import_csv,
    parse_price_cents,
    split_item_allocations,
)
from .templatetags.receipt_extras import highlight_search, market_logo, quantity_int


SAMPLE_CSV = """Datum;Einkaufsladen;Artikel;Anzahl;Gesamtpreis;Käufer
03.07.2026;Example Market;Snack A;1;1,99 €;Buyer 1
03.07.2026;Example Market;Drink A;2;3,98 €;Buyer 1
03.07.2026;Example Market;Shared Item;2;1,00 €;Buyer 1
"""


class ReceiptTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name in ["Person 1", "Person 2", "Person 3"]:
            Person.objects.create(name=name, active=True)


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


class ViewTests(ReceiptTestCase):
    def test_receipt_list_market_filter_shows_market_logos(self):
        buyer = Person.objects.get(name="Person 1")
        Receipt.objects.create(date="2026-07-01", market="REWE", buyer=buyer)
        Receipt.objects.create(date="2026-07-02", market="Corner Shop", buyer=buyer)

        response = self.client.get(reverse("receipts:receipt_list"))

        self.assertContains(response, 'id="receipt-filter-market"')
        self.assertContains(response, 'data-name="REWE"')
        self.assertContains(response, "images/market-logos/rewe.svg")
        self.assertContains(response, 'data-name="Corner Shop"')
        self.assertContains(response, 'class="market-option-logo is-fallback"', html=False)

    def test_new_receipt_market_is_editable_with_known_market_suggestions(self):
        Receipt.objects.create(
            date="2026-07-01",
            market="Corner Shop",
            buyer=Person.objects.get(name="Person 1"),
        )

        response = self.client.get(reverse("receipts:receipt_create"))

        self.assertContains(response, 'role="combobox"')
        self.assertContains(response, 'data-name="REWE"')
        self.assertContains(response, 'data-name="Corner Shop"')
        self.assertContains(response, 'class="market-option-logo is-fallback"', html=False)

    def test_market_and_people_stats_are_sorted_by_spending_descending(self):
        person_1 = Person.objects.get(name="Person 1")
        person_2 = Person.objects.get(name="Person 2")
        low_receipt = Receipt.objects.create(date="2026-07-03", market="Low Market", buyer=person_1)
        high_receipt = Receipt.objects.create(date="2026-07-03", market="High Market", buyer=person_2)
        low_item = ReceiptItem.objects.create(
            receipt=low_receipt, article="Low", quantity=1, total_price_cents=200
        )
        high_item = ReceiptItem.objects.create(
            receipt=high_receipt, article="High", quantity=1, total_price_cents=900
        )
        ItemAllocation.objects.create(item=low_item, person=person_1, weight=1)
        ItemAllocation.objects.create(item=high_item, person=person_2, weight=1)

        stats = build_stats({})

        self.assertEqual(stats["markets"]["labels"], ["High Market", "Low Market"])
        self.assertEqual(stats["markets"]["values"], [9.0, 2.0])
        self.assertEqual(stats["people"]["labels"], ["Person 2", "Person 1"])
        self.assertEqual(stats["people"]["values"], [9.0, 2.0])

    def test_category_skip_changes_item_without_assigning_or_clearing_undo_state(self):
        buyer = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(date="2026-07-03", market="A", buyer=buyer)
        ReceiptItem.objects.create(receipt=receipt, article="First", quantity=1, total_price_cents=100)
        ReceiptItem.objects.create(receipt=receipt, article="Second", quantity=1, total_price_cents=100)

        response = self.client.post(
            reverse("receipts:categories"), {"action": "skip", "article": "First"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.json()["next_article"], "Second")
        self.assertEqual(ReceiptItem.objects.filter(category__isnull=True).count(), 2)

    def test_stats_use_the_intersection_of_all_filters_for_top_articles(self):
        buyer_a = Person.objects.get(name="Person 1")
        buyer_b = Person.objects.get(name="Person 2")
        selected_person = Person.objects.get(name="Person 3")
        fruit = Category.objects.create(name="Obst", emoji="🍎")
        other = Category.objects.create(name="Andere", emoji="A")

        matching_receipt = Receipt.objects.create(date="2026-07-03", market="A", buyer=buyer_a)
        matching_item = ReceiptItem.objects.create(receipt=matching_receipt, article="Matching Apple", quantity=1, total_price_cents=600, category=fruit)
        ItemAllocation.objects.create(item=matching_item, person=buyer_a, weight=1)
        ItemAllocation.objects.create(item=matching_item, person=selected_person, weight=1)

        wrong_buyer = Receipt.objects.create(date="2026-07-03", market="A", buyer=buyer_b)
        wrong_buyer_item = ReceiptItem.objects.create(receipt=wrong_buyer, article="Wrong Buyer", quantity=1, total_price_cents=900, category=fruit)
        ItemAllocation.objects.create(item=wrong_buyer_item, person=selected_person, weight=1)

        wrong_category = Receipt.objects.create(date="2026-07-03", market="A", buyer=buyer_a)
        wrong_category_item = ReceiptItem.objects.create(receipt=wrong_category, article="Wrong Category", quantity=1, total_price_cents=800, category=other)
        ItemAllocation.objects.create(item=wrong_category_item, person=selected_person, weight=1)

        stats = build_stats({
            "buyer_id": buyer_a.id, "person_id": selected_person.id,
            "category": str(fruit.id), "market": "A",
            "date_from": date(2026, 7, 1), "date_to": date(2026, 7, 31),
        })

        self.assertEqual(stats["top_articles"], [("Matching Apple", "3,00 €")])
        self.assertEqual(stats["monthly"]["total"], "3,00 €")

    def test_category_stats_are_sorted_colored_badged_and_filterable(self):
        buyer = Person.objects.get(name="Person 1")
        fruit = Category.objects.create(name="Obst", emoji="🍎")
        vegetables = Category.objects.create(name="Gemüse", emoji="🥦")
        receipt = Receipt.objects.create(date="2026-07-03", market="A", buyer=buyer)
        ReceiptItem.objects.create(receipt=receipt, article="Apple", quantity=1, total_price_cents=500, category=fruit)
        ReceiptItem.objects.create(receipt=receipt, article="Broccoli", quantity=1, total_price_cents=200, category=vegetables)

        stats = build_stats({})["categories"]
        filtered = build_stats({"category": str(fruit.id)})["categories"]
        response = self.client.get(reverse("receipts:stats"), {"category": str(fruit.id)})

        self.assertEqual(stats["values"], [5.0, 2.0])
        self.assertEqual([badge["initials"] for badge in stats["badges"]], ["🍎", "🥦"])
        self.assertEqual(stats["colors"], ["#df4b4b", "#57a653"])
        self.assertEqual(filtered["labels"], ["🍎 Obst"])
        self.assertNotContains(response, 'data-category-emojis')
        self.assertContains(response, 'name="category"')

    def test_person_filter_hides_person_charts_and_settlement(self):
        person = Person.objects.get(name="Person 1")
        response = self.client.get(reverse("receipts:stats"), {
            "person": person.id, "date_from": "2026-07-01", "date_to": "2026-07-31",
        })

        self.assertNotContains(response, "Personen pro Monat")
        self.assertNotContains(response, "Anteil pro Person")
        self.assertNotContains(response, "Monatsausgleich")

    def test_existing_category_can_be_renamed_and_reiconed(self):
        category = Category.objects.create(name="Obst", emoji="🍎")

        response = self.client.post(reverse("receipts:categories"), {
            "action": "edit", "category_id": category.id, "name": "Früchte", "emoji": "F",
        })

        self.assertEqual(response.status_code, 302)
        category.refresh_from_db()
        self.assertEqual((category.name, category.emoji), ("Früchte", "F"))

    def test_sonstiges_can_be_reiconed_but_not_renamed(self):
        self.client.get(reverse("receipts:categories"))
        category = Category.objects.get(name="Sonstiges")

        self.client.post(reverse("receipts:categories"), {
            "action": "edit", "category_id": category.id, "name": "Other", "emoji": "❓",
        })

        category.refresh_from_db()
        self.assertEqual((category.name, category.emoji), ("Sonstiges", "❓"))

    def test_category_symbol_must_be_one_emoji_or_uppercase_letter(self):
        url = reverse("receipts:categories")
        self.client.post(url, {"action": "create", "name": "Invalid", "emoji": "12"})
        self.client.post(url, {"action": "create", "name": "Letter", "emoji": "A"})
        self.client.post(url, {"action": "create", "name": "Emoji", "emoji": "🧑‍⚕️"})

        self.assertFalse(Category.objects.filter(name="Invalid").exists())
        self.assertTrue(Category.objects.filter(name="Letter", emoji="A").exists())
        self.assertTrue(Category.objects.filter(name="Emoji", emoji="🧑‍⚕️").exists())

    def test_categories_always_include_protected_sonstiges(self):
        response = self.client.get(reverse("receipts:categories"))
        category = Category.objects.get(name="Sonstiges")

        self.assertEqual(category.emoji, "📦")
        self.assertContains(response, "Standard")
        self.client.post(reverse("receipts:categories"), {"action": "delete", "category_id": category.id})
        self.assertTrue(Category.objects.filter(pk=category.id).exists())

    def test_category_assignment_updates_every_matching_article(self):
        buyer = Person.objects.get(name="Person 1")
        category = Category.objects.create(name="Obst", emoji="🍎")
        for market in ("A", "B"):
            receipt = Receipt.objects.create(date="2026-07-03", market=market, buyer=buyer)
            ReceiptItem.objects.create(receipt=receipt, article="Apfel", quantity=1, total_price_cents=100)

        response = self.client.post(
            reverse("receipts:categories"),
            {"action": "assign", "article": "Apfel", "category_id": category.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ReceiptItem.objects.filter(category=category).count(), 2)
        self.assertEqual(response.json()["remaining"], 0)

    def test_category_appears_on_receipt_and_in_filtered_stats(self):
        buyer = Person.objects.get(name="Person 1")
        category = Category.objects.create(name="Gemüse", emoji="🥕")
        receipt = Receipt.objects.create(date="2026-07-03", market="A", buyer=buyer)
        ReceiptItem.objects.create(receipt=receipt, article="Karotte", quantity=1, total_price_cents=250, category=category)

        receipt_response = self.client.get(reverse("receipts:receipt_list"))
        stats = build_stats({"market": "A"})

        self.assertContains(receipt_response, "🥕")
        self.assertEqual(stats["categories"]["labels"], ["🥕 Gemüse"])
        self.assertEqual(stats["categories"]["values"], [2.5])

    def test_uncategorized_items_are_presented_as_unknown(self):
        buyer = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(date="2026-07-03", market="A", buyer=buyer)
        ReceiptItem.objects.create(receipt=receipt, article="Mystery", quantity=1, total_price_cents=125)

        response = self.client.get(reverse("receipts:receipt_list"))
        stats = build_stats({})

        self.assertContains(response, 'title="Unbekannt"')
        self.assertEqual(stats["categories"]["labels"], ["? Unbekannt"])

    def test_people_can_select_preset_avatar(self):
        person = Person.objects.get(name="Person 1")
        payload = {"action": "save"}
        for current in Person.objects.all():
            payload[f"name-{current.id}"] = current.name
            payload[f"active-{current.id}"] = "on"
            payload[f"avatar-choice-{current.id}"] = "preset-7" if current == person else "initials"

        response = self.client.post(reverse("receipts:people"), payload)

        self.assertEqual(response.status_code, 302)
        person.refresh_from_db()
        self.assertEqual(person.avatar_choice, "preset-7")
        self.assertTrue(person.avatar_image_url.endswith("images/avatars/avatar-7.svg"))

    def test_animal_avatar_cannot_be_assigned_to_two_people(self):
        payload = {"action": "save"}
        people = list(Person.objects.all())
        for current in people:
            payload[f"name-{current.id}"] = current.name
            payload[f"active-{current.id}"] = "on"
            payload[f"avatar-choice-{current.id}"] = "preset-3" if current in people[:2] else "initials"

        response = self.client.post(reverse("receipts:people"), payload, follow=True)

        self.assertContains(response, "Tieravatar ist bereits")
        self.assertFalse(Person.objects.filter(avatar_choice="preset-3").exists())

    def test_assigned_animal_avatar_is_disabled_for_other_people(self):
        owner = Person.objects.get(name="Person 1")
        owner.avatar_choice = "preset-3"
        owner.save()

        response = self.client.get(reverse("receipts:people"))
        preset = next(item for item in response.context["avatar_presets"] if item["value"] == "preset-3")

        self.assertEqual(preset["owner_id"], owner.id)
        self.assertEqual(preset["owner_name"], owner.name)
        self.assertContains(
            response,
            f"Bereits von {owner.name} verwendet",
            count=Person.objects.filter(is_deleted=False).exclude(pk=owner.pk).count(),
        )

    def test_people_can_upload_one_avatar_image(self):
        person = Person.objects.get(name="Person 1")
        gif = SimpleUploadedFile(
            "avatar.gif",
            b"GIF89a" + b"\x00" * 32,
            content_type="image/gif",
        )
        payload = {"action": "save", f"avatar-upload-{person.id}": gif}
        for current in Person.objects.all():
            payload[f"name-{current.id}"] = current.name
            payload[f"active-{current.id}"] = "on"
            payload[f"avatar-choice-{current.id}"] = "upload" if current == person else "initials"

        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            response = self.client.post(reverse("receipts:people"), payload)
            person.refresh_from_db()

            self.assertEqual(response.status_code, 302)
            self.assertEqual(person.avatar_choice, "upload")
            self.assertTrue(person.avatar_image_url.startswith("/media/avatars/"))
            self.assertTrue(Path(media_root, person.avatar_upload.name).exists())

    def test_people_page_offers_thirty_one_animal_presets_and_initials(self):
        response = self.client.get(reverse("receipts:people"))

        self.assertContains(response, "avatar-1.svg")
        self.assertContains(response, "avatar-24.svg")
        self.assertContains(response, "avatar-31.svg")
        self.assertContains(response, "Känguru")
        self.assertContains(response, "Schildkröte")
        self.assertContains(response, "Initialen")
        self.assertContains(response, "avatar-dialog-1")

    def test_receipt_article_search_matches_inside_words_and_ignores_case(self):
        buyer = Person.objects.get(name="Person 1")
        matching_receipt = Receipt.objects.create(date="2026-07-03", market="A", buyer=buyer)
        ReceiptItem.objects.create(
            receipt=matching_receipt,
            article="Große KAFFEEDose",
            quantity=1,
            total_price_cents=500,
        )
        other_receipt = Receipt.objects.create(date="2026-07-04", market="B", buyer=buyer)
        ReceiptItem.objects.create(
            receipt=other_receipt,
            article="Tee",
            quantity=1,
            total_price_cents=300,
        )

        response = self.client.get(reverse("receipts:receipt_list"), {"article": "feeDo"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Große KAF<mark class="search-highlight">FEEDo</mark>se')
        self.assertNotContains(response, "Tee")
        self.assertNotContains(response, "Filter anwenden")
        self.assertContains(response, f'href="#receipt-{matching_receipt.id}"')
        self.assertContains(response, "person-avatar-small")

    def test_stats_page_has_no_article_filter(self):
        response = self.client.get(reverse("receipts:stats"))

        self.assertNotContains(response, 'name="article"')
        self.assertNotContains(response, "Filter anwenden")

    def test_receipt_create_view(self):
        person_1 = Person.objects.get(name="Person 1")
        person_2 = Person.objects.get(name="Person 2")
        response = self.client.post(
            reverse("receipts:receipt_create"),
            {
                "date": "2026-07-03",
                "market": "Example Market",
                "buyer": str(person_1.id),
                "row_count": "1",
                "item-0-article": "Drink",
                "item-0-quantity": "2",
                "item-0-price": "3,98 €",
                "item-0-persons": [str(person_1.id), str(person_2.id)],
                f"item-0-weight-{person_1.id}": "2",
                f"item-0-weight-{person_2.id}": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ReceiptItem.objects.count(), 1)
        self.assertEqual(ItemAllocation.objects.count(), 2)
        weights = {
            allocation.person.name: allocation.weight
            for allocation in ItemAllocation.objects.select_related("person")
        }
        self.assertEqual(weights["Person 1"], Decimal("0.6667"))
        self.assertEqual(weights["Person 2"], Decimal("0.3333"))
        self.assertEqual(sum(weights.values(), Decimal("0")), Decimal("1.0000"))

    def test_import_preview_and_stats_views(self):
        response = self.client.post(reverse("receipts:import"), {"csv_text": SAMPLE_CSV})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vorschau")
        self.assertContains(response, "Bereit")
        self.assertContains(response, "Summe: 6,97 €")
        self.assertNotContains(response, "Zuordnung und Faktoren")

        stats_response = self.client.get(reverse("receipts:stats"))
        self.assertEqual(stats_response.status_code, 200)
        self.assertContains(stats_response, "Statistiken")
        self.assertContains(stats_response, "data-person-avatars")

    def test_import_page_has_copyable_csv_prompt_matching_parser_columns(self):
        response = self.client.get(reverse("receipts:import"))
        prompt_file = Path(__file__).resolve().parent / "prompts" / "receipt_import_prompt.txt"

        self.assertContains(response, 'id="receipt-import-prompt"')
        self.assertContains(response, 'data-copy-target="receipt-import-prompt"')
        self.assertContains(response, "Datum;Einkaufsladen;Artikel;Anzahl;Gesamtpreis;Käufer")
        self.assertContains(response, "keine Markdown-Tabelle")
        self.assertEqual(response.context["receipt_import_prompt"], prompt_file.read_text(encoding="utf-8").strip())

    def test_stats_person_charts_use_avatar_colors(self):
        person = Person.objects.get(name="Person 1")
        person.avatar_choice = "preset-3"
        person.save()
        receipt = Receipt.objects.create(date="2026-07-03", market="Example Market", buyer=person)
        ReceiptItem.objects.create(receipt=receipt, article="Test", quantity=1, total_price_cents=100)

        response = self.client.get(reverse("receipts:stats"))

        self.assertContains(response, Person.AVATAR_CHART_COLORS[2])

    def test_import_save_creates_unassigned_items(self):
        response = self.client.post(reverse("receipts:import"), {"csv_text": SAMPLE_CSV})
        self.assertEqual(response.status_code, 200)

        save_response = self.client.post(
            reverse("receipts:import"),
            {
                "mode": "save",
                "row_count": "1",
                "row-0-date": "2026-07-03",
                "row-0-market": "Example Market",
                "row-0-buyer": "Buyer 1",
                "row-0-article": "Snack A",
                "row-0-quantity": "1",
                "row-0-price": "1,99 €",
            },
        )

        self.assertEqual(save_response.status_code, 302)
        self.assertEqual(ReceiptItem.objects.count(), 1)
        self.assertEqual(ItemAllocation.objects.count(), 0)

    def test_receipt_edit_updates_item_and_allocations(self):
        person_1 = Person.objects.get(name="Person 1")
        person_2 = Person.objects.get(name="Person 2")
        receipt = Receipt.objects.create(
            date="2026-07-03",
            market="Example Market",
            buyer=person_1,
        )
        item = ReceiptItem.objects.create(
            receipt=receipt,
            article="Old Item",
            quantity=Decimal("1"),
            total_price_cents=100,
        )

        response = self.client.post(
            reverse("receipts:receipt_edit", args=[receipt.id]),
            {
                "date": "2026-07-04",
                "market": "Updated Market",
                "buyer": str(person_2.id),
                "row_count": "1",
                "item-0-id": str(item.id),
                "item-0-article": "Updated Item",
                "item-0-quantity": "2",
                "item-0-price": "-0,25 €",
                "item-0-persons": [str(person_1.id), str(person_2.id)],
                f"item-0-weight-{person_1.id}": "2",
                f"item-0-weight-{person_2.id}": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        receipt.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(receipt.market, "Updated Market")
        self.assertEqual(receipt.buyer, person_2)
        self.assertEqual(item.article, "Updated Item")
        self.assertEqual(item.total_price_cents, -25)
        self.assertEqual(ItemAllocation.objects.count(), 2)

    def test_receipt_edit_deletes_item(self):
        person_1 = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(
            date="2026-07-03",
            market="Example Market",
            buyer=person_1,
        )
        item_1 = ReceiptItem.objects.create(
            receipt=receipt,
            article="Keep",
            quantity=Decimal("1"),
            total_price_cents=100,
        )
        item_2 = ReceiptItem.objects.create(
            receipt=receipt,
            article="Delete",
            quantity=Decimal("1"),
            total_price_cents=100,
        )

        response = self.client.post(
            reverse("receipts:receipt_edit", args=[receipt.id]),
            {
                "date": "2026-07-03",
                "market": "Example Market",
                "buyer": str(person_1.id),
                "row_count": "2",
                "item-0-id": str(item_1.id),
                "item-0-article": "Keep",
                "item-0-quantity": "1",
                "item-0-price": "1,00 €",
                "item-1-id": str(item_2.id),
                "item-1-delete": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ReceiptItem.objects.filter(id=item_1.id).exists())
        self.assertFalse(ReceiptItem.objects.filter(id=item_2.id).exists())

    def test_receipt_delete_view(self):
        person_1 = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(
            date="2026-07-03",
            market="Example Market",
            buyer=person_1,
        )
        ReceiptItem.objects.create(
            receipt=receipt,
            article="Item",
            quantity=Decimal("1"),
            total_price_cents=100,
        )

        response = self.client.post(reverse("receipts:receipt_delete", args=[receipt.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Receipt.objects.count(), 0)
        self.assertEqual(ReceiptItem.objects.count(), 0)

    def test_people_soft_delete_hides_person_from_new_assignments(self):
        person_2 = Person.objects.get(name="Person 2")

        response = self.client.post(
            reverse("receipts:people"),
            {"delete_person": str(person_2.id)},
        )

        self.assertEqual(response.status_code, 302)
        person_2.refresh_from_db()
        self.assertFalse(person_2.active)
        self.assertTrue(person_2.is_deleted)

        create_response = self.client.get(reverse("receipts:receipt_create"))
        self.assertContains(create_response, "Person 1")
        self.assertNotContains(create_response, "Person 2")

    def test_deleted_person_assignment_is_preserved_on_receipt_edit(self):
        person_1 = Person.objects.get(name="Person 1")
        person_2 = Person.objects.get(name="Person 2")
        receipt = Receipt.objects.create(
            date="2026-07-03",
            market="Example Market",
            buyer=person_1,
        )
        item = ReceiptItem.objects.create(
            receipt=receipt,
            article="Historical Item",
            quantity=Decimal("1"),
            total_price_cents=300,
        )
        ItemAllocation.objects.create(item=item, person=person_2, weight=2)
        person_2.active = False
        person_2.is_deleted = True
        person_2.save()

        edit_response = self.client.get(reverse("receipts:receipt_edit", args=[receipt.id]))
        self.assertContains(edit_response, "Historische Zuordnung")
        self.assertContains(edit_response, "Person 2")

        response = self.client.post(
            reverse("receipts:receipt_edit", args=[receipt.id]),
            {
                "date": "2026-07-03",
                "market": "Updated Market",
                "buyer": str(person_1.id),
                "row_count": "1",
                "item-0-id": str(item.id),
                "item-0-article": "Historical Item",
                "item-0-quantity": "1",
                "item-0-price": "3,00 €",
                "item-0-locked-persons": [str(person_2.id)],
                f"item-0-locked-weight-{person_2.id}": "2",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ItemAllocation.objects.filter(item=item, person=person_2, weight=2).exists()
        )

    def test_people_restore(self):
        person_2 = Person.objects.get(name="Person 2")
        person_2.active = False
        person_2.is_deleted = True
        person_2.save()

        response = self.client.post(
            reverse("receipts:people"),
            {"action": "restore", "person_id": str(person_2.id)},
        )

        self.assertEqual(response.status_code, 302)
        person_2.refresh_from_db()
        self.assertTrue(person_2.active)
        self.assertFalse(person_2.is_deleted)

    def test_deleted_people_show_hard_delete_action(self):
        person_2 = Person.objects.get(name="Person 2")
        person_2.active = False
        person_2.is_deleted = True
        person_2.save()

        response = self.client.get(reverse("receipts:people"))

        self.assertContains(response, "Endgültig löschen")

    def test_deleted_person_can_be_hard_deleted_when_unused(self):
        person_2 = Person.objects.get(name="Person 2")
        person_2.active = False
        person_2.is_deleted = True
        person_2.save()

        response = self.client.post(
            reverse("receipts:people"),
            {"action": "hard_delete", "person_id": str(person_2.id)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Person.objects.filter(id=person_2.id).exists())

    def test_referenced_deleted_person_cannot_be_hard_deleted(self):
        person_2 = Person.objects.get(name="Person 2")
        Receipt.objects.create(date="2026-07-03", market="Example Market", buyer=person_2)
        person_2.active = False
        person_2.is_deleted = True
        person_2.save()

        response = self.client.post(
            reverse("receipts:people"),
            {"action": "hard_delete", "person_id": str(person_2.id)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Person.objects.filter(id=person_2.id).exists())
        self.assertTrue(Receipt.objects.filter(buyer=person_2).exists())

    def test_health_view(self):
        response = self.client.get(reverse("receipts:health"))
        self.assertEqual(response.content, b"ok")
