# Family Receipt Tracking

Django webapp for household receipt entry, CSV import, and statistics based on weighted assignments.

## Start With Docker

```bash
cp .env.example .env
docker compose up --build
```

The app then runs with Gunicorn at <http://localhost:6767>. The SQLite database is stored in the Docker volume `receipt_data`.

## Local Development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

People can be added through the app. To create the optional default person
manually, run `python manage.py seed_people` once.

## Import Format

Expected header:

```csv
Datum;Einkaufsladen;Artikel;Anzahl;Gesamtpreis;Käufer
```

Import is paste-only. Negative totals are allowed for bottle and can returns.

Assignments and factors are not imported. Imported rows start unassigned, and statistics treat unassigned items as equally assigned to all active people until explicit assignments are added in the app.

Manual receipt entry still supports explicit assignments and factors.

Statistics use assigned cost shares, not raw buyer totals.
