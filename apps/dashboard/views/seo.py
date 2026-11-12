from django.contrib.auth.decorators import login_required, user_passes_test

from django.shortcuts import render

from apps.public.seo_health import compute_seo_health


@login_required
@user_passes_test(lambda u: u.is_staff, login_url="dashboard:index")
def seo_dashboard(request):
    health = compute_seo_health()
    context = {"page_title": "SEO Health", "health": health}
    return render(request, "admin_panel/seo/dashboard.html", context)
