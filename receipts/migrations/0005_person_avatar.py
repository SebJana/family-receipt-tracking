import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("receipts", "0004_itemallocation_weight_precision"),
    ]

    operations = [
        migrations.AddField(
            model_name="person",
            name="avatar_choice",
            field=models.CharField(
                choices=[
                    ("initials", "Initialen"),
                    ("preset-1", "Avatar 1"),
                    ("preset-2", "Avatar 2"),
                    ("preset-3", "Avatar 3"),
                    ("preset-4", "Avatar 4"),
                    ("preset-5", "Avatar 5"),
                    ("preset-6", "Avatar 6"),
                    ("preset-7", "Avatar 7"),
                    ("preset-8", "Avatar 8"),
                    ("preset-9", "Avatar 9"),
                    ("preset-10", "Avatar 10"),
                    ("upload", "Eigenes Bild"),
                ],
                default="initials",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="person",
            name="avatar_upload",
            field=models.FileField(
                blank=True,
                upload_to="avatars/",
                validators=[django.core.validators.FileExtensionValidator(["png", "jpg", "jpeg", "gif", "webp"])],
            ),
        ),
    ]
