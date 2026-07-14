from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Person",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Receipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("market", models.CharField(max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "buyer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bought_receipts",
                        to="receipts.person",
                    ),
                ),
            ],
            options={"ordering": ["-date", "-created_at", "market"]},
        ),
        migrations.CreateModel(
            name="ReceiptItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("article", models.CharField(max_length=200)),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("1"),
                        max_digits=8,
                        validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                    ),
                ),
                (
                    "total_price_cents",
                    models.IntegerField(validators=[django.core.validators.MinValueValidator(0)]),
                ),
                ("imported_raw_row", models.JSONField(blank=True, null=True)),
                (
                    "receipt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="receipts.receipt",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="ItemAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "weight",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("1"),
                        max_digits=8,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="allocations",
                        to="receipts.receiptitem",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="item_allocations",
                        to="receipts.person",
                    ),
                ),
            ],
            options={"ordering": ["person__name"]},
        ),
        migrations.AddConstraint(
            model_name="itemallocation",
            constraint=models.UniqueConstraint(
                fields=("item", "person"), name="unique_item_person_allocation"
            ),
        ),
    ]
