import time

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run the database backup job immediately and then once per interval."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database-path",
            default=str(settings.DATABASE_PATH),
            help="SQLite database to back up.",
        )
        parser.add_argument(
            "--backup-dir",
            default=str(settings.DATABASE_BACKUP_DIR),
            help="Directory where backup files are stored.",
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            default=settings.DATABASE_BACKUP_RETENTION_DAYS,
            help="Delete managed backups older than this many days.",
        )
        parser.add_argument(
            "--interval-seconds",
            type=int,
            default=settings.DATABASE_BACKUP_INTERVAL_SECONDS,
            help="Seconds between backup runs.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run one backup without waiting for the next interval.",
        )

    def handle(self, *args, **options):
        if options["interval_seconds"] < 1:
            raise CommandError("interval-seconds must be at least 1")

        while True:
            call_command(
                "backup_database",
                database_path=options["database_path"],
                backup_dir=options["backup_dir"],
                retention_days=options["retention_days"],
                stdout=self.stdout,
                stderr=self.stderr,
            )
            if options["once"]:
                return
            self.stdout.write(
                f"Next database backup in {options['interval_seconds']} seconds."
            )
            self.stdout.flush()
            time.sleep(options["interval_seconds"])
