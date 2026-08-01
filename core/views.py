from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.templatetags.static import static
from django.utils import timezone
from django.views.generic import TemplateView

from content.models import SitePage
from content.services import public_blog_posts, public_page
from events.models import Event, EventOccurrence
from subscriptions.gateway import billing_options

from .health import readiness_status

LEGAL_DOCUMENTS = (
    {
        "key": "terms",
        "title": "Terms of Service",
        "short_title": "Terms",
        "description": "The agreement for accounts, subscriptions, sites, events, communications, content, and platform use.",
        "route": "core:terms",
        "template": "core/legal/terms.html",
    },
    {
        "key": "privacy",
        "title": "Privacy Notice",
        "short_title": "Privacy",
        "description": "What Gather HQs and subscriber groups collect, why it is used, where it goes, and the choices people have.",
        "route": "core:privacy",
        "template": "core/legal/privacy.html",
    },
    {
        "key": "cookies",
        "title": "Cookie Notice",
        "short_title": "Cookies",
        "description": "The essential browser storage used by the platform and how third-party hosted pages are handled.",
        "route": "core:cookies",
        "template": "core/legal/cookies.html",
    },
    {
        "key": "refunds",
        "title": "Payments, Cancellations & Refunds",
        "short_title": "Payments & refunds",
        "description": "Separate rules for Gather HQs subscriptions, event tickets, and subscriber membership dues.",
        "route": "core:refunds",
        "template": "core/legal/refunds.html",
    },
    {
        "key": "acceptable_use",
        "title": "Acceptable Use Policy",
        "short_title": "Acceptable use",
        "description": "Safety, consent, content, communications, security, and platform-integrity requirements.",
        "route": "core:acceptable_use",
        "template": "core/legal/acceptable_use.html",
    },
    {
        "key": "retention",
        "title": "Data Retention & Deletion",
        "short_title": "Retention",
        "description": "How active data, deletion requests, protected records, logs, and backups are handled.",
        "route": "core:retention",
        "template": "core/legal/retention.html",
    },
    {
        "key": "security",
        "title": "Security & Responsible Disclosure",
        "short_title": "Security",
        "description": "Platform safeguards, customer responsibilities, incident handling, and how to report a concern.",
        "route": "core:security",
        "template": "core/legal/security.html",
    },
    {
        "key": "review_guidelines",
        "title": "Review Guidelines",
        "short_title": "Reviews",
        "description": "Eligibility, honest feedback, prohibited content, moderation, removal, and appeals.",
        "route": "core:review_guidelines",
        "template": "core/legal/review_guidelines.html",
    },
)


def health_live(request):
    return JsonResponse({"ok": True, "service": "web"})


def health_ready(request):
    status = readiness_status()
    return JsonResponse(status, status=200 if status["ok"] else 503)


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get(self, request, *args, **kwargs):
        site = getattr(request, "site", None)
        if site is None and request.user.is_authenticated:
            return redirect("sites:account_dashboard")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site = getattr(self.request, "site", None)
        context["site"] = site
        context["base_template"] = "public/site_base.html" if site else "base.html"
        if site and site.accepts_public_traffic and site.is_published:
            context["home_page"] = public_page(site, SitePage.PageType.HOME)
            context["upcoming_occurrences"] = (
                EventOccurrence.objects.for_site(site)
                .filter(
                    event__status=Event.Status.PUBLISHED,
                    event__visibility=Event.Visibility.PUBLIC,
                    status=EventOccurrence.Status.SCHEDULED,
                    ends_at__gte=timezone.now(),
                )
                .select_related("event")[:3]
            )
            context["recent_posts"] = public_blog_posts(site)[:3]
        elif site is None:
            context["billing_options"] = billing_options()
            context["canonical_url"] = self.request.build_absolute_uri("/")
            context["social_image_url"] = self.request.build_absolute_uri(
                static("img/gather-hqs-social.png")
            )
        return context


class LegalContextMixin:
    document_key = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documents = list(LEGAL_DOCUMENTS)
        current_document = next(
            (
                document
                for document in documents
                if document["key"] == self.document_key
            ),
            None,
        )
        billing = {option["interval"]: option for option in billing_options()}
        context.update(
            {
                "legal_documents": documents,
                "legal_document": current_document,
                "legal_draft": settings.LEGAL_DRAFT,
                "legal_business_name": settings.LEGAL_BUSINESS_NAME,
                "legal_postal_address": settings.LEGAL_POSTAL_ADDRESS,
                "legal_effective_date": settings.LEGAL_EFFECTIVE_DATE,
                "legal_governing_law": settings.LEGAL_GOVERNING_LAW,
                "legal_venue": settings.LEGAL_VENUE,
                "privacy_email": settings.PRIVACY_EMAIL or settings.SUPPORT_EMAIL,
                "security_email": settings.SECURITY_EMAIL or settings.SUPPORT_EMAIL,
                "trial_days": settings.SUBSCRIPTION_TRIAL_DAYS,
                "retention_days": settings.SUSPENDED_DATA_RETENTION_DAYS,
                "ticket_application_fee_percent": (
                    Decimal(settings.TICKET_APPLICATION_FEE_BPS) / 100
                ),
                "standard_monthly_amount": billing["monthly"]["amount"],
                "standard_yearly_amount": billing["yearly"]["amount"],
            }
        )
        return context


class LegalCenterView(LegalContextMixin, TemplateView):
    template_name = "core/legal/index.html"


class LegalPageView(LegalContextMixin, TemplateView):
    def get_template_names(self):
        document = next(
            (
                document
                for document in LEGAL_DOCUMENTS
                if document["key"] == self.document_key
            ),
            None,
        )
        if document is None:
            return ["core/legal/index.html"]
        return [document["template"]]


class HelpView(TemplateView):
    template_name = "core/help.html"
