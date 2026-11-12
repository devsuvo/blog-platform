from django.core.management.base import BaseCommand

from apps.core.tasks import cleanup_old_data


class Command(BaseCommand):
    help = (
        "Run the same housekeeping as the daily cleanup_old_data Celery task "
        "(expired sessions, stale 404 log entries, aged analytics rows) "
        "synchronously — useful for cron fallback or a manual run without "
        "Celery running."
    )

    def handle(self, *args, **options):
        result = cleanup_old_data()  # calling a Celery task directly runs it in-process, not through the broker
        self.stdout.write(self.style.SUCCESS(
            f"Pruned {result['not_found_logs_pruned']} stale 404 log entry(ies), "
            f"{result['post_views_pruned']} daily view-count row(s), "
            f"{result['search_stats_pruned']} search query stat(s)."
        ))
