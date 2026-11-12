from django.core.management.base import BaseCommand

from apps.public.models import Redirect
from apps.public.seo_health import redirect_target_resolves


class Command(BaseCommand):
    help = "Validate every Redirect row: broken targets and chains longer than one hop."

    def handle(self, *args, **options):
        redirects = list(Redirect.objects.all())
        by_old_path = {entry.old_path: entry for entry in redirects}

        broken = [entry for entry in redirects if not redirect_target_resolves(entry)]
        chained = [
            entry for entry in redirects
            if entry.new_path in by_old_path and by_old_path[entry.new_path].pk != entry.pk
        ]

        self.stdout.write(f"Checked {len(redirects)} redirect(s).")

        if broken:
            self.stdout.write(self.style.WARNING(f"\n{len(broken)} broken (target doesn't resolve):"))
            for entry in broken:
                self.stdout.write(f"  {entry.old_path} -> {entry.new_path}")

        if chained:
            self.stdout.write(self.style.WARNING(f"\n{len(chained)} chained (target is itself another redirect's source):"))
            for entry in chained:
                next_hop = by_old_path[entry.new_path]
                self.stdout.write(f"  {entry.old_path} -> {entry.new_path} -> {next_hop.new_path}")

        if not broken and not chained:
            self.stdout.write(self.style.SUCCESS("No problems found."))
        else:
            raise SystemExit(1)
