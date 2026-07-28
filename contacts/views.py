from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from ops.services import record_audit_event
from sites.permissions import site_staff_required

from .forms import ContactForm
from .models import Contact
from .services import save_contact_from_form


@site_staff_required
def contact_list(request, site_id):
    site = request.authorized_site
    query = request.GET.get("q", "").strip()
    contacts = Contact.objects.for_site(site).filter(archived_at__isnull=True)
    if query:
        contacts = contacts.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
            | Q(tags__name__icontains=query)
        ).distinct()
    return render(
        request,
        "contacts/list.html",
        {"site": site, "contacts": contacts.prefetch_related("tags"), "query": query},
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
        return redirect("contacts:list", site_id=site.id)
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
