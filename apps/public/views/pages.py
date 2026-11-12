import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django_ratelimit.decorators import ratelimit

from apps.core.services import get_client_ip
from apps.public.seo import build_page_seo, get_site_name, safe_json_ld, webpage_json_ld

from ..forms import ContactForm

logger = logging.getLogger("apps.public")


def about(request):
    seo = build_page_seo(request, title=f"About — {get_site_name()}", description=f"About {get_site_name()}.")
    context = {**seo, "webpage_ld": safe_json_ld(webpage_json_ld(request, seo))}
    return render(request, "public/about.html", context)


@ratelimit(key="ip", rate="5/m", method="POST", block=True)
def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.ip_address = get_client_ip(request)
            message.save()
            _notify_contact_message(message)
            messages.success(request, "Thanks for reaching out — we'll get back to you soon.")
            return redirect("public:contact")
    else:
        form = ContactForm()

    seo = build_page_seo(request, title=f"Contact — {get_site_name()}", description=f"Get in touch with {get_site_name()}.")
    context = {"form": form, **seo}
    return render(request, "public/contact.html", context)


def _notify_contact_message(message):
    try:
        send_mail(
            subject=f"[Contact] {message.subject}",
            message=f"From: {message.name} <{message.email}>\n\n{message.message}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.CONTACT_EMAIL],
            fail_silently=False,
        )
    except Exception:
        # The submission is already saved; a notification-email hiccup
        # shouldn't turn into a 500 for the visitor.
        logger.exception("Failed to send contact-form notification email")


def privacy(request):
    seo = build_page_seo(request, title=f"Privacy Policy — {get_site_name()}", description=f"Privacy Policy for {get_site_name()}.")
    return render(request, "public/privacy.html", seo)


def terms(request):
    seo = build_page_seo(request, title=f"Terms of Use — {get_site_name()}", description=f"Terms of Use for {get_site_name()}.")
    return render(request, "public/terms.html", seo)
