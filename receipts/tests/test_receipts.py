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


class ReceiptViewTests(ReceiptTestCase):
    def test_receipt_list_market_filter_shows_market_logos(self):
        buyer = Person.objects.get(name="Person 1")
        Receipt.objects.create(date="2026-07-01", market="REWE", buyer=buyer)
        Receipt.objects.create(date="2026-07-02", market="Corner Shop", buyer=buyer)

        response = self.client.get(reverse("receipts:receipt_list"))

        self.assertContains(response, 'id="receipt-filter-market"')
        self.assertContains(response, 'data-name="REWE"')
        self.assertContains(response, static("images/market-logos/rewe.svg"))
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
        self.assertContains(response, "data-weight-fixed", count=6)
        self.assertNotContains(response, "data-allocation-total")
        self.assertContains(response, "data-receipt-total", count=1)

    def test_sonstiges_can_be_reiconed_but_not_renamed(self):
        self.client.get(reverse("receipts:categories"))
        category = Category.objects.get(name="Sonstiges")

        self.client.post(reverse("receipts:categories"), {
            "action": "edit", "category_id": category.id, "name": "Other", "emoji": "❓",
        })

        category.refresh_from_db()
        self.assertEqual((category.name, category.emoji), ("Sonstiges", "❓"))

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

    def test_old_receipts_load_items_only_when_expanded(self):
        buyer = Person.objects.get(name="Person 1")
        old_receipt = Receipt.objects.create(
            date=timezone.localdate() - timedelta(days=90),
            market="Old Market",
            buyer=buyer,
        )
        old_item = ReceiptItem.objects.create(
            receipt=old_receipt, article="Archived Item", quantity=1, total_price_cents=345
        )

        response = self.client.get(reverse("receipts:receipt_list"))

        self.assertContains(response, "Old Market")
        self.assertContains(response, "3,45")
        self.assertContains(response, "Artikel anzeigen")
        self.assertNotContains(response, "Archived Item")

        items_response = self.client.get(
            reverse("receipts:receipt_items", args=[old_receipt.id])
        )
        self.assertContains(items_response, "Archived Item")
        self.assertContains(
            items_response,
            f"?item={old_item.id}",
        )

    def test_item_search_fully_displays_matching_old_receipt(self):
        buyer = Person.objects.get(name="Person 1")
        old_receipt = Receipt.objects.create(
            date=timezone.localdate() - timedelta(days=90),
            market="Old Search Market",
            buyer=buyer,
        )
        ReceiptItem.objects.create(
            receipt=old_receipt,
            article="Historical Pineapple",
            quantity=1,
            total_price_cents=500,
        )

        response = self.client.get(
            reverse("receipts:receipt_list"), {"article": "pineAPPLE"}
        )

        self.assertContains(response, "Old Search Market")
        self.assertContains(response, "Historical ")
        self.assertContains(response, "Pineapple")
        self.assertNotContains(response, "Artikel anzeigen")

    def test_forms_expose_action_availability_hooks(self):
        person = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(
            date=timezone.localdate(),
            market="State Market",
            buyer=person,
        )
        ReceiptItem.objects.create(
            receipt=receipt,
            article="State Item",
            quantity=1,
            total_price_cents=100,
        )

        edit_response = self.client.get(reverse("receipts:receipt_edit", args=[receipt.id]))
        people_response = self.client.get(reverse("receipts:people"))
        categories_response = self.client.get(reverse("receipts:categories"))
        import_response = self.client.get(reverse("receipts:import"))

        self.assertContains(edit_response, "data-dirty-form")
        self.assertContains(edit_response, "data-dirty-submit", count=2)
        self.assertContains(edit_response, "data-dirty-submit disabled", count=2)
        self.assertContains(people_response, "data-content-form")
        self.assertContains(people_response, "data-dirty-form")
        self.assertContains(people_response, "data-state-submit disabled")
        self.assertContains(categories_response, "data-content-form")
        self.assertContains(categories_response, "data-dirty-form")
        self.assertContains(import_response, "data-content-form")
        self.assertContains(import_response, "data-state-submit disabled")

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

    def test_clickable_receipt_item_opens_focused_item_editor(self):
        person = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(
            date="2026-07-03",
            market="Example Market",
            buyer=person,
        )
        selected = ReceiptItem.objects.create(
            receipt=receipt, article="Selected Item", quantity=1, total_price_cents=100
        )
        ReceiptItem.objects.create(
            receipt=receipt, article="Other Item", quantity=1, total_price_cents=200
        )

        list_response = self.client.get(reverse("receipts:receipt_list"))
        edit_url = reverse("receipts:receipt_edit", args=[receipt.id])
        self.assertContains(list_response, f'data-href="{edit_url}?item={selected.id}"')

        edit_response = self.client.get(edit_url, {"item": selected.id})
        self.assertContains(edit_response, "Artikel bearbeiten")
        self.assertContains(edit_response, "Selected Item")
        self.assertNotContains(edit_response, "Other Item")
        self.assertNotContains(edit_response, "Zeile hinzufügen")

    def test_focused_item_editor_saves_every_editable_attribute(self):
        person_1 = Person.objects.get(name="Person 1")
        person_2 = Person.objects.get(name="Person 2")
        old_category = Category.objects.create(name="Alt", emoji="A")
        new_category = Category.objects.create(name="Neu", emoji="N")
        receipt = Receipt.objects.create(
            date="2026-07-03", market="Example Market", buyer=person_1
        )
        untouched_item = ReceiptItem.objects.create(
            receipt=receipt,
            article="Untouched Item",
            quantity=Decimal("1"),
            total_price_cents=100,
            category=old_category,
        )
        edited_item = ReceiptItem.objects.create(
            receipt=receipt,
            article="Old Item",
            quantity=Decimal("1"),
            total_price_cents=200,
            category=old_category,
        )
        ItemAllocation.objects.create(item=edited_item, person=person_1, weight=1)
        ReceiptItem.objects.create(
            receipt=Receipt.objects.create(
                date="2026-07-02", market="Other Market", buyer=person_1
            ),
            article="New Item",
            quantity=1,
            total_price_cents=50,
            category=new_category,
        )

        edit_url = reverse("receipts:receipt_edit", args=[receipt.id])
        get_response = self.client.get(edit_url, {"item": edited_item.id})
        self.assertContains(
            get_response, f'name="item-0-id" value="{edited_item.id}"'
        )

        response = self.client.post(
            f"{edit_url}?item={edited_item.id}",
            {
                "date": "2026-07-03",
                "market": "Example Market",
                "buyer": str(person_1.id),
                "row_count": "1",
                "item-0-id": str(edited_item.id),
                "item-0-article": "New Item",
                "item-0-quantity": "2,5",
                "item-0-price": "7,89 €",
                "item-0-persons": [str(person_1.id), str(person_2.id)],
                f"item-0-weight-{person_1.id}": "3",
                f"item-0-weight-{person_2.id}": "1",
            },
        )

        self.assertRedirects(response, reverse("receipts:receipt_list"))
        edited_item.refresh_from_db()
        untouched_item.refresh_from_db()
        self.assertEqual(edited_item.article, "New Item")
        self.assertEqual(edited_item.quantity, Decimal("2.50"))
        self.assertEqual(edited_item.total_price_cents, 789)
        self.assertEqual(edited_item.category, new_category)
        self.assertEqual(
            {
                allocation.person_id: allocation.weight
                for allocation in edited_item.allocations.all()
            },
            {
                person_1.id: Decimal("0.7500"),
                person_2.id: Decimal("0.2500"),
            },
        )
        self.assertEqual(untouched_item.article, "Untouched Item")
        self.assertEqual(untouched_item.quantity, Decimal("1.00"))
        self.assertEqual(untouched_item.total_price_cents, 100)
        self.assertEqual(untouched_item.category, old_category)

    def test_focused_item_editor_rejects_item_from_another_receipt(self):
        person = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(date="2026-07-03", market="A", buyer=person)
        other_receipt = Receipt.objects.create(date="2026-07-04", market="B", buyer=person)
        other_item = ReceiptItem.objects.create(
            receipt=other_receipt, article="Other", quantity=1, total_price_cents=100
        )

        response = self.client.get(
            reverse("receipts:receipt_edit", args=[receipt.id]), {"item": other_item.id}
        )
        self.assertEqual(response.status_code, 404)

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

    def test_health_view(self):
        response = self.client.get(reverse("receipts:health"))
        self.assertEqual(response.content, b"ok")
