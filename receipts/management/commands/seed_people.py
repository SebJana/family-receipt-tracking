from django.core.management.base import BaseCommand

from receipts.models import Person


DEFAULT_PEOPLE = ["Person 1"]


class Command(BaseCommand):
    help = "Seed the default household people."

    def handle(self, *args, **options):
        created = 0
        for name in DEFAULT_PEOPLE:
            _person, was_created = Person.objects.get_or_create(
                name=name,
                defaults={"active": True, "is_deleted": False},
            )
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"People ready: {created} created"))
