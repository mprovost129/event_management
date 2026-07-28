from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from sites.permissions import site_staff_required

from .forms import ReviewForm, ReviewReportForm, ReviewResponseForm
from .models import Review
from .services import (
    delete_review,
    participant_can_review,
    participant_for_token,
    report_review,
    respond_to_review,
    save_review,
)


@require_http_methods(("GET", "POST"))
def submit_review(request, token):
    site = getattr(request, "site", None)
    if site is None or not site.accepts_public_traffic:
        raise Http404("Review link not found.")
    participant = participant_for_token(site=site, token=token)
    if participant is None or not participant_can_review(participant):
        raise Http404("Review link not found or not yet available.")
    review = Review.objects.filter(participant=participant).first()
    if request.method == "POST" and request.POST.get("action") == "delete":
        if review is None:
            raise Http404("Review not found.")
        delete_review(review=review)
        return render(request, "reviews/complete.html", {"site": site, "deleted": True})
    form = ReviewForm(request.POST or None, instance=review)
    if request.method == "POST" and form.is_valid():
        try:
            review, _ = save_review(
                participant=participant,
                rating=form.cleaned_data["rating"],
                comment=form.cleaned_data["comment"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return render(
                request, "reviews/complete.html", {"site": site, "review": review}
            )
    return render(
        request,
        "reviews/form.html",
        {"site": site, "participant": participant, "review": review, "form": form},
    )


@site_staff_required
def manage_reviews(request, site_id):
    site = request.authorized_site
    reviews = Review.objects.for_site(site).select_related(
        "occurrence__event", "responded_by"
    )
    return render(request, "reviews/manage.html", {"site": site, "reviews": reviews})


@site_staff_required
@require_http_methods(("GET", "POST"))
def respond(request, site_id, review_id):
    review = get_object_or_404(
        Review.objects.for_site(request.authorized_site), pk=review_id
    )
    form = ReviewResponseForm(
        request.POST or None, initial={"response": review.response}
    )
    if request.method == "POST" and form.is_valid():
        respond_to_review(
            review=review, actor=request.user, response=form.cleaned_data["response"]
        )
        messages.success(request, "Response published.")
        return redirect("reviews:manage", site_id=site_id)
    return render(
        request,
        "reviews/respond.html",
        {"site": request.authorized_site, "review": review, "form": form},
    )


@site_staff_required
@require_POST
def report(request, site_id, review_id):
    review = get_object_or_404(
        Review.objects.for_site(request.authorized_site), pk=review_id
    )
    form = ReviewReportForm(request.POST)
    if form.is_valid():
        report_review(
            review=review,
            actor=request.user,
            reason=form.cleaned_data["reason"],
            request=request,
        )
        messages.success(
            request,
            "Review reported to platform moderation. It remains public pending review.",
        )
    else:
        messages.error(request, "A report reason is required.")
    return redirect("reviews:manage", site_id=site_id)
