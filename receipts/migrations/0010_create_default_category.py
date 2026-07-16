from django.db import migrations


def create_default_category(apps, schema_editor):
    Category = apps.get_model("receipts", "Category")
    Category.objects.get_or_create(name="Sonstiges", defaults={"emoji": "📦"})


class Migration(migrations.Migration):
    dependencies = [("receipts", "0009_category_receiptitem_category")]
    operations = [migrations.RunPython(create_default_category, migrations.RunPython.noop)]
