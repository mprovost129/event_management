from django.conf import settings


def ticket_application_fee(amount_cents, *, basis_points=None):
    basis_points = (
        settings.TICKET_APPLICATION_FEE_BPS if basis_points is None else basis_points
    )
    if amount_cents <= 1 or basis_points <= 0:
        return 0
    rounded_fee = (amount_cents * basis_points + 5_000) // 10_000
    return min(amount_cents - 1, rounded_fee)


def proportional_fee_refund(*, fee_cents, refunded_cents, total_cents):
    if fee_cents <= 0 or refunded_cents <= 0 or total_cents <= 0:
        return 0
    if refunded_cents >= total_cents:
        return fee_cents
    return min(
        fee_cents,
        (fee_cents * refunded_cents + total_cents // 2) // total_cents,
    )
