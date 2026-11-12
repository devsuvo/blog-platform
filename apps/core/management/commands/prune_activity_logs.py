from django.core.management.base import BaseCommand, CommandError

from apps.core.services import prune_activity_logs


class Command(BaseCommand):
    help = (
        "Delete ActivityLog entries older than N days. Manual/cron-only by "
        "design — this is an audit trail, so pruning it is an explicit "
        "operator decision (with a required cutoff), never a silent "
        "scheduled default. See DEPLOYMENT.md for a suggested retention policy."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-days", type=int, required=True,
            help="Delete entries older than this many days (e.g. 730 for a 2-year retention policy).",
        )
        parser.add_argument(
            "--yes", action="store_true",
            help="Skip the confirmation prompt (for non-interactive/cron use).",
        )

    def handle(self, *args, **options):
        days = options["older_than_days"]
        if days < 30:
            raise CommandError("Refusing to prune activity logs newer than 30 days — that's almost certainly a mistake.")

        if not options["yes"]:
            confirm = input(f"This will permanently delete ActivityLog entries older than {days} days. Type 'yes' to continue: ")
            if confirm.strip().lower() != "yes":
                self.stdout.write("Aborted.")
                return

        deleted_count = prune_activity_logs(older_than_days=days)
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} activity log entry(ies) older than {days} days."))
