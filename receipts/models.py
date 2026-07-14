from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Person(models.Model):
    AVATAR_LABELS = [
        "Katze", "Hund", "Fuchs", "Bär", "Panda", "Koala", "Tiger", "Löwe",
        "Kuh", "Schwein", "Frosch", "Affe", "Huhn", "Pinguin", "Vogel", "Küken",
        "Eule", "Einhorn", "Biene", "Schmetterling", "Oktopus", "Schildkröte",
        "Delfin", "Wal", "Maus", "Hase", "Waschbär", "Giraffe", "Zebra", "Igel",
        "Känguru",
    ]
    AVATAR_CHOICES = [("initials", "Initialen")] + [
        (f"preset-{index}", label) for index, label in enumerate(AVATAR_LABELS, start=1)
    ] + [("upload", "Eigenes Bild")]
    AVATAR_CHART_COLORS = [
        "#e89b2d", "#9b5d46", "#e87524", "#9a6049", "#46525a", "#82979c",
        "#e79a23", "#c88b24", "#76939a", "#e9829a", "#68a94f", "#a9684e",
        "#d94b42", "#344750", "#d84343", "#e7b92f", "#8b654b", "#9367c7",
        "#d6a51f", "#4b91c5", "#8a63c2", "#659a4c", "#3f96cf", "#3789bd",
        "#9a8d86", "#c9a27d", "#68777d", "#d39b42", "#4f5558", "#9a765e",
        "#b77a45",
    ]

    name = models.CharField(max_length=80, unique=True)
    active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    avatar_choice = models.CharField(max_length=20, choices=AVATAR_CHOICES, default="initials")
    avatar_upload = models.FileField(
        upload_to="avatars/",
        blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "gif", "webp"])],
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["avatar_choice"],
                condition=Q(avatar_choice__startswith="preset-"),
                name="unique_person_animal_avatar",
            )
        ]

    def __str__(self):
        return self.name

    @property
    def avatar_initials(self):
        return self.name.strip()[:2].upper() or "?"

    @property
    def avatar_color(self):
        seed = self.pk or sum(ord(character) for character in self.name)
        return f"hsl({(seed * 137) % 360} 58% 42%)"

    @property
    def avatar_image_url(self):
        if self.avatar_choice == "upload" and self.avatar_upload:
            return self.avatar_upload.url
        if self.avatar_choice.startswith("preset-"):
            return f"{settings.STATIC_URL}images/avatars/avatar-{self.avatar_choice.removeprefix('preset-')}.svg"
        return ""

    @property
    def avatar_is_preset(self):
        return self.avatar_choice.startswith("preset-")

    @property
    def avatar_background(self):
        return "#e6f3ef" if self.avatar_is_preset else "#ffffff"

    @property
    def avatar_chart_color(self):
        if self.avatar_is_preset:
            index = int(self.avatar_choice.removeprefix("preset-")) - 1
            if 0 <= index < len(self.AVATAR_CHART_COLORS):
                return self.AVATAR_CHART_COLORS[index]
        return self.avatar_color


class Receipt(models.Model):
    date = models.DateField()
    market = models.CharField(max_length=120)
    buyer = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="bought_receipts")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at", "market"]

    def __str__(self):
        return f"{self.date:%d.%m.%Y} - {self.market}"

    @property
    def total_cents(self):
        return sum(item.total_price_cents for item in self.items.all())


class ReceiptItem(models.Model):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="items")
    article = models.CharField(max_length=200)
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    total_price_cents = models.IntegerField()
    imported_raw_row = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.article

    @property
    def total_price_euros(self):
        return Decimal(self.total_price_cents) / Decimal("100")

    def allocation_text(self):
        allocations = list(self.allocations.all())
        if not allocations:
            return "Alle aktiven Personen"
        return "/".join(allocation.person.name for allocation in allocations)

    def allocation_short_text(self):
        allocations = list(self.allocations.all())
        if not allocations:
            return "Alle"
        return "/".join(allocation.person.name[:2] for allocation in allocations)

    def factor_text(self):
        allocations = list(self.allocations.all())
        if len(allocations) <= 1:
            return ""
        if all(allocation.weight == allocations[0].weight for allocation in allocations[1:]):
            return ""
        return ", ".join(
            f"{allocation.person.name}={allocation.weight.normalize()}" for allocation in allocations
        )

    def factor_breakdown(self):
        allocations = list(self.allocations.all())
        if len(allocations) <= 1:
            return []
        weights = [allocation.weight for allocation in allocations]
        if all(weight == weights[0] for weight in weights[1:]):
            return []
        total = sum(weights, Decimal("0"))
        if total <= 0:
            return []
        return [
            {
                "person": allocation.person,
                "short_name": allocation.person.name[:2],
                "percentage": int((allocation.weight * 100 / total).quantize(Decimal("1"))),
                "width": f"{allocation.weight * 100 / total:.2f}",
            }
            for allocation in allocations
        ]


class ItemAllocation(models.Model):
    item = models.ForeignKey(ReceiptItem, on_delete=models.CASCADE, related_name="allocations")
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="item_allocations")
    weight = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0.0001"))],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "person"], name="unique_item_person_allocation")
        ]
        ordering = ["person__name"]

    def __str__(self):
        return f"{self.item} -> {self.person} ({self.weight})"

    @staticmethod
    def split_cents(total_cents, allocations):
        weights = [Decimal(str(allocation.weight)) for allocation in allocations]
        weight_sum = sum(weights, Decimal("0"))
        if total_cents == 0 or weight_sum <= 0:
            return [0 for _ in allocations]

        raw_values = [
            (Decimal(total_cents) * weight / weight_sum).quantize(Decimal("0.0001"))
            for weight in weights
        ]
        rounded = [int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) for value in raw_values]
        difference = total_cents - sum(rounded)
        if difference:
            remainders = [
                (idx, raw_values[idx] - Decimal(rounded[idx]))
                for idx in range(len(raw_values))
            ]
            remainders.sort(key=lambda pair: pair[1], reverse=difference > 0)
            step = 1 if difference > 0 else -1
            for idx, _remainder in remainders[: abs(difference)]:
                rounded[idx] += step
        return rounded
