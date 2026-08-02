from decimal import Decimal

from django.conf import settings
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from events.models import EventAlbum
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


def _add_sitemap_entry(entries, loc, lastmod):
    entries.append(
        {
            "loc": loc,
            "lastmod": lastmod,
        }
    )


def _public_sitemap_entries(request, site):
    now = timezone.now()
    entries = []
    _add_sitemap_entry(
        entries,
        request.build_absolute_uri(reverse("core:home")),
        site.updated_at,
    )

    for page_type, route_name in (
        (SitePage.PageType.ABOUT, "content:about"),
        (SitePage.PageType.CONTACT, "content:contact"),
        (SitePage.PageType.NEWSLETTER, "content:newsletter"),
    ):
        if page := public_page(site, page_type):
            _add_sitemap_entry(
                entries,
                request.build_absolute_uri(reverse(route_name)),
                page.updated_at,
            )

    posts = public_blog_posts(site)
    if posts.exists():
        newest_post = posts.first()
        _add_sitemap_entry(
            entries,
            request.build_absolute_uri(reverse("content:blog_index")),
            newest_post.updated_at,
        )
        for post in posts:
            _add_sitemap_entry(
                entries,
                request.build_absolute_uri(
                    reverse("content:blog_detail", kwargs={"slug": post.slug})
                ),
                post.updated_at,
            )

    _add_sitemap_entry(
        entries,
        request.build_absolute_uri(reverse("events:calendar")),
        site.updated_at,
    )

    events = (
        Event.objects.for_site(site)
        .filter(
            status=Event.Status.PUBLISHED,
            visibility=Event.Visibility.PUBLIC,
            occurrences__status=EventOccurrence.Status.SCHEDULED,
            occurrences__ends_at__gte=now,
        )
        .distinct()
    )
    for event in events:
        _add_sitemap_entry(
            entries,
            request.build_absolute_uri(
                reverse("events:detail", kwargs={"slug": event.slug})
            ),
            event.updated_at,
        )

    occurrences = (
        EventOccurrence.objects.for_site(site)
        .filter(
            event__status=Event.Status.PUBLISHED,
            event__visibility=Event.Visibility.PUBLIC,
            status=EventOccurrence.Status.SCHEDULED,
            ends_at__gte=now,
        )
        .select_related("event")
    )
    for occurrence in occurrences:
        _add_sitemap_entry(
            entries,
            request.build_absolute_uri(
                reverse(
                    "events:occurrence_detail",
                    kwargs={
                        "slug": occurrence.event.slug,
                        "occurrence_id": occurrence.id,
                    },
                )
            ),
            occurrence.updated_at,
        )

    albums = (
        EventAlbum.objects.for_site(site)
        .filter(status=EventAlbum.Status.PUBLISHED, occurrence__ends_at__lte=now)
        .annotate(photo_count=Count("photos"))
        .filter(photo_count__gt=0)
    )
    if albums.exists():
        _add_sitemap_entry(
            entries,
            request.build_absolute_uri(reverse("events:photo_album_list")),
            max(album.updated_at for album in albums),
        )
        for album in albums:
            _add_sitemap_entry(
                entries,
                request.build_absolute_uri(
                    reverse("events:photo_album_detail", kwargs={"slug": album.slug})
                ),
                album.updated_at,
            )

    return entries


def _control_sitemap_entries(request):
    entries = []
    for route_name in (
        "core:home",
        "core:help",
        "core:legal",
        "core:privacy",
        "core:terms",
        "core:cookies",
        "core:refunds",
        "core:acceptable_use",
        "core:retention",
        "core:security",
        "core:review_guidelines",
        "users:signup",
        "users:login",
    ):
        _add_sitemap_entry(
            entries,
            request.build_absolute_uri(reverse(route_name)),
            timezone.now(),
        )
    return entries


@require_GET
def robots_txt(request):
    site = getattr(request, "site", None)
    allow_indexing = bool(
        site is None or (site.accepts_public_traffic and site.is_published)
    )
    return TemplateResponse(
        request,
        "core/robots.txt",
        {
            "allow_indexing": allow_indexing,
            "sitemap_url": request.build_absolute_uri(reverse("core:sitemap")),
        },
        content_type="text/plain",
    )


@require_GET
def sitemap_xml(request):
    site = getattr(request, "site", None)
    if site is not None and (not site.accepts_public_traffic or not site.is_published):
        raise Http404("Site not found.")
    entries = (
        _public_sitemap_entries(request, site)
        if site
        else _control_sitemap_entries(request)
    )
    return TemplateResponse(
        request,
        "core/sitemap.xml",
        {"entries": entries},
        content_type="application/xml",
    )


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
