from django.db import migrations

TASK_NAME = "Publish scheduled posts"
TASK_PATH = "apps.blog.tasks.publish_scheduled_posts"


def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _created = IntervalSchedule.objects.get_or_create(every=1, period="minutes")
    PeriodicTask.objects.get_or_create(
        name=TASK_NAME,
        defaults={"interval": schedule, "task": TASK_PATH},
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0001_initial"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
