from decimal import Decimal

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Max, Prefetch, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from core.pagination import paginate
from core.rate_limits import public_write_rate_limit
from notifications.services import notify_registration_response
from ops.services import record_audit_event
from payments.services import registration_checkout_token, ticket_inventory
from sites.permissions import site_staff_required

from .forms import (
    EventAlbumCreateForm,
    EventAlbumEditForm,
    EventDetailsForm,
    EventForm,
    EventPhotoEditForm,
    EventPhotoUploadForm,
    InvitationForm,
    ManagerResponseForm,
    OccurrenceEditForm,
    RSVPForm,
)
from .messaging import (
    queue_confirmation,
    queue_invitation,
    queue_occurrence_notice,
    queue_rsvp_manage_link,
)
from .models import Event, EventAlbum, EventOccurrence, EventPhoto, Registration
from .registration import (
    CapacityExceeded,
    PublicResponseAlreadyExists,
    RegistrationUnavailable,
    create_invitations,
    invitation_for_token,
    public_registration_for_token,
    save_public_response,
    save_response,
)
from .reporting import occurrence_metrics
from .services import (
    create_event_series,
    public_occurrence_url,
    update_occurrences_from,
)


def _public_site(request):
    site = getattr(request, "site", None)
    if site is None or not site.accepts_public_traffic or not site.is_published:
        raise Http404("Site not found.")
    return site


