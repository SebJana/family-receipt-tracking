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


class CategoryViewTests(ReceiptTestCase):
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

    def test_existing_category_can_be_renamed_and_reiconed(self):
        category = Category.objects.create(name="Obst", emoji="🍎")

        response = self.client.post(reverse("receipts:categories"), {
            "action": "edit", "category_id": category.id, "name": "Früchte", "emoji": "F",
        })

        self.assertEqual(response.status_code, 302)
        category.refresh_from_db()
        self.assertEqual((category.name, category.emoji), ("Früchte", "F"))

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

    def test_new_matching_article_inherits_known_category(self):
        buyer = Person.objects.get(name="Person 1")
        category = Category.objects.create(name="Obst", emoji="🍎")
        old_receipt = Receipt.objects.create(
            date="2026-07-01", market="A", buyer=buyer
        )
        ReceiptItem.objects.create(
            receipt=old_receipt,
            article="Apfel",
            quantity=1,
            total_price_cents=100,
            category=category,
        )

        response = self.client.post(
            reverse("receipts:receipt_create"),
            {
                "date": "2026-07-02",
                "market": "B",
                "buyer": str(buyer.id),
                "row_count": "1",
                "item-0-article": "Apfel",
                "item-0-quantity": "1",
                "item-0-price": "2,00 €",
            },
        )

        self.assertEqual(response.status_code, 302)
        new_item = ReceiptItem.objects.get(receipt__market="B", article="Apfel")
        self.assertEqual(new_item.category, category)

    def test_renamed_article_uses_category_known_for_new_name(self):
        buyer = Person.objects.get(name="Person 1")
        fruit = Category.objects.create(name="Obst", emoji="🍎")
        other = Category.objects.create(name="Andere", emoji="A")
        receipt = Receipt.objects.create(date="2026-07-03", market="A", buyer=buyer)
        item = ReceiptItem.objects.create(
            receipt=receipt,
            article="Old Name",
            quantity=1,
            total_price_cents=100,
            category=other,
        )
        known_receipt = Receipt.objects.create(
            date="2026-07-02", market="B", buyer=buyer
        )
        ReceiptItem.objects.create(
            receipt=known_receipt,
            article="Apple",
            quantity=1,
            total_price_cents=100,
            category=fruit,
        )

        response = self.client.post(
            reverse("receipts:receipt_edit", args=[receipt.id]),
            {
                "date": "2026-07-03",
                "market": "A",
                "buyer": str(buyer.id),
                "row_count": "1",
                "item-0-id": str(item.id),
                "item-0-article": "Apple",
                "item-0-quantity": "1",
                "item-0-price": "1,00 €",
            },
        )

        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.category, fruit)

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
