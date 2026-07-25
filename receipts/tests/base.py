from django.test import TestCase, override_settings

from ..models import Person


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class ReceiptTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name in ["Person 1", "Person 2", "Person 3"]:
            Person.objects.create(name=name, active=True)
