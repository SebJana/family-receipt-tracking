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


class StatsViewTests(ReceiptTestCase):
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

    def test_person_filter_hides_person_charts_and_settlement(self):
        person = Person.objects.get(name="Person 1")
        response = self.client.get(reverse("receipts:stats"), {
            "person": person.id, "date_from": "2026-07-01", "date_to": "2026-07-31",
        })

        self.assertNotContains(response, "Personen pro Monat")
        self.assertNotContains(response, "Anteil pro Person")
        self.assertNotContains(response, "Monatsausgleich")

    def test_stats_page_has_no_article_filter(self):
        response = self.client.get(reverse("receipts:stats"))

        self.assertNotContains(response, 'name="article"')
        self.assertNotContains(response, "Filter anwenden")

    def test_stats_page_defaults_to_current_month(self):
        today = timezone.localdate()
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        response = self.client.get(reverse("receipts:stats"))

        self.assertEqual(response.context["filters"]["date_from"], month_start.isoformat())
        self.assertEqual(response.context["filters"]["date_to"], month_end.isoformat())
        self.assertEqual(response.context["single_month"], month_start)
        self.assertNotContains(response, "Personen pro Monat")
        self.assertNotContains(response, 'id="person-month-data"')

    def test_person_per_month_chart_is_hidden_for_both_month_presets(self):
        today = timezone.localdate()
        current_start = today.replace(day=1)
        current_end = (current_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)

        for date_from, date_to in (
            (current_start, current_end),
            (previous_start, previous_end),
        ):
            with self.subTest(date_from=date_from):
                response = self.client.get(
                    reverse("receipts:stats"),
                    {
                        "date_from": date_from.isoformat(),
                        "date_to": date_to.isoformat(),
                    },
                )
                self.assertNotContains(response, "Personen pro Monat")
                self.assertNotContains(response, 'id="person-month-data"')

    def test_stats_page_has_responsive_settlement_and_grouped_breakdowns(self):
        person = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(
            date=timezone.localdate(),
            market="Responsive Market",
            buyer=person,
        )
        ReceiptItem.objects.create(
            receipt=receipt,
            article="Responsive Item",
            quantity=1,
            total_price_cents=100,
        )

        response = self.client.get(reverse("receipts:stats"))

        self.assertContains(response, 'class="settlement-balance-table"')
        self.assertContains(response, 'data-label="Saldo"')
        self.assertContains(response, 'class="settlement-transfer-table"')
        self.assertContains(
            response,
            'class="chart-panel wide month-total-card stats-summary-total"',
        )
        self.assertContains(
            response, 'class="chart-panel wide settlement-panel"'
        )
        self.assertContains(response, 'class="stats-breakdown-row"', count=2)

    def test_import_preview_and_stats_views(self):
        response = self.client.post(reverse("receipts:import"), {"csv_text": SAMPLE_CSV})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import prüfen")
        self.assertContains(response, 'name="date" value="2026-07-03"')
        self.assertContains(response, 'name="market" value="Example Market"')
        self.assertContains(response, 'name="buyer"')
        self.assertContains(response, 'name="item-0-article" value="Snack A"')
        self.assertContains(response, "Zuordnung und Faktoren")
        self.assertContains(response, 'name="mode" value="save_manual"')

        stats_response = self.client.get(reverse("receipts:stats"))
        self.assertEqual(stats_response.status_code, 200)
        self.assertContains(stats_response, "Statistiken")
        self.assertContains(stats_response, "data-person-avatars")

    def test_market_stats_keep_brand_color_keys_with_cached_logo_urls(self):
        person = Person.objects.get(name="Person 1")
        receipt = Receipt.objects.create(
            date=timezone.localdate(), market="REWE", buyer=person
        )
        ReceiptItem.objects.create(
            receipt=receipt, article="Test", quantity=1, total_price_cents=100
        )

        response = self.client.get(reverse("receipts:stats"))
        market_data = response.context["stats"]["markets"]

        self.assertEqual(market_data["logo_keys"], ["rewe.svg"])
        self.assertEqual(
            market_data["logos"], [static("images/market-logos/rewe.svg")]
        )
