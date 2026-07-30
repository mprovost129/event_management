from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from core.pagination import paginate
from events.models import Registration
from ops.services import record_audit_event
from payments.models import Order
from sites.models import SiteRole
from sites.permissions import site_staff_required

from .forms import ContactForm
from .models import ConsentStatus, Contact, Member
from .services import save_contact_from_form


@site_staff_required
def contact_list(request, site_id):
    site = request.authorized_site
    query = request.GET.get("q", "").strip()
    selected_filter = request.GET.get("filter", "all")
    base_contacts = Contact.objects.for_site(site).filter(archived_at__isnull=True)
    summary = {
        "all": base_contacts.count(),
        "members": base_contacts.filter(
            membership__administrative_status=Member.AdministrativeStatus.ACTIVE
        ).count(),
        "email": base_contacts.filter(
            email_consent_status=ConsentStatus.GRANTED
        ).count(),
        "sms": base_contacts.filter(sms_consent_status=ConsentStatus.GRANTED).count(),
    }
    contacts = base_contacts
    if selected_filter == "members":
        contacts = contacts.filter(
            membership__administrative_status=Member.AdministrativeStatus.ACTIVE
        )
    elif selected_filter == "email":
        contacts = contacts.filter(email_consent_status=ConsentStatus.GRANTED)
    elif selected_filter == "sms":
        contacts = contacts.filter(sms_consent_status=ConsentStatus.GRANTED)
    else:
        selected_filter = "all"
    if query:
        contacts = contacts.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
            | Q(tags__name__icontains=query)
        ).distinct()
    page_obj = paginate(
        request,
        contacts.select_related("membership").prefetch_related("tags"),
    )
    created_contact_id = request.GET.get("created", "")
    for contact in page_obj.object_list:
        contact.just_created = str(contact.id) == created_contact_id
    return render(
        request,
        "contacts/list.html",
        {
            "site": site,
            "contacts": page_obj,
            "page_obj": page_obj,
            "query": query,
            "selected_filter": selected_filter,
            "summary": summary,
        },
    )


@site_staff_required
def contact_detail(request, site_id, contact_id):
    site = request.authorized_site
    contact = get_object_or_404(
        Contact.objects.for_site(site)
        .select_related("membership")
        .prefetch_related("tags", "consent_history"),
        pk=contact_id,
    )
    registrations = contact.event_registrations.select_related(
        "occurrence__event"
    ).order_by("-responded_at")
    invitations = contact.event_invitations.select_related(
        "occurrence__event"
    ).order_by("-created_at")
    orders = contact.orders.select_related("occurrence__event").order_by("-created_at")
    paid_orders = orders.filter(
        status__in=[
            Order.Status.PAID,
            Order.Status.PARTIALLY_REFUNDED,
            Order.Status.REFUNDED,
        ]
    )
    documents = contact.documents.all()
    if request.site_role.role != SiteRole.Role.SUBSCRIBER_ADMIN:
        documents = documents.exclude(visibility="admin")
    lifetime_spend_cents = paid_orders.aggregate(total=Sum("total_cents"))["total"] or 0
    stats = {
        "events_attended": registrations.filter(
            response=Registration.Response.GOING
        ).count(),
        "events_invited": invitations.count(),
        "responses": registrations.count(),
        "lifetime_spend": lifetime_spend_cents / 100,
    }
    timeline = []
    for registration in registrations[:30]:
        timeline.append(
            {
                "at": registration.responded_at,
                "label": f"Responded {registration.get_response_display()} to {registration.occurrence.event.title}",
                "kind": "event",
            }
        )
    for invitation in invitations[:30]:
        timeline.append(
            {
                "at": invitation.created_at,
                "label": f"Invited to {invitation.occurrence.event.title}",
                "kind": "invitation",
            }
        )
    for order in orders[:30]:
        timeline.append(
            {
                "at": order.created_at,
                "label": f"Order for {order.occurrence.event.title}: ${order.total_cents / 100:.2f} ({order.get_status_display()})",
                "kind": "payment",
            }
        )
    for document in documents[:30]:
        timeline.append(
            {
                "at": document.created_at,
                "label": f"Document uploaded: {document.title}",
                "kind": "document",
            }
        )
    timeline.sort(key=lambda item: item["at"], reverse=True)
    return render(
        request,
        "contacts/detail.html",
        {
            "site": site,
            "contact": contact,
            "stats": stats,
            "registrations": registrations[:20],
            "orders": orders[:20],
            "documents": documents,
            "timeline": timeline[:50],
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def contact_create(request, site_id):
    site = request.authorized_site
    form = ContactForm(request.POST or None, site=site)
    if request.method == "POST" and form.is_valid():
        contact = save_contact_from_form(form=form, site=site, source="manager_create")
        record_audit_event(
            action="contact.created",
            actor=request.user,
            site_id=site.id,
            target=contact,
            summary={"contact_id": str(contact.id)},
            request=request,
        )
        messages.success(request, "Contact was created.")
        return redirect(
            f"{reverse('contacts:list', kwargs={'site_id': site.id})}?created={contact.id}"
        )
    return render(request, "contacts/form.html", {"site": site, "form": form})


@site_staff_required
@require_http_methods(["GET", "POST"])
def contact_edit(request, site_id, contact_id):
    site = request.authorized_site
    contact = get_object_or_404(Contact.objects.for_site(site), pk=contact_id)
    form = ContactForm(request.POST or None, instance=contact, site=site)
    if request.method == "POST" and form.is_valid():
        contact = save_contact_from_form(form=form, site=site)
        record_audit_event(
            action="contact.updated",
            actor=request.user,
            site_id=site.id,
            target=contact,
            summary={"contact_id": str(contact.id)},
            request=request,
        )
        messages.success(request, "Contact was saved.")
        return redirect("contacts:list", site_id=site.id)
    return render(
        request,
        "contacts/form.html",
        {"site": site, "contact": contact, "form": form},
    )


@site_staff_required
@require_POST
def contact_archive(request, site_id, contact_id):
    site = request.authorized_site
    contact = get_object_or_404(Contact.objects.for_site(site), pk=contact_id)
    contact.archive()
    record_audit_event(
        action="contact.archived",
        actor=request.user,
        site_id=site.id,
        target=contact,
        summary={"contact_id": str(contact.id)},
        request=request,
    )
    messages.success(request, "Contact was archived.")
    return redirect("contacts:list", site_id=site.id)
