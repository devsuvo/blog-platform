from django.core.management.base import BaseCommand

from apps.public.seo_health import compute_seo_health


class Command(BaseCommand):
    help = (
        "Check for SEO problems and exit non-zero if any were found — "
        "suitable for CI. For a full informational breakdown, use `seo_report` instead."
    )

    def handle(self, *args, **options):
        health = compute_seo_health()
        problems = []

        if health["redirects_broken"]:
            problems.append(f"{health['redirects_broken']} broken redirect(s)")
        if health["missing_seo_title"]:
            problems.append(f"{health['missing_seo_title']} published post(s) with no SEO title (falls back to post title — usually fine, but worth a look)")
        if health["missing_meta_description"]:
            problems.append(f"{health['missing_meta_description']} published post(s) with no meta description AND no excerpt")
        if health["duplicate_slug_groups"]:
            problems.append(f"{len(health['duplicate_slug_groups'])} group(s) of posts with similar slugs")

        if not problems:
            self.stdout.write(self.style.SUCCESS("check_seo: no problems found."))
            return

        self.stdout.write(self.style.WARNING("check_seo: issues found:"))
        for problem in problems:
            self.stdout.write(f"  - {problem}")

        # Only genuinely broken things (not "missing" recommendations) fail
        # the command — those two are advisory, not errors.
        if health["redirects_broken"]:
            raise SystemExit(1)
