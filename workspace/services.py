from django.utils import timezone
from django.utils.text import slugify

from .models import Activity


def record_activity(
    *, site, verb, actor=None, detail="", kind="general", target_url=""
):
    return Activity.objects.create(
        site=site,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        verb=verb,
        detail=detail,
        kind=kind,
        target_url=target_url,
    )


def _render_template(value, context):
    text = str(value or "")
    for key, replacement in context.items():
        text = text.replace("{{ " + key + " }}", str(replacement or ""))
        text = text.replace("{{" + key + "}}", str(replacement or ""))
    return text


def run_automation_rule(rule, *, trigger_data=None, actor=None, contact=None):
    from .models import AutomationRun, WorkTask

    trigger_data = trigger_data or {}
    context = {
        key: value
        for key, value in trigger_data.items()
        if isinstance(value, (str, int, float))
    }
    try:
        if rule.action == rule.Action.CREATE_TASK:
            config = rule.action_config
            task = WorkTask.objects.create(
                site=rule.site,
                title=_render_template(config.get("title"), context)[:180],
                description=_render_template(config.get("description", ""), context),
                priority=config.get("priority", WorkTask.Priority.NORMAL),
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
            )
            detail = f"Created task: {task.title}"
        elif rule.action == rule.Action.ADD_CONTACT_TAG:
            if not contact:
                return AutomationRun.objects.create(
                    site=rule.site,
                    rule=rule,
                    status=AutomationRun.Status.SKIPPED,
                    trigger_data=trigger_data,
                    result_detail="No contact was available for the tag action.",
                )
            tag = str(rule.action_config.get("tag", "")).strip()
            # Contacts store tags through the existing contact service/model API when available.
            if hasattr(contact, "tags") and hasattr(contact.tags, "add"):
                from contacts.models import ContactTag

                tag_slug = slugify(tag)[:60] or "automation-tag"
                tag_obj, _ = ContactTag.objects.get_or_create(
                    site=rule.site, slug=tag_slug, defaults={"name": tag[:50]}
                )
                contact.tags.add(tag_obj)
                detail = f"Added contact tag: {tag}"
            else:
                return AutomationRun.objects.create(
                    site=rule.site,
                    rule=rule,
                    status=AutomationRun.Status.SKIPPED,
                    trigger_data=trigger_data,
                    result_detail="This contact model does not expose a tag relation.",
                )
        else:
            detail = _render_template(
                rule.action_config.get("message", rule.name), context
            )
            record_activity(
                site=rule.site, actor=actor, verb=detail[:180], kind="automation"
            )

        rule.last_run_at = timezone.now()
        rule.save(update_fields=("last_run_at", "updated_at"))
        run = AutomationRun.objects.create(
            site=rule.site,
            rule=rule,
            status=AutomationRun.Status.SUCCEEDED,
            trigger_data=trigger_data,
            result_detail=detail,
        )
        record_activity(
            site=rule.site,
            actor=actor,
            verb=f"Automation ran: {rule.name}",
            detail=detail,
            kind="automation",
        )
        return run
    except Exception as exc:
        return AutomationRun.objects.create(
            site=rule.site,
            rule=rule,
            status=AutomationRun.Status.FAILED,
            trigger_data=trigger_data,
            error_detail=str(exc)[:2000],
        )


def dispatch_automation_trigger(
    *, site, trigger, trigger_data=None, actor=None, contact=None
):
    from .models import AutomationRule

    runs = []
    for rule in AutomationRule.objects.for_site(site).filter(
        trigger=trigger, is_active=True
    ):
        expected_form = str(rule.trigger_config.get("form_id", "")).strip()
        actual_form = str((trigger_data or {}).get("form_id", "")).strip()
        if expected_form and expected_form != actual_form:
            continue
        runs.append(
            run_automation_rule(
                rule, trigger_data=trigger_data, actor=actor, contact=contact
            )
        )
    return runs
