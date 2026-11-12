from django.core.management.base import BaseCommand

from apps.public.seo_health import compute_seo_health


class Command(BaseCommand):
    help = "Print a full SEO health report. Read-only; safe to run any time."

    def handle(self, *args, **options):
        health = compute_seo_health()

        self.stdout.write(self.style.MIGRATE_HEADING("SEO Report"))

        self.stdout.write("\nPosts:")
        self.stdout.write(f"  Total: {health['total_posts']}")
        self.stdout.write(f"  Published: {health['published_posts']}")
        self.stdout.write(f"  Indexed: {health['indexed_posts']}")
        self.stdout.write(f"  Missing SEO Title: {health['missing_seo_title']}")
        self.stdout.write(f"  Missing Description: {health['missing_meta_description']}")
        self.stdout.write(f"  Missing Category: {health['missing_category']}")

        self.stdout.write("\nCategories:")
        self.stdout.write(f"  Empty: {health['empty_categories']}")

        self.stdout.write("\nTags:")
        self.stdout.write(f"  Empty: {health['empty_tags']}")

        self.stdout.write("\nRedirects:")
        self.stdout.write(f"  Active: {health['redirects_total']}")
        self.stdout.write(f"  Broken: {health['redirects_broken']}")
        for entry in health["broken_redirects"]:
            self.stdout.write(self.style.WARNING(f"    {entry.old_path} -> {entry.new_path}"))

        if health["duplicate_slug_groups"]:
            self.stdout.write("\nPotential duplicate slugs:")
            for base, slugs in health["duplicate_slug_groups"].items():
                self.stdout.write(f"  {base}: {', '.join(slugs)}")

        self.stdout.write("")