@site_staff_required
def manage_events(request, site_id):
    site = request.authorized_site
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    occurrences = EventOccurrence.objects.annotate(
        going_metric=Count(
            "registrations",
            filter=Q(registrations__response=Registration.Response.GOING),
            distinct=True,
        ),
        maybe_metric=Count(
            "registrations",
            filter=Q(registrations__response=Registration.Response.MAYBE),
            distinct=True,
        ),
        participants_metric=Count(
            "registrations__participants",
            filter=Q(
                registrations__payment_status__in=(
                    Registration.PaymentStatus.NOT_REQUIRED,
                    Registration.PaymentStatus.PAID,
                ),
                registrations__participants__status="active",
            ),
            distinct=True,
        ),
    )
    events_qs = Event.objects.for_site(site).prefetch_related(
        Prefetch("occurrences", queryset=occurrences)
    )
    if status in Event.Status.values:
        events_qs = events_qs.filter(status=status)
    else:
        status = "all"
    if query:
        events_qs = events_qs.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(host_name__icontains=query)
        )
    events = paginate(
        request,
        events_qs.order_by("title", "id"),
        per_page=20,
    )
    created_event_id = request.GET.get("created", "")
    for event in events:
        event.just_created = str(event.id) == created_event_id
        occurrences = list(event.occurrences.all())
        event.first_occurrence = occurrences[0] if occurrences else None
        for occurrence in occurrences:
            occurrence.metrics = {
                "going": occurrence.going_metric,
                "maybe": occurrence.maybe_metric,
                "participants": occurrence.participants_metric,
                "capacity_remaining": (
                    None
                    if occurrence.capacity is None
                    else max(0, occurrence.capacity - occurrence.participants_metric)
                ),
            }
    return render(
        request,
        "events/manage.html",
        {
            "site": site,
            "events": events,
            "page_obj": events,
            "query": query,
            "selected_status": status,
            "status_choices": Event.Status.choices,
            "canonical_domain": site.domains.filter(is_canonical=True).first(),
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def event_create(request, site_id):
    site = request.authorized_site
    form = EventForm(request.POST or None, request.FILES or None, site=site)
    if request.method == "POST" and form.is_valid():
        model_fields = {
            field: form.cleaned_data[field]
            for field in (
                "title",
                "slug",
                "description",
                "featured_image",
                "host_name",
                "visibility",
                "status",
                "recurrence",
                "recurrence_interval",
                "recurrence_until",
                "max_guests",
            )
        }
        try:
            event = create_event_series(
                site=site,
                creator=request.user,
                event_values=model_fields,
                first_start=form.cleaned_data["starts_at"],
                first_end=form.cleaned_data["ends_at"],
                venue_name=form.cleaned_data["venue_name"],
                venue_address=form.cleaned_data["venue_address"],
                capacity=form.cleaned_data["capacity"],
            )
        except IntegrityError:
            # clean_slug()'s uniqueness check and this insert aren't atomic -
            # a near-simultaneous double-submit can pass the check twice and
            # only collide here, on the database's own constraint.
            form.add_error(
                "slug", "That event URL is already in use. Try a different one."
            )
            return render(
                request, "events/event_form.html", {"site": site, "form": form}
            )
        record_audit_event(
            action="event.created",
            actor=request.user,
            site_id=site.id,
            target=event,
            summary={
                "visibility": event.visibility,
                "recurrence": event.recurrence,
                "occurrences": event.occurrences.count(),
            },
            request=request,
        )
        messages.success(request, "Event and its calendar occurrences were created.")
        return redirect(
            f"{reverse('events:manage', kwargs={'site_id': site.id})}?created={event.id}"
        )
    return render(request, "events/event_form.html", {"site": site, "form": form})


@site_staff_required
@require_http_methods(["GET", "POST"])
def event_edit(request, site_id, event_id):
    site = request.authorized_site
    event = get_object_or_404(Event.objects.for_site(site), pk=event_id)
    previous = {
        "title": event.title,
        "description": event.description,
        "host_name": event.host_name,
        "visibility": event.visibility,
        "status": event.status,
    }
    form = EventDetailsForm(
        request.POST or None,
        request.FILES or None,
        instance=event,
        site=site,
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                event = form.save()
        except IntegrityError:
            form.add_error(
                "slug", "That event URL is already in use. Try a different one."
            )
            return render(
                request,
                "events/event_edit.html",
                {"site": site, "event": event, "form": form},
            )
        record_audit_event(
            action="event.updated",
            actor=request.user,
            site_id=site.id,
            target=event,
            summary={"status": event.status, "visibility": event.visibility},
            request=request,
        )
        changed = any(
            getattr(event, field) != value for field, value in previous.items()
        )
        if (
            event.status == Event.Status.CANCELED
            and previous["status"] != Event.Status.CANCELED
        ):
            for occurrence in event.occurrences.exclude(
                status=EventOccurrence.Status.CANCELED
            ):
                occurrence.status = EventOccurrence.Status.CANCELED
                occurrence.canceled_by_event = True
                occurrence.save(
                    update_fields=("status", "canceled_by_event", "updated_at")
                )
                queue_occurrence_notice(occurrence, cancellation=True)
        elif (
            event.status == Event.Status.PUBLISHED
            and previous["status"] == Event.Status.CANCELED
        ):
            # Only restore dates this cancellation took down, not ones a
            # manager had already canceled individually beforehand, and never
            # a date that has since passed.
            for occurrence in event.occurrences.filter(
                status=EventOccurrence.Status.CANCELED,
                canceled_by_event=True,
                ends_at__gte=timezone.now(),
            ):
                occurrence.status = EventOccurrence.Status.SCHEDULED
                occurrence.canceled_by_event = False
                occurrence.save(
                    update_fields=("status", "canceled_by_event", "updated_at")
                )
                queue_occurrence_notice(
                    occurrence, revision_key=event.updated_at.isoformat()
                )
        elif changed and event.status == Event.Status.PUBLISHED:
            for occurrence in event.occurrences.filter(
                status=EventOccurrence.Status.SCHEDULED,
                ends_at__gte=timezone.now(),
            ):
                queue_occurrence_notice(
                    occurrence, revision_key=event.updated_at.isoformat()
                )
        messages.success(request, "Event details were saved.")
        return redirect("events:manage", site_id=site.id)
    return render(
        request,
        "events/event_edit.html",
        {"site": site, "event": event, "form": form},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def occurrence_edit(request, site_id, occurrence_id):
    site = request.authorized_site
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site).select_related("event"), pk=occurrence_id
    )
    form = OccurrenceEditForm(request.POST or None, instance=occurrence, site=site)
    if request.method == "POST" and form.is_valid():
        values = {
            key: form.cleaned_data[key]
            for key in (
                "starts_at",
                "ends_at",
                "venue_name",
                "venue_address",
                "capacity",
                "status",
            )
        }
        updated = update_occurrences_from(
            occurrence=occurrence,
            scope=form.cleaned_data["scope"],
            values=values,
        )
        if form.cleaned_data["status"] == EventOccurrence.Status.CANCELED:
            for item in updated:
                queue_occurrence_notice(item, cancellation=True)
        else:
            for item in updated:
                queue_occurrence_notice(item)
        record_audit_event(
            action="event.occurrences.updated",
            actor=request.user,
            site_id=site.id,
            target=occurrence.event,
            summary={"scope": form.cleaned_data["scope"], "count": len(updated)},
            request=request,
        )
        messages.success(request, f"{len(updated)} occurrence(s) were updated.")
        return redirect("events:manage", site_id=site.id)
    return render(
        request,
        "events/occurrence_form.html",
        {"site": site, "occurrence": occurrence, "form": form},
    )


@site_staff_required
def album_list(request, site_id):
    site = request.authorized_site
    albums = (
        EventAlbum.objects.for_site(site)
        .select_related("occurrence__event", "cover_photo")
        .annotate(photo_count=Count("photos"))
    )
    return render(
        request,
        "events/album_list.html",
        {"site": site, "albums": albums},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def album_create(request, site_id):
    site = request.authorized_site
    initial = {}
    requested_occurrence = request.GET.get("occurrence", "")
    if requested_occurrence:
        initial["occurrence"] = requested_occurrence
    form = EventAlbumCreateForm(request.POST or None, site=site, initial=initial)
    if request.method == "POST" and form.is_valid():
        album = form.save(commit=False)
        album.site = site
        album.created_by = request.user
        try:
            with transaction.atomic():
                album.save()
        except IntegrityError:
            form.add_error(
                "slug", "That album URL is already in use. Try a different one."
            )
            return render(
                request, "events/album_form.html", {"site": site, "form": form}
            )
        record_audit_event(
            action="event.album.created",
            actor=request.user,
            site_id=site.id,
            target=album,
            summary={"occurrence_id": str(album.occurrence_id)},
            request=request,
        )
        messages.success(request, "Album created. Add photos, then publish it.")
        return redirect("events:album_edit", site_id=site.id, album_id=album.id)
    return render(
        request,
        "events/album_form.html",
        {"site": site, "form": form},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def album_edit(request, site_id, album_id):
    site = request.authorized_site
    album = get_object_or_404(
        EventAlbum.objects.for_site(site).select_related("occurrence__event"),
        pk=album_id,
    )
    previous_status = album.status
    form = EventAlbumEditForm(request.POST or None, instance=album, site=site)
    if request.method == "POST" and form.is_valid():
        album = form.save(commit=False)
        if (
            album.status == EventAlbum.Status.PUBLISHED
            and previous_status != EventAlbum.Status.PUBLISHED
        ):
            album.published_at = timezone.now()
        elif album.status == EventAlbum.Status.DRAFT:
            album.published_at = None
        try:
            with transaction.atomic():
                album.save()
        except IntegrityError:
            form.add_error(
                "slug", "That album URL is already in use. Try a different one."
            )
            return render(
                request,
                "events/album_edit.html",
                {
                    "site": site,
                    "album": album,
                    "form": form,
                    "photo_form": EventPhotoUploadForm(album=album),
                    "photos": album.photos.all(),
                    "public_hostname": site.domains.get(is_canonical=True).hostname,
                },
            )
        record_audit_event(
            action="event.album.updated",
            actor=request.user,
            site_id=site.id,
            target=album,
            summary={"status": album.status},
            request=request,
        )
        messages.success(request, "Album details were saved.")
        return redirect("events:album_edit", site_id=site.id, album_id=album.id)
    return render(
        request,
        "events/album_edit.html",
        {
            "site": site,
            "album": album,
            "form": form,
            "photo_form": EventPhotoUploadForm(album=album),
            "photos": album.photos.all(),
            "public_hostname": site.domains.get(is_canonical=True).hostname,
        },
    )


@site_staff_required
@require_POST
def album_photo_upload(request, site_id, album_id):
    site = request.authorized_site
    album = get_object_or_404(
        EventAlbum.objects.for_site(site).select_related("occurrence__event", "site"),
        pk=album_id,
    )
    form = EventPhotoUploadForm(request.POST, request.FILES, album=album)
    if form.is_valid():
        alt_text = form.default_alt_text()
        next_position = (
            album.photos.aggregate(highest=Max("position"))["highest"] or 0
        ) + 1
        created = []
        with transaction.atomic():
            for offset, (full, thumbnail) in enumerate(form.cleaned_data["images"]):
                photo = EventPhoto(
                    site=site,
                    album=album,
                    alt_text=alt_text,
                    position=next_position + offset,
                    uploaded_by=request.user,
                )
                photo.image = full
                photo.thumbnail = thumbnail
                photo.save()
                created.append(photo)
            if album.cover_photo_id is None and created:
                album.cover_photo = created[0]
                album.save(update_fields=("cover_photo", "updated_at"))
        record_audit_event(
            action="event.photo.uploaded",
            actor=request.user,
            site_id=site.id,
            target=album,
            summary={"album_id": str(album.id), "photo_count": len(created)},
            request=request,
        )
        messages.success(
            request,
            f"{len(created)} photo{'' if len(created) == 1 else 's'} added. "
            "Add captions or reorder them below.",
        )
        return redirect("events:album_edit", site_id=site.id, album_id=album.id)
    return render(
        request,
        "events/album_edit.html",
        {
            "site": site,
            "album": album,
            "form": EventAlbumEditForm(instance=album, site=site),
            "photo_form": form,
            "photos": album.photos.all(),
            "public_hostname": site.domains.get(is_canonical=True).hostname,
        },
        status=400,
    )


@site_staff_required
@require_POST
def album_photo_reorder(request, site_id, album_id):
    """Persist a drag-and-drop reordering of an album's photos."""
    site = request.authorized_site
    album = get_object_or_404(EventAlbum.objects.for_site(site), pk=album_id)
    ordered_ids = request.POST.getlist("photo_ids")
    if not ordered_ids:
        return JsonResponse({"error": "No photo order was submitted."}, status=400)

    photos = {
        str(photo.id): photo
        for photo in EventPhoto.objects.for_site(site).filter(album=album)
    }
    if set(ordered_ids) != set(photos):
        return JsonResponse(
            {"error": "That order does not match this album."}, status=400
        )

    updated = []
    for position, photo_id in enumerate(ordered_ids, start=1):
        photo = photos[photo_id]
        if photo.position != position:
            photo.position = position
            updated.append(photo)
    if updated:
        EventPhoto.objects.bulk_update(updated, ["position"])
        record_audit_event(
            action="event.album.reordered",
            actor=request.user,
            site_id=site.id,
            target=album,
            summary={"photo_count": len(ordered_ids)},
            request=request,
        )
    return JsonResponse({"status": "saved", "photo_count": len(ordered_ids)})


@site_staff_required
@require_POST
def album_cover_set(request, site_id, album_id, photo_id):
    site = request.authorized_site
    album = get_object_or_404(EventAlbum.objects.for_site(site), pk=album_id)
    photo = get_object_or_404(
        EventPhoto.objects.for_site(site), pk=photo_id, album=album
    )
    album.cover_photo = photo
    album.save(update_fields=("cover_photo", "updated_at"))
    messages.success(request, "Album cover updated.")
    return redirect("events:album_edit", site_id=site.id, album_id=album.id)


@site_staff_required
@require_http_methods(["GET", "POST"])
def album_photo_edit(request, site_id, album_id, photo_id):
    site = request.authorized_site
    album = get_object_or_404(EventAlbum.objects.for_site(site), pk=album_id)
    photo = get_object_or_404(
        EventPhoto.objects.for_site(site), pk=photo_id, album=album
    )
    form = EventPhotoEditForm(request.POST or None, instance=photo)
    if request.method == "POST" and form.is_valid():
        photo = form.save()
        record_audit_event(
            action="event.photo.updated",
            actor=request.user,
            site_id=site.id,
            target=photo,
            summary={"album_id": str(album.id)},
            request=request,
        )
        messages.success(request, "Photo details were saved.")
        return redirect("events:album_edit", site_id=site.id, album_id=album.id)
    return render(
        request,
        "events/photo_edit.html",
        {"site": site, "album": album, "photo": photo, "form": form},
    )


@site_staff_required
@require_POST
def album_photo_delete(request, site_id, album_id, photo_id):
    site = request.authorized_site
    album = get_object_or_404(EventAlbum.objects.for_site(site), pk=album_id)
    photo = get_object_or_404(
        EventPhoto.objects.for_site(site), pk=photo_id, album=album
    )
    storage = photo.image.storage
    stored_names = [photo.image.name]
    if photo.thumbnail:
        stored_names.append(photo.thumbnail.name)
    was_cover = album.cover_photo_id == photo.id
    record_audit_event(
        action="event.photo.deleted",
        actor=request.user,
        site_id=site.id,
        target=photo,
        summary={"album_id": str(album.id)},
        request=request,
    )
    photo.delete()
    update_fields = []
    if was_cover:
        album.cover_photo = album.photos.first()
        update_fields.append("cover_photo")
    emptied_a_published_album = (
        album.status == EventAlbum.Status.PUBLISHED and not album.photos.exists()
    )
    if emptied_a_published_album:
        # EventAlbumEditForm already refuses to publish an album with no
        # photos - deleting the last one must enforce the same rule instead
        # of leaving "Published" showing in the admin while the album
        # silently vanishes from the public gallery and 404s nowhere but
        # renders empty at its own direct URL.
        album.status = EventAlbum.Status.DRAFT
        update_fields.append("status")
    if update_fields:
        album.save(update_fields=(*update_fields, "updated_at"))

    def _remove_files():
        for name in stored_names:
            storage.delete(name)

    transaction.on_commit(_remove_files, robust=True)
    messages.success(request, "Photo deleted.")
    if emptied_a_published_album:
        messages.warning(
            request,
            "This album had no photos left, so it was moved back to Draft.",
        )
    return redirect("events:album_edit", site_id=site.id, album_id=album.id)


@site_staff_required
@require_http_methods(["GET", "POST"])
def invite_contacts(request, site_id, occurrence_id):
    site = request.authorized_site
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site).select_related("event"), pk=occurrence_id
    )
    form = InvitationForm(request.POST or None, site=site)
    if request.method == "POST" and form.is_valid():
        invitations = create_invitations(
            site=site,
            occurrence=occurrence,
            contacts=form.cleaned_data["contacts"],
            actor=request.user,
        )
        hostname = site.domains.get(is_canonical=True).hostname
        scheme = "https" if request.is_secure() else "http"
        for invitation, token in invitations:
            response_path = reverse(
                "events:invitation_response", kwargs={"token": token}
            )
            queue_invitation(
                invitation=invitation,
                token=token,
                response_url=f"{scheme}://{hostname}{response_path}",
            )
        invitation_count = len(invitations)
        if invitation_count == 1:
            success_message = "Invitation is being sent to 1 person."
        else:
            success_message = (
                f"Invitations are being sent to {invitation_count} people."
            )
        success_message += (
            " Most emails arrive within a few minutes; allow up to 10 minutes."
        )
        messages.success(request, success_message)
        return redirect("events:manage", site_id=site.id)
    return render(
        request,
        "events/invite_form.html",
        {"site": site, "occurrence": occurrence, "form": form},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def manager_response(request, site_id, occurrence_id):
    site = request.authorized_site
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site).select_related("event"), pk=occurrence_id
    )
    form = ManagerResponseForm(request.POST or None, site=site, occurrence=occurrence)
    if request.method == "POST" and form.is_valid():
        try:
            registration, history = save_response(
                occurrence=occurrence,
                contact=form.cleaned_data["contact"],
                response=form.cleaned_data["response"],
                guests=form.guest_data(),
                source=Registration.Source.MANAGER,
                actor=request.user,
            )
        except (CapacityExceeded, RegistrationUnavailable) as exc:
            form.add_error(None, str(exc))
        else:
            queue_confirmation(registration, history)
            messages.success(request, "The response was recorded.")
            return redirect(
                "attendance:roster", site_id=site.id, occurrence_id=occurrence.id
            )
    return render(
        request,
        "events/manager_response_form.html",
        {
            "site": site,
            "occurrence": occurrence,
            "form": form,
            "paid_event": form.paid_event,
            "guest_groups": [
                {
                    "number": index,
                    "first_name": form[f"guest_{index}_first_name"],
                    "last_name": form[f"guest_{index}_last_name"],
                    "email": form[f"guest_{index}_email"],
                    "phone": form[f"guest_{index}_phone"],
                }
                for index in range(1, occurrence.event.max_guests + 1)
            ],
        },
    )


@site_staff_required
@require_POST
def cancel_event(request, site_id, event_id):
    site = request.authorized_site
    event = get_object_or_404(Event.objects.for_site(site), pk=event_id)
    event.status = Event.Status.CANCELED
    event.save(update_fields=("status", "updated_at"))
    occurrences = list(
        event.occurrences.exclude(status=EventOccurrence.Status.CANCELED)
    )
    for occurrence in occurrences:
        occurrence.status = EventOccurrence.Status.CANCELED
        occurrence.canceled_by_event = True
        occurrence.save(
            update_fields=("status", "canceled_by_event", "updated_at")
        )
        queue_occurrence_notice(occurrence, cancellation=True)
    record_audit_event(
        action="event.canceled",
        actor=request.user,
        site_id=site.id,
        target=event,
        summary={"occurrences": len(occurrences)},
        request=request,
    )
    messages.success(
        request,
        "The event was canceled. Notices are being sent to affected attendees.",
    )
    return redirect("events:manage", site_id=site.id)


def public_event_image(request, slug):
    site = _public_site(request)
    event = get_object_or_404(
        Event.objects.for_site(site),
        slug=slug,
        status=Event.Status.PUBLISHED,
        visibility__in=(Event.Visibility.PUBLIC, Event.Visibility.UNLISTED),
    )
    if not event.featured_image:
        raise Http404("Event image not found.")
    response = redirect(event.featured_image.url)
    response["Cache-Control"] = "public, max-age=300"
    return response


def photo_album_list(request):
    site = _public_site(request)
    albums = list(
        EventAlbum.objects.for_site(site)
        .filter(
            status=EventAlbum.Status.PUBLISHED,
            occurrence__ends_at__lte=timezone.now(),
        )
        .annotate(photo_count=Count("photos"))
        .filter(photo_count__gt=0)
        .select_related("occurrence__event", "cover_photo")
        .prefetch_related("photos")
    )
    for album in albums:
        # Read from the prefetch cache. Calling .first() here would issue a
        # fresh LIMIT 1 query per album and bypass the prefetch entirely.
        album.display_cover = album.cover_photo or next(iter(album.photos.all()), None)
    return render(
        request,
        "public/photo_albums.html",
        {"site": site, "albums": albums},
    )


def photo_album_detail(request, slug):
    site = _public_site(request)
    album = get_object_or_404(
        EventAlbum.objects.for_site(site)
        .filter(
            status=EventAlbum.Status.PUBLISHED,
            occurrence__ends_at__lte=timezone.now(),
        )
        .annotate(photo_count=Count("photos"))
        .filter(photo_count__gt=0)
        .select_related("occurrence__event")
        .prefetch_related("photos"),
        slug=slug,
    )
    return render(
        request,
        "public/photo_album_detail.html",
        {"site": site, "album": album, "photos": album.photos.all()},
    )


def calendar(request):
    site = _public_site(request)
    occurrences = (
        EventOccurrence.objects.for_site(site)
        .filter(
            event__status=Event.Status.PUBLISHED,
            event__visibility=Event.Visibility.PUBLIC,
            status=EventOccurrence.Status.SCHEDULED,
            ends_at__gte=timezone.now(),
        )
        .select_related("event")
    )
    return render(
        request,
        "public/calendar.html",
        {"site": site, "occurrences": occurrences},
    )


def event_detail(request, slug):
    site = _public_site(request)
    event = get_object_or_404(
        Event.objects.for_site(site).filter(
            status=Event.Status.PUBLISHED,
            visibility__in=(Event.Visibility.PUBLIC, Event.Visibility.UNLISTED),
        ),
        slug=slug,
    )
    occurrences = event.occurrences.filter(
        status=EventOccurrence.Status.SCHEDULED, ends_at__gte=timezone.now()
    )
    return render(
        request,
        "public/event_detail.html",
        {"site": site, "event": event, "occurrences": occurrences},
    )


def occurrence_detail(request, slug, occurrence_id):
    site = _public_site(request)
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site)
        .select_related("event")
        .filter(
            event__slug=slug,
            event__status=Event.Status.PUBLISHED,
            event__visibility__in=(
                Event.Visibility.PUBLIC,
                Event.Visibility.UNLISTED,
            ),
            status=EventOccurrence.Status.SCHEDULED,
        ),
        pk=occurrence_id,
    )
    # site is joined because effective_refund_policy falls back to the
    # site default, and this list renders on a public page.
    ticket_types = occurrence.ticket_types.filter(is_active=True).select_related("site")
    for ticket_type in ticket_types:
        ticket_type.price_display = Decimal(ticket_type.amount_cents) / 100
        ticket_type.inventory = ticket_inventory(ticket_type)
        ticket_type.available_now = (
            ticket_type.sales_are_open() and ticket_type.inventory["remaining"] > 0
        )
    public_reviews = occurrence.reviews.filter(deleted_at__isnull=True).exclude(
        moderation_status="hidden"
    )
    rating_summary = public_reviews.aggregate(average=Avg("rating"))
    return render(
        request,
        "public/occurrence_detail.html",
        {
            "site": site,
            "event": occurrence.event,
            "occurrence": occurrence,
            "metrics": occurrence_metrics(occurrence),
            "ticket_types": ticket_types,
            "reviews": public_reviews,
            "review_average": rating_summary["average"],
            "review_count": public_reviews.count(),
        },
    )


