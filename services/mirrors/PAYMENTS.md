# Stripe order binding

This service uses fixed-price, one-time Checkout Sessions. A valid webhook signature authenticates its sender; it does not by itself prove that the session belongs to the referenced local order.

## Acceptance contract

For a paid Checkout event, Mirrors checks the saved order's Stripe provider, integer amount in minor units, currency, payment mode, owner metadata and session ID before granting access. When both metadata `order_no` and `client_reference_id` are supplied, they must agree. The original checkout flow supplies both references and `metadata[user_sub]`; client-reference fallback remains supported with the owner metadata and matching saved session.

Checkout creation also verifies returned amount/currency before redirecting the customer. Local product pricing must agree with the configured Stripe Price. Tax, discount, adaptive-currency pricing and subscription flows that change this fixed-price contract require a separately reviewed implementation; mismatches fail explicitly rather than granting access or silently treating the price as valid.

The creation response must be a JSON object with a nonempty session ID and an absolute HTTPS checkout URL. Missing or malformed URLs (including credentials, whitespace/control characters and invalid ports) and non-JSON responses fail with 502, mark the local order failed, and do not save a session binding or redirect. Stripe-hosted and configured custom-domain URLs are supported; this format check is not a domain ownership check.

`checkout.session.completed` and `checkout.session.async_payment_succeeded` share these checks and require `payment_status=paid`. Unpaid, zero-payment (`no_payment_required`) and unrelated event types do not grant access. The Checkout object supports an expandable PaymentIntent reference, so both its ID string and expanded object's ID are accepted. These shapes follow the [Checkout Session reference](https://docs.stripe.com/api/checkout/sessions/object) and [event-type reference](https://docs.stripe.com/api/events/types).

## Retries and refunds

Event receipt, order transition and entitlement mutation commit together. Invalid bindings roll back the receipt so a correctly resolved/retried event can be processed. Duplicate event IDs remain idempotent; another event for an already-paid or refunded payment never renews or reactivates access.

Stripe can deliver duplicates or events out of order; see [webhook delivery behavior](https://docs.stripe.com/webhooks#event-delivery-behaviors). A callback arriving before its local session is saved returns 409. A refund whose PaymentIntent is not yet uniquely bound to a Stripe order also returns 409, without consuming its event ID, allowing retry after checkout completion. An unrelated refund may therefore keep retrying and needs owner review. The existing policy of revoking the order entitlement on `charge.refunded` (including partial refunds) is unchanged. No Stripe fetch, refund, charge or account-setting action is performed by these guards.

## Migration and owner review

Startup adds `orders.stripe_session_id` with an empty-string default and copies existing `cs_` references into it. New checkout creation saves the session ID there; `provider_ref` still becomes the PaymentIntent for refund lookup. Migration is additive and idempotent.

Legacy paid/refunded orders may have lost their session ID. A matching already-recorded PaymentIntent can be acknowledged without any entitlement mutation. Pending orders without a trustworthy session binding fail closed and need operator reconciliation; the service does not guess identifiers or fetch production objects.

Before any separately authorized deployment, the owner should review payment/privacy behavior, back up operational data, verify local prices/currencies match Stripe, and verify the webhook destination includes the existing completed/refund events and delayed-success event if delayed methods are used. This PR does not change that destination or enable payment methods. Staging validation with the owner's authorized test environment remains required; repository tests use synthetic events and mocked HTTP only.

Rolling back code requires no column removal: the previous version ignores the additive column. It would also restore the missing binding checks. Prefer a forward fix; do not delete receipts, order history or entitlements to force retries.
