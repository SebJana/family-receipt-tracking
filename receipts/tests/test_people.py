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


class PeopleViewTests(ReceiptTestCase):
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
        self.assertEqual(
            person.avatar_image_url, static("images/avatars/avatar-7.svg")
        )

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

        self.assertContains(response, static("images/avatars/avatar-1.svg"))
        self.assertContains(response, static("images/avatars/avatar-24.svg"))
        self.assertContains(response, static("images/avatars/avatar-31.svg"))
        self.assertContains(response, "Känguru")
        self.assertContains(response, "Schildkröte")
        self.assertContains(response, "Initialen")
        self.assertContains(response, "avatar-dialog-1")

    def test_avatar_dialog_has_mobile_interaction_safeguards(self):
        project_root = Path(__file__).resolve().parent.parent.parent
        css = (project_root / "static/css/app.css").read_text(encoding="utf-8")
        javascript = (project_root / "static/js/people.js").read_text(encoding="utf-8")

        self.assertIn("height: calc(100dvh - 16px)", css)
        self.assertIn("grid-auto-rows: max-content", css)
        self.assertIn("grid-template-columns: repeat(3, minmax(68px, 1fr))", css)
        self.assertIn("grid-template-columns: repeat(2, minmax(72px, 1fr))", css)
        self.assertIn("height: 82px", css)
        self.assertIn("touch-action: manipulation", css)
        self.assertIn("const outside = event.clientX < bounds.left", javascript)

    def test_avatar_options_do_not_show_hover_tooltips(self):
        response = self.client.get(reverse("receipts:people"))

        self.assertNotRegex(
            response.content.decode(),
            r'class="avatar-option[^"]*"[^>]*\stitle=',
        )

    def test_avatar_dialog_distinguishes_cancel_from_confirm(self):
        response = self.client.get(reverse("receipts:people"))
        javascript = (
            Path(__file__).resolve().parent.parent.parent / "static/js/people.js"
        ).read_text(encoding="utf-8")

        self.assertContains(response, "data-avatar-cancel")
        self.assertContains(response, "data-avatar-confirm")
        self.assertIn("captureSnapshot(dialog)", javascript)
        self.assertIn("cancelDialog(dialog)", javascript)
        self.assertIn('originalChoice.dispatchEvent(new Event("change"', javascript)

    def test_stats_person_charts_use_avatar_colors(self):
        person = Person.objects.get(name="Person 1")
        person.avatar_choice = "preset-3"
        person.save()
        receipt = Receipt.objects.create(
            date=timezone.localdate(), market="Example Market", buyer=person
        )
        ReceiptItem.objects.create(receipt=receipt, article="Test", quantity=1, total_price_cents=100)

        response = self.client.get(reverse("receipts:stats"))

        self.assertContains(response, Person.AVATAR_CHART_COLORS[2])

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
