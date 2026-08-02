from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from contacts.services import subscribe_to_newsletter
from core.rate_limits import public_write_rate_limit
from ops.services import record_audit_event
from sites.permissions import site_staff_required

from .forms import (
    BlogPostForm,
    NewsletterSignupForm,
    SitePageForm,
    SitePresentationForm,
)
from .models import BlogPost, SitePage
from .services import initialize_site_content, public_blog_posts, public_page


def _public_site(request):
    site = getattr(request, "site", None)
    if site is None or not site.accepts_public_traffic or not site.is_published:
        raise Http404("Site not found.")
    return site


@require_GET
def public_brand_asset(request, asset):
    site = _public_site(request)
    brand_file = {
        "logo": site.theme.logo,
        "hero": site.theme.hero_image,
    }.get(asset)
    if not brand_file:
        raise Http404("Brand image not found.")
    response = redirect(brand_file.url)
    response["Cache-Control"] = "public, max-age=300"
    return response


@site_staff_required
def manage_content(request, site_id):
    site = request.authorized_site
    pages = initialize_site_content(site)
    home_page = next(page for page in pages if page.page_type == SitePage.PageType.HOME)
    website_checks = (
        {
            "label": "Choose your look",
            "description": "Set the template, colors, name, and welcome message.",
            "complete": bool(
                site.theme.hero_heading or site.theme.logo or site.theme.hero_image
            ),
            "url": reverse("content:presentation", args=(site.id,)),
        },
        {
            "label": "Write your homepage",
            "description": "Introduce the group below the welcome banner.",
            "complete": bool(home_page.body.strip()),
            "url": reverse("content:page_edit", args=(site.id, SitePage.PageType.HOME)),
        },
        {
            "label": "Publish your website",
            "description": "Make the site available at its Gather HQs address.",
            "complete": site.is_published,
            "url": reverse("content:presentation", args=(site.id,)),
        },
    )
    completed_checks = sum(check["complete"] for check in website_checks)
    return render(
        request,
        "content/manage.html",
        {
            "site": site,
            "pages": pages,
            "posts": BlogPost.objects.for_site(site).select_related("author"),
            "canonical_domain": site.domains.filter(is_canonical=True).first(),
            "website_setup": {
                "checks": website_checks,
                "completed": completed_checks,
                "total": len(website_checks),
                "percent": round(completed_checks / len(website_checks) * 100),
            },
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def presentation(request, site_id):
    site = request.authorized_site
    form = SitePresentationForm(request.POST or None, request.FILES or None, site=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit_event(
            action="site.presentation.updated",
            actor=request.user,
            site_id=site.id,
            target=site,
            summary={"published": site.is_published, "template": site.template_key},
            request=request,
        )
        messages.success(
            request, "Site appearance and publication settings were saved."
        )
        return redirect("content:manage", site_id=site.id)
    return render(
        request,
        "content/presentation_form.html",
        {
            "site": site,
            "form": form,
            "canonical_domain": site.domains.filter(is_canonical=True).first(),
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def page_edit(request, site_id, page_type):
    site = request.authorized_site
    initialize_site_content(site)
    page = get_object_or_404(SitePage.objects.for_site(site), page_type=page_type)
    form = SitePageForm(request.POST or None, instance=page)
    if request.method == "POST" and form.is_valid():
        page = form.save()
        record_audit_event(
            action="content.page.updated",
            actor=request.user,
            site_id=site.id,
            target=page,
            summary={"page_type": page.page_type, "status": page.status},
            request=request,
        )
        messages.success(request, f"{page.title} was saved.")
        return redirect("content:manage", site_id=site.id)
    return render(
        request, "content/page_form.html", {"site": site, "page": page, "form": form}
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def blog_create(request, site_id):
    site = request.authorized_site
    form = BlogPostForm(request.POST or None, request.FILES or None, site=site)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        post.site = site
        post.author = request.user
        try:
            with transaction.atomic():
                post.save()
        except IntegrityError:
            form.add_error(
                "slug", "That blog URL is already in use. Try a different one."
            )
            return render(
                request, "content/blog_form.html", {"site": site, "form": form}
            )
        record_audit_event(
            action="content.blog_post.created",
            actor=request.user,
            site_id=site.id,
            target=post,
            summary={"status": post.status, "slug": post.slug},
            request=request,
        )
        messages.success(request, "Blog post was created.")
        return redirect("content:manage", site_id=site.id)
    return render(request, "content/blog_form.html", {"site": site, "form": form})


@site_staff_required
@require_http_methods(["GET", "POST"])
def blog_edit(request, site_id, post_id):
    site = request.authorized_site
    post = get_object_or_404(BlogPost.objects.for_site(site), pk=post_id)
    form = BlogPostForm(
        request.POST or None, request.FILES or None, instance=post, site=site
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                post = form.save()
        except IntegrityError:
            form.add_error(
                "slug", "That blog URL is already in use. Try a different one."
            )
            return render(
                request,
                "content/blog_form.html",
                {"site": site, "post": post, "form": form},
            )
        record_audit_event(
            action="content.blog_post.updated",
            actor=request.user,
            site_id=site.id,
            target=post,
            summary={"status": post.status, "slug": post.slug},
            request=request,
        )
        messages.success(request, "Blog post was saved.")
        return redirect("content:manage", site_id=site.id)
    return render(
        request, "content/blog_form.html", {"site": site, "post": post, "form": form}
    )


def page_detail(request, page_type):
    site = _public_site(request)
    page = public_page(site, page_type)
    if page is None:
        raise Http404("Page not found.")
    return render(request, "public/page.html", {"site": site, "page": page})


def blog_index(request):
    site = _public_site(request)
    return render(
        request,
        "public/blog_index.html",
        {"site": site, "posts": public_blog_posts(site)},
    )


def blog_detail(request, slug):
    site = _public_site(request)
    post = get_object_or_404(public_blog_posts(site), slug=slug)
    return render(request, "public/blog_detail.html", {"site": site, "post": post})


@require_http_methods(["GET", "POST"])
@public_write_rate_limit("newsletter-signup")
def newsletter_signup(request):
    site = _public_site(request)
    page = public_page(site, SitePage.PageType.NEWSLETTER)
    form = NewsletterSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        subscribe_to_newsletter(
            site=site,
            email=form.cleaned_data["email"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            source="public_newsletter_form",
        )
        messages.success(request, "You're subscribed to email updates.")
        return redirect(reverse("content:newsletter"))
    return render(
        request,
        "public/newsletter.html",
        {"site": site, "page": page, "form": form},
    )
