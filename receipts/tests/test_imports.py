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


class ImportViewTests(ReceiptTestCase):
    def test_import_page_has_copyable_csv_prompt_matching_parser_columns(self):
        response = self.client.get(reverse("receipts:import"))
        prompt_file = Path(__file__).resolve().parent.parent / "prompts" / "receipt_import_prompt.txt"

        self.assertContains(response, 'id="receipt-import-prompt"')
        self.assertContains(response, 'data-copy-target="receipt-import-prompt"')
        self.assertContains(response, "Datum;Einkaufsladen;Artikel;Anzahl;Gesamtpreis;Käufer")
        self.assertContains(response, "keine Markdown-Tabelle")
        self.assertEqual(response.context["receipt_import_prompt"], prompt_file.read_text(encoding="utf-8").strip())

    def test_unified_import_review_saves_like_manual_entry(self):
        person = Person.objects.get(name="Person 1")

        response = self.client.post(
            reverse("receipts:import"),
            {
                "mode": "save_manual",
                "date": "2026-07-03",
                "market": "Example Market",
                "buyer": str(person.id),
                "row_count": "1",
                "item-0-article": "Imported Item",
                "item-0-quantity": "2",
                "item-0-price": "4,00 €",
                "item-0-persons": [str(person.id)],
                f"item-0-weight-{person.id}": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        item = ReceiptItem.objects.get(article="Imported Item")
        self.assertEqual(item.receipt.buyer, person)
        self.assertTrue(item.allocations.filter(person=person).exists())
