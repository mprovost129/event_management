from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0004_connectedaccount_reconciliation_streak"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="application_fee_bps",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="order",
            name="application_fee_cents",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="order",
            name="application_fee_refunded_cents",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=Q(application_fee_bps__lte=9999),
                name="payments_order_application_fee_bps_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=Q(application_fee_cents__lte=F("total_cents")),
                name="payments_order_application_fee_not_over_total",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=Q(
                    application_fee_refunded_cents__lte=F("application_fee_cents")
                ),
                name="payments_order_fee_refund_not_over_fee",
            ),
        ),
    ]
