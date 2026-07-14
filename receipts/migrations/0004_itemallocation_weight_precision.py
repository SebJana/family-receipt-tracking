from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("receipts", "0003_person_is_deleted"),
    ]

    operations = [
        migrations.AlterField(
            model_name="itemallocation",
            name="weight",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("1"),
                max_digits=8,
                validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))],
            ),
        ),
    ]