@require_http_methods(["GET", "POST"])
@public_write_rate_limit("public-rsvp-manage")
def public_response_manage(request, slug, occurrence_id, token):
    site = _public_site(request)
    registration = public_registration_for_token(site=site, token=token)
    if (
        registration is None
        or registration.occurrence_id != occurrence_id
        or registration.occurrence.event.slug != slug
    ):
        raise Http404("RSVP management link not found.")

    occurrence = registration.occurrence
    form = RSVPForm(
        request.POST or None,
        occurrence=occurrence,
        contact=registration.contact,
    )
    if request.method == "POST" and form.is_valid():
        try:
            registration, history = save_response(
                occurrence=occurrence,
                contact=registration.contact,
                response=form.cleaned_data["response"],
                guests=form.guest_data(),
                source=Registration.Source.PUBLIC,
            )
        except (CapacityExceeded, RegistrationUnavailable) as exc:
            form.add_error(None, str(exc))
        else:
            queue_confirmation(registration, history)
            notify_registration_response(registration, history)
            return render(
                request,
                "public/rsvp_complete.html",
                {
                    "site": site,
                    "registration": registration,
                    "event_url": public_occurrence_url(registration.occurrence),
                    "checkout_token": (
                        registration_checkout_token(registration)
                        if registration.payment_status
                        == Registration.PaymentStatus.PENDING
                        else ""
                    ),
                },
            )
    return render(
        request,
        "public/rsvp_form.html",
        {
            "site": site,
            "occurrence": occurrence,
            "form": form,
            "manage_response": True,
        },
    )


