from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.http import Http404
from django.shortcuts import redirect, render

from apps.core.models import ActivityAction, SiteSetting
from apps.core.services import log_activity

from ..forms_settings import (
    AnalyticsSettingsForm,
    GeneralSettingsForm,
    PublishingSettingsForm,
    SEOSettingsForm,
    SocialSettingsForm,
)

SECTIONS = {
    "general": "General",
    "seo": "SEO",
    "social": "Social",
    "publishing": "Publishing",
    "analytics": "Analytics",
    "system": "System",
}

# Sections with a real, saveable form (SiteSetting-backed). The rest stay
# navigation-only placeholders until their underlying feature ships.
SECTION_FORMS = {
    "general": GeneralSettingsForm,
    "seo": SEOSettingsForm,
    "social": SocialSettingsForm,
    "publishing": PublishingSettingsForm,
    "analytics": AnalyticsSettingsForm,
}


@login_required
def settings_index(request):
    return redirect("dashboard:settings-section", section="general")


@login_required
@user_passes_test(lambda u: u.is_staff, login_url="dashboard:index")
def settings_section(request, section):
    if section not in SECTIONS:
        raise Http404

    form_class = SECTION_FORMS.get(section)
    if form_class is None:
        context = {
            "page_title": f"Settings — {SECTIONS[section]}",
            "sections": SECTIONS,
            "active_section": section,
            "active_section_label": SECTIONS[section],
        }
        return render(request, "admin_panel/settings/section.html", context)

    return _render_settings_form(request, section, form_class)


@permission_required("core.change_sitesetting", raise_exception=True)
def _render_settings_form(request, section, form_class):
    instance = SiteSetting.load()

    if request.method == "POST":
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            log_activity(
                ActivityAction.SETTINGS_CHANGED, actor=request.user,
                description=f"Updated {SECTIONS[section]} settings",
                metadata={"section": section, "fields": list(form.changed_data)},
                request=request,
            )
            messages.success(request, "Settings saved.")
            return redirect("dashboard:settings-section", section=section)
    else:
        form = form_class(instance=instance)

    context = {
        "page_title": f"Settings — {SECTIONS[section]}",
        "sections": SECTIONS,
        "active_section": section,
        "active_section_label": SECTIONS[section],
        "form": form,
    }
    return render(request, "admin_panel/settings/seo_social_form.html", context)
