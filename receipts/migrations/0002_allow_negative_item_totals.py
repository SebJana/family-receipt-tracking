from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("receipts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="receiptitem",
            name="total_price_cents",
            field=models.IntegerField(),
        ),
    ]
