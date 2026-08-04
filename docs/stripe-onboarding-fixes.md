# Gather HQs: Stripe Connect onboarding fixes

Review date: August 3, 2026
Repo: `Dropbox/Projects/event_management`
Reviewed: `payments/gateway.py`, `payments/services.py`, `payments/views.py`, `payments/models.py`, `payments/urls.py`, `templates/payments/manage.html`

Goal: make the Connect onboarding flow safe to put in front of real customers before marketing starts.

---

## Priority 1: the return page shows a stale status (blocker)

**File:** `payments/views.py`
**Function:** `manage`

### The problem

`_account_link` sets the Stripe return URL to:

```python
return_url=manage_url + "?connect=returned",
```

Nothing reads that `connect` parameter. Neither `views.manage` nor `templates/payments/manage.html` looks at `request.GET`. The page renders whatever `ConnectedAccount.status` held before the user left for Stripe.

Stripe's `account.updated` webhook usually arrives within a second or two, so the row often catches up on its own. But you are racing it. If the webhook is slow, or is not wired up in the environment being tested, the user completes onboarding and lands on:

> Setup needed. Finish Stripe setup before selling.

That is the worst possible first impression for the exact flow being marketed.

### The fix

Add a refresh block at the top of `manage`. Everything below `ticket_types = list(...)` stays exactly as it is.

```python
@site_staff_required
def manage(request, site_id):
    site = request.authorized_site
    connected = ConnectedAccount.objects.filter(site=site).first()

    if connected and request.GET.get("connect") == "returned":
        try:
            connected = refresh_connected_account(connected)
        except (CommerceNotConfigured, stripe.StripeError):
            messages.warning(
                request,
                "We could not confirm your Stripe status just now. "
                "Try Refresh status in a moment.",
            )
        else:
            if connected.commerce_ready:
                messages.success(
                    request,
                    "Stripe setup is complete. You can start selling tickets.",
                )
            else:
                messages.info(
                    request,
                    "Stripe still needs a few details before you can accept payments.",
                )

    ticket_types = list(
        TicketType.objects.for_site(site)
        .select_related("occurrence__event")
        .order_by("occurrence__starts_at", "name")
    )
    # ... rest of the view unchanged
```

### Why each piece matters

- **`request.GET.get("connect") == "returned"`** gates the whole block, so it only fires on the trip back from Stripe. Normal page loads still cost zero Stripe API calls.
- **Reassigning `connected`** is the part that actually fixes the bug. The rest of the view and the template both read that variable, so the status pill and the Continue Stripe setup button reflect the fresh state in the same render, with no second page load.
- **`refresh_connected_account`** already handles its own failure bookkeeping through `record_connected_account_sync_failure`, which increments `sync_failure_count` and stores `last_sync_error`. Reusing it means no new error-tracking code.
- **`except (CommerceNotConfigured, stripe.StripeError)`** matches the pair already caught in `connect_start` and `connect_sync`. A Stripe outage degrades to the existing manual Refresh status button instead of a 500 on the page a new customer just landed on.
- **No new imports needed.** `refresh_connected_account`, `CommerceNotConfigured`, `stripe`, and `messages` are all already imported in `views.py`.

### Optional polish

After the refresh, redirect to the clean URL so a page reload does not trigger another Stripe API call:

```python
        return redirect("payments:manage", site_id=site.id)
```

Place it as the last line inside the `if connected and request.GET.get(...)` block. The message framework carries the success or warning across the redirect.

---

## Priority 2: raw exception text reaches the user

**File:** `payments/views.py`
**Functions:** `connect_start`, `connect_refresh`, `connect_sync`, `refund_order`

Current pattern:

```python
messages.error(request, f"Stripe onboarding could not start: {exc}")
```

This is fine while testing solo. Before customers see it, swap to a generic message and log the detail:

```python
    except (CommerceNotConfigured, stripe.StripeError):
        logger.exception("Connect onboarding failed for site %s", site_id)
        messages.error(
            request,
            "We could not reach Stripe just now. Please try again in a minute.",
        )
        return redirect("payments:manage", site_id=site_id)
```

- Requires adding `import logging` and `logger = logging.getLogger(__name__)` at the top of `views.py`. `services.py` already does this, so follow the same pattern.
- `logger.exception` inside an `except` block captures the full traceback automatically, so nothing is lost for debugging.

---

