# Family Receipt Tracking

Django webapp for household receipt entry, CSV import, and statistics based on weighted assignments.

## Start With the Published Docker Image

```bash
cp .env.example .env
docker compose pull
docker compose up -d
```

Compose pulls `ghcr.io/sebjana/family-receipt-tracking:latest` before deployment. The app then runs with Gunicorn at <http://localhost:6767>. The SQLite database is stored in the Docker volume `receipt_data`, so replacing the application container does not remove existing data.

## Test a Local Docker Build

`docker-compose.local.yml` overrides the deployment image with a build from the local `Dockerfile`. It uses the local image tag `family-receipt-tracking:local`, disables registry pulls, and retains the ports, environment, and `receipt_data` volume from the main Compose file.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

The same command works in PowerShell. To force a cache-free rebuild:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml build --no-cache
docker compose -f docker-compose.yml -f docker-compose.local.yml up
```

Stop the local build and return to the published GHCR image with:

```bash
docker compose down
docker compose pull
docker compose up -d
```

The local override intentionally shares `receipt_data` with the published deployment. Use a separate volume before testing destructive database changes.

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
