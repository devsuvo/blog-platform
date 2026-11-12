from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect


class RedirectMiddleware:
    """Catches any 404 and checks the `Redirect` table for the requested
    path before giving up — one general mechanism for admin-managed
    redirects *and* the ones auto-created on a post slug change, covering
    any URL on the site, not just `/blog/<slug>/`.

    Runs its query only on the (rare) 404 path, so normal page performance
    is untouched. A genuine 404 (no matching redirect) is sampled into
    NotFoundLog here too, so both concerns share the one place a "path
    that doesn't resolve" is actually observed.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code == 404 and request.method in ("GET", "HEAD"):
            from .models import Redirect

            entry = Redirect.objects.filter(old_path=request.path).first()
            if entry is not None:
                redirect_cls = (
                    HttpResponsePermanentRedirect if entry.status_code == 301 else HttpResponseRedirect
                )
                return redirect_cls(entry.new_path)

            from apps.core.services import record_not_found

            record_not_found(request)

        return response
