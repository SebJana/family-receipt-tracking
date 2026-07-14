from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("receipts", "0007_unique_animal_avatars")]

    operations = [
        migrations.AlterField(
            model_name="person",
            name="avatar_choice",
            field=models.CharField(
                choices=[
                    ("initials", "Initialen"),
                    ("preset-1", "Katze"), ("preset-2", "Hund"), ("preset-3", "Fuchs"),
                    ("preset-4", "Bär"), ("preset-5", "Panda"), ("preset-6", "Koala"),
                    ("preset-7", "Tiger"), ("preset-8", "Löwe"), ("preset-9", "Kuh"),
                    ("preset-10", "Schwein"), ("preset-11", "Frosch"), ("preset-12", "Affe"),
                    ("preset-13", "Huhn"), ("preset-14", "Pinguin"), ("preset-15", "Vogel"),
                    ("preset-16", "Küken"), ("preset-17", "Eule"), ("preset-18", "Einhorn"),
                    ("preset-19", "Biene"), ("preset-20", "Schmetterling"),
                    ("preset-21", "Oktopus"), ("preset-22", "Schildkröte"),
                    ("preset-23", "Delfin"), ("preset-24", "Wal"), ("preset-25", "Maus"),
                    ("preset-26", "Hase"), ("preset-27", "Waschbär"),
                    ("preset-28", "Giraffe"), ("preset-29", "Zebra"), ("preset-30", "Igel"),
                    ("preset-31", "Känguru"), ("upload", "Eigenes Bild"),
                ],
                default="initials",
                max_length=20,
            ),
        ),
    ]