@require_http_methods(["GET", "POST"])
@public_write_rate_limit("public-rsvp")
def public_response(request, slug, occurrence_id):
    site = _public_site(request)
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site).select_related("event"),
        pk=occurrence_id,
        event__slug=slug,
        event__status=Event.Status.PUBLISHED,
        event__visibility__in=(Event.Visibility.PUBLIC, Event.Visibility.UNLISTED),
        status=EventOccurrence.Status.SCHEDULED,
        ends_at__gte=timezone.now(),
    )
    form = RSVPForm(request.POST or None, occurrence=occurrence)
    if request.method == "POST" and form.is_valid():
        try:
            registration, history = save_public_response(
                site=site,
                occurrence=occurrence,
                response=form.cleaned_data["response"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=form.cleaned_data["email"],
                guests=form.guest_data(),
            )
        except PublicResponseAlreadyExists as exc:
            existing_registration = get_object_or_404(
                Registration.objects.for_site(site).select_related(
                    "contact", "occurrence__event"
                ),
                pk=exc.registration_id,
                occurrence=occurrence,
            )
            queue_rsvp_manage_link(existing_registration)
            return render(
                request,
                "public/rsvp_access_sent.html",
                {"site": site, "occurrence": occurrence},
            )
        except (CapacityExceeded, RegistrationUnavailable) as exc:
            form.add_error(None, str(exc))
        else:
            queue_confirmation(registration, history)
            notify_registration_response(registration, history)
            return render(
                request,
                "public/rsvp_complete.html",
                {
                    "site": site,
                    "registration": registration,
                    "event_url": public_occurrence_url(registration.occurrence),
                    "checkout_token": (
                        registration_checkout_token(registration)
                        if registration.payment_status
                        == Registration.PaymentStatus.PENDING
                        else ""
                    ),
                },
            )
    return render(
        request,
        "public/rsvp_form.html",
        {"site": site, "occurrence": occurrence, "form": form},
    )


@require_http_methods(["GET", "POST"])
@public_write_rate_limit("invitation-rsvp")
def invitation_response(request, token):
    site = _public_site(request)
    invitation = invitation_for_token(site=site, token=token)
    if invitation is None:
        raise Http404("Invitation not found.")
    form = RSVPForm(
        request.POST or None,
        occurrence=invitation.occurrence,
        contact=invitation.contact,
    )
    if request.method == "POST" and form.is_valid():
        try:
            registration, history = save_response(
                occurrence=invitation.occurrence,
                contact=invitation.contact,
                response=form.cleaned_data["response"],
                guests=form.guest_data(),
                source=Registration.Source.INVITATION,
                invitation=invitation,
            )
        except (CapacityExceeded, RegistrationUnavailable) as exc:
            form.add_error(None, str(exc))
        else:
            queue_confirmation(registration, history)
            notify_registration_response(registration, history)
            return render(
                request,
                "public/rsvp_complete.html",
                {
                    "site": site,
                    "registration": registration,
                    "event_url": public_occurrence_url(registration.occurrence),
                    "checkout_token": (
                        registration_checkout_token(registration)
                        if registration.payment_status
                        == Registration.PaymentStatus.PENDING
                        else ""
                    ),
                },
            )
    return render(
        request,
        "public/invitation_response.html",
        {"site": site, "invitation": invitation, "form": form},
    )
