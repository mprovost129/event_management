from django.utils import timezone
from django.views.generic import TemplateView

from content.models import SitePage
from content.services import public_blog_posts, public_page
from events.models import Event, EventOccurrence


class HomeView(TemplateView):
    template_name = "core/home.html"

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
        return context
