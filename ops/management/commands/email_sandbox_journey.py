import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from communications.models import (
    OutboundMessage,
    ProviderCallbackEvent,
    UnsubscribeCapability,
)
from sites.models import Site


class Command(BaseCommand):
    help = "Check local evidence for the complete Resend email sandbox journey."

    def add_arguments(self, parser):
        parser.add_argument("site_slug")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        site = Site.objects.filter(slug=options["site_slug"]).first()
        if site is None:
            raise CommandError("Email sandbox site not found.")

        messages = OutboundMessage.objects.for_site(site).filter(
            channel=OutboundMessage.Channel.EMAIL,
            provider="resend",
        )
        provider_ids = messages.exclude(provider_message_id="").values_list(
            "provider_message_id", flat=True
        )
        successful_statuses = (
            OutboundMessage.Status.DELIVERED,
            OutboundMessage.Status.OPENED,
            OutboundMessage.Status.CLICKED,
        )
        processed_callbacks = ProviderCallbackEvent.objects.filter(
            provider="resend",
            provider_message_id__in=provider_ids,
            status=ProviderCallbackEvent.Status.PROCESSED,
        )
        checks = {
            "resend_selected": settings.EMAIL_DELIVERY_BACKEND == "resend",
            "api_key_configured": bool(settings.RESEND_API_KEY),
            "webhook_secret_configured": bool(settings.RESEND_WEBHOOK_SECRET),
            "transactional_delivered": messages.filter(
                is_marketing=False, status__in=successful_statuses
            ).exists(),
            "marketing_delivered": messages.filter(
                is_marketing=True, status__in=successful_statuses
            ).exists(),
            "delivery_callback_processed": processed_callbacks.filter(
                event_type__in=("delivered", "opened", "clicked")
            ).exists(),
            "suppression_callback_processed": (
                processed_callbacks.filter(
                    event_type__in=("bounced", "complained", "suppressed")
                ).exists()
                and messages.filter(
                    status__in=(
                        OutboundMessage.Status.BOUNCED,
                        OutboundMessage.Status.SUPPRESSED,
                    )
                ).exists()
            ),
            "unsubscribe_completed": UnsubscribeCapability.objects.for_site(site)
            .filter(channel=OutboundMessage.Channel.EMAIL, used_at__isnull=False)
            .exists(),
        }
        payload = {
            "ok": all(checks.values()),
            "site": site.slug,
            "checks": checks,
            "completed": sum(checks.values()),
            "total": len(checks),
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
        else:
            self.stdout.write(
                "Resend sandbox journey: PASS"
                if payload["ok"]
                else "Resend sandbox journey: INCOMPLETE"
            )
            for label, passed in checks.items():
                marker = "PASS" if passed else "MISSING"
                self.stdout.write(f"{marker}: {label}")
        if not payload["ok"]:
            raise CommandError("Resend sandbox journey evidence is incomplete.")
