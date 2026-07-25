import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "receipts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "receipt_tracker.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "receipt_tracker.wsgi.application"

DATABASE_PATH = Path(os.environ.get("SQLITE_PATH", str(BASE_DIR / "data" / "app.sqlite3")))
if DATABASE_PATH.name != ":memory:":
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(DATABASE_PATH),
    }
}
DATABASE_BACKUP_DIR = Path(
    os.environ.get(
        "DATABASE_BACKUP_DIR",
        str(DATABASE_PATH.parent / "backups"),
    )
)
DATABASE_BACKUP_RETENTION_DAYS = int(
    os.environ.get("DATABASE_BACKUP_RETENTION_DAYS", "30")
)
DATABASE_BACKUP_INTERVAL_SECONDS = int(
    os.environ.get("DATABASE_BACKUP_INTERVAL_SECONDS", "86400")
)

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "de-de"
TIME_ZONE = os.environ.get("TZ", "Europe/Berlin")
USE_I18N = True
USE_TZ = True

DATA_UPLOAD_MAX_NUMBER_FIELDS_RAW = os.environ.get(
    "DJANGO_DATA_UPLOAD_MAX_NUMBER_FIELDS", "none"
).strip()
DATA_UPLOAD_MAX_NUMBER_FIELDS = (
    None
    if DATA_UPLOAD_MAX_NUMBER_FIELDS_RAW.lower() in {"", "none", "unlimited", "0"}
    else int(DATA_UPLOAD_MAX_NUMBER_FIELDS_RAW)
)

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = DATABASE_PATH.parent / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
