import json

from django.core.management.base import BaseCommand, CommandError

from ops.health import operational_alerts


class Command(BaseCommand):
    help = "Summarize recent operational exceptions for an external monitor."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--fail-on-alert", action="store_true")

    def handle(self, *args, **options):
        alerts = operational_alerts(hours=max(1, options["hours"]))
        payload = {"ok": not alerts, "alerts": alerts}
        if options["json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
        elif alerts:
            for alert in alerts:
                self.stdout.write(
                    f"{alert['severity'].upper()} {alert['code']}: "
                    f"{alert['label']} ({alert['count']})"
                )
        else:
            self.stdout.write(self.style.SUCCESS("No operational alerts."))
        if alerts and options["fail_on_alert"]:
            raise CommandError(f"{len(alerts)} operational alert(s) require attention.")
