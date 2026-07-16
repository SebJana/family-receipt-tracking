from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("receipts", "0008_expand_animal_avatars_again")]
    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("emoji", models.CharField(max_length=16)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="receiptitem", name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="items", to="receipts.category"),
        ),
    ]
