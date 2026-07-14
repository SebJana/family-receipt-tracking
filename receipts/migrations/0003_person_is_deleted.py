from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("receipts", "0002_allow_negative_item_totals"),
    ]

    operations = [
        migrations.AddField(
            model_name="person",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
    ]
