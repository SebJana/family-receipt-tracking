from django.db import migrations, models
from django.db.models import Q


def reset_duplicate_presets(apps, schema_editor):
    Person = apps.get_model("receipts", "Person")
    seen = set()
    for person in Person.objects.filter(avatar_choice__startswith="preset-").order_by("id"):
        if person.avatar_choice in seen:
            person.avatar_choice = "initials"
            person.save(update_fields=["avatar_choice"])
        else:
            seen.add(person.avatar_choice)


class Migration(migrations.Migration):
    dependencies = [
        ("receipts", "0006_expand_animal_avatars"),
    ]

    operations = [
        migrations.RunPython(reset_duplicate_presets, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="person",
            constraint=models.UniqueConstraint(
                fields=("avatar_choice",),
                condition=Q(avatar_choice__startswith="preset-"),
                name="unique_person_animal_avatar",
            ),
        ),
    ]
