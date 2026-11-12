from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.test import RequestFactory

from apps.blog.services import SITEMAP_SECTIONS, invalidate_sitemap_cache, sitemap_cache_key
from apps.public.views.sitemaps import sitemap_index, sitemap_section


class Command(BaseCommand):
    help = "Invalidate and re-warm the sitemap cache (index + every section)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-warm", action="store_true",
            help="Only invalidate the cache; don't immediately regenerate it (next visitor pays the cost instead).",
        )

    def handle(self, *args, **options):
        invalidate_sitemap_cache()
        self.stdout.write("Sitemap cache invalidated.")

        if options["no_warm"]:
            return

        request = RequestFactory().get("/sitemap.xml", SERVER_NAME="localhost")
        sitemap_index(request)
        for section in SITEMAP_SECTIONS:
            if section == "index":
                continue
            request = RequestFactory().get(f"/sitemap-{section}.xml", SERVER_NAME="localhost")
            sitemap_section(request, section)
            self.stdout.write(f"  Warmed: {section} ({'cached' if cache.get(sitemap_cache_key(section)) else 'empty'})")

        self.stdout.write(self.style.SUCCESS("Sitemap rebuilt."))