## Priority 3: reconnecting after a disconnect (defer unless it comes up)

**File:** `payments/services.py`
**Function:** `start_connected_account`

### The problem

```python
def start_connected_account(*, site):
    existing = ConnectedAccount.objects.filter(site=site).first()
    if existing:
        return existing
```

If a site deauthorizes in Stripe, `account.application.deauthorized` fires and `mark_connected_account_disconnected` sets status to `DISCONNECTED`. When that user clicks Connect Stripe again, this returns the dead row, `_account_link` builds an AccountLink against a deauthorized account, and Stripe errors out.

### Honest recommendation

This is rare, and a proper fix has real complexity: the Stripe idempotency key `gather-hqs-connect-account-{site.id}` would return the same dead account on retry, so a reconnect needs a distinct key, and historical `Order.connected_account_id` values still point at the old account, meaning refunds on old orders would fail against the new one.

For MVP, do the cheap version. Detect the state and route the user to you:

```python
def start_connected_account(*, site):
    existing = ConnectedAccount.objects.filter(site=site).first()
    if existing and existing.status == ConnectedAccount.Status.DISCONNECTED:
        raise CommerceUnavailable(
            "This Stripe account was disconnected. Contact support to reconnect."
        )
    if existing:
        return existing
    # ... unchanged
```

- `CommerceUnavailable` is a `ValidationError` subclass already defined in `services.py`, but note that `connect_start` currently only catches `CommerceNotConfigured` and `stripe.StripeError`. Add `CommerceUnavailable` to that except clause or the exception escapes as a 500.
- Handling reconnects by hand for the first few customers is the right call. Build the automated path only when the manual work becomes annoying.

---

## Test sequence

Run in Stripe **test mode**, with a Connect webhook endpoint pointed at:

```
https://gatherhqs.com/commerce/stripe/connect/
```

Confirm `STRIPE_CONNECT_WEBHOOK_SECRET` in Render matches that endpoint's signing secret, and that `STRIPE_SECRET_KEY` is in the same mode.

1. **Happy path.** Fresh site, click Connect Stripe, complete onboarding with Stripe test data. Confirm the return page immediately shows Payments ready.
2. **Abandoned onboarding.** Start onboarding, close the tab partway through. Return to the commerce page. Confirm Continue Stripe setup resumes the same account rather than creating a second one.
3. **Double click.** Submit Connect Stripe twice quickly. Confirm only one `acct_` id exists for the site. The idempotency key on `Account.create` should cover this.
4. **Expired link.** Let an account link sit until it expires, then use it. Confirm Stripe bounces to `connect_refresh` and issues a fresh link.
5. **Sell a ticket.** Buy one with a test card. Confirm the order reaches PAID, a Ticket row is created per participant, and `application_fee_cents` is populated at 3 percent (`TICKET_APPLICATION_FEE_BPS=300`).
6. **Refund it.** Confirm the refund succeeds, the order flips to REFUNDED, and `application_fee_refunded_cents` is proportional.
7. **Webhook replay.** Resend a `checkout.session.completed` event from the Stripe dashboard. Confirm the `ConnectWebhookEvent` row stays PROCESSED and no duplicate tickets are issued.

---

## What is already solid (no action needed)

- Idempotency keys on every Stripe write: account creation, checkout sessions, refunds, membership products and prices. Retries cannot double-charge or double-create.
- `ConnectWebhookEvent` inbox with a unique `stripe_event_id`, attempt counting, FAILED status, and a `retry_failed_connect_events` recovery path. Replays are safe.
- Every webhook handler cross-checks `event.account` against the stored `connected_account_id` and raises on mismatch. This is the multi-tenant failure mode most integrations miss.
- `require_commerce_ready` gates ticket type creation, membership plan creation, ticket checkout, and membership join. Nothing can be sold before onboarding completes.
- `reconcile_site_commerce` refreshes order, charge, and subscription state directly from Stripe, so webhooks are not the only source of truth.
- Inventory holds use `select_for_update` with expiry, and `Order` carries DB check constraints preventing fees from exceeding totals or refunds exceeding fees.
- `submit_refund` marks the row FAILED on a Stripe rejection instead of leaving it stuck at PENDING forever.

## Notes

- Render web service is on the **Basic** plan, so there is no spin-down and no cold-start risk on the webhook endpoint. Earlier free-plan concern no longer applies.
- Settings module is `config.settings.prod` (lowercase `settings`).
