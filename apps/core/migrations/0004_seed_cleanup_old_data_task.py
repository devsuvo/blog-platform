from django.db import migrations

TASK_NAME = "Cleanup old data"
TASK_PATH = "apps.core.tasks.cleanup_old_data"


def create_periodic_task(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    # Once a day at 03:00 — cheap, low-value-to-run-often housekeeping
    # (expired sessions, stale 404 logs), deliberately not on a tight
    # interval like scheduled publishing.
    schedule, _created = CrontabSchedule.objects.get_or_create(
        minute="0", hour="3", day_of_week="*", day_of_month="*", month_of_year="*",
    )
    PeriodicTask.objects.get_or_create(
        name=TASK_NAME,
        defaults={"crontab": schedule, "task": TASK_PATH},
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_sitesetting_alter_activitylog_action_notfoundlog"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
