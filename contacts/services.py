from django.db import transaction
from django.utils.text import slugify

from .models import ConsentRecord, ConsentStatus, Contact, ContactTag


def _record_consent(contact, channel, status, source):
    status_field = f"{channel}_consent_status"
    if (
        getattr(contact, status_field) == ConsentStatus.SUPPRESSED
        and status != ConsentStatus.SUPPRESSED
    ):
        return
    if getattr(contact, status_field) == status:
        return
    setattr(contact, status_field, status)
    contact.save(update_fields=(status_field, "updated_at"))
    ConsentRecord.objects.create(
        site=contact.site,
        contact=contact,
        channel=channel,
        status=status,
        source=source,
    )


def set_consent_status(*, contact, channel, status, source):
    _record_consent(contact, channel, status, source)


def update_contact_consent(
    contact, *, email_granted, sms_granted, source="manager_edit"
):
    _record_consent(
        contact,
        ConsentRecord.Channel.EMAIL,
        ConsentStatus.GRANTED if email_granted else ConsentStatus.WITHDRAWN,
        source,
    )
    _record_consent(
        contact,
        ConsentRecord.Channel.SMS,
        ConsentStatus.GRANTED if sms_granted else ConsentStatus.WITHDRAWN,
        source,
    )


def replace_contact_tags(contact, tag_names):
    tags = []
    for raw_name in tag_names:
        name = raw_name.strip()
        slug = slugify(name)[:60]
        if not name or not slug:
            continue
        tag, _ = ContactTag.objects.get_or_create(
            site=contact.site, slug=slug, defaults={"name": name[:50]}
        )
        tags.append(tag)
    contact.tags.set(tags)


@transaction.atomic
def save_contact_from_form(*, form, site, source="manager_edit"):
    contact = form.save(commit=False)
    contact.site = site
    contact.save()
    replace_contact_tags(contact, form.cleaned_data["tag_names"].split(","))
    update_contact_consent(
        contact,
        email_granted=form.cleaned_data["email_consent"],
        sms_granted=form.cleaned_data["sms_consent"],
        source=source,
    )
    return contact


@transaction.atomic
def subscribe_to_newsletter(*, site, email, first_name="", last_name="", source):
    normalized_email = email.strip().casefold()
    contact = (
        Contact.objects.for_site(site).filter(normalized_email=normalized_email).first()
    )
    if contact is None:
        contact = Contact.objects.create(
            site=site,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            email=normalized_email,
        )
    else:
        changed_fields = []
        if first_name.strip() and not contact.first_name:
            contact.first_name = first_name.strip()
            changed_fields.append("first_name")
        if last_name.strip() and not contact.last_name:
            contact.last_name = last_name.strip()
            changed_fields.append("last_name")
        if contact.archived_at is not None:
            contact.archived_at = None
            changed_fields.append("archived_at")
        if changed_fields:
            contact.save(update_fields=(*changed_fields, "updated_at"))
    _record_consent(
        contact,
        ConsentRecord.Channel.EMAIL,
        ConsentStatus.GRANTED,
        source,
    )
    return contact
