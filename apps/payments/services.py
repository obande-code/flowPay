import json
import urllib.request
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction

from apps.audit.services import audit

from .models import Payment, PaymentEvent

PAYSTACK_VERIFY_URL = 'https://api.paystack.co/transaction/verify/{}'

# Gateway statuses that mean the money was definitely not taken.
FAILED_STATUSES = {'failed', 'reversed'}


def paystack_verify(reference):
    """Ask Paystack for the authoritative state of a transaction.

    Returns the transaction payload, or None when Paystack could not be reached.
    """
    req = urllib.request.Request(
        PAYSTACK_VERIFY_URL.format(reference),
        headers={
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
            # Paystack's Cloudflare blocks the default Python-urllib User-Agent (403, error 1010).
            'User-Agent': 'flowPay/1.0',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.load(resp)
    except (OSError, ValueError):
        # OSError covers HTTP errors and network failures; ValueError covers a bad JSON body.
        return None
    if not result.get('status'):
        return None
    return result.get('data') or {}


def record_event(payment, source, message):
    """Append an entry to a payment's history."""
    PaymentEvent.objects.create(
        payment=payment, source=source, status=payment.status, message=message,
    )


def settle_payment(payment, gateway_status, amount, source, provider_name):
    """Settle a pending payment from a gateway's verified state.

    `gateway_status` is the gateway's own status string ('success' for Paystack,
    'successful' for Flutterwave is normalised to 'success' by the caller). `amount`
    is the Decimal amount in naira, or None if the gateway did not report one.

    Shared by every route (webhook, callback, reconcile, Flutterwave) so they all
    apply the same rules. Returns True only when this call changed the status.
    """
    if gateway_status == 'success':
        if amount is None or amount != payment.amount:
            record_event(payment, source, f'{provider_name} reported an amount that does not match; not settled')
            return False
        new_status = Payment.Status.SUCCESSFUL
        message = f'{provider_name} confirmed the payment'
    elif gateway_status in FAILED_STATUSES:
        new_status = Payment.Status.FAILED
        message = f'{provider_name} reported the payment as {gateway_status}'
    else:
        # ongoing/pending/queued/processing/abandoned: the customer may still pay.
        return False

    with transaction.atomic():
        locked = Payment.objects.select_for_update().filter(
            pk=payment.pk, status=Payment.Status.PENDING
        ).first()
        if locked is None:
            return False
        locked.status = new_status
        locked.save(update_fields=['status'])
        payment = locked
        record_event(payment, source, message)
        audit('payment.settled', business=payment.business, reference=payment.reference,
              status=new_status, source=source, provider=provider_name)

    payment.status = new_status
    return True


def settle_from_paystack_data(payment, data, source):
    """Settle a pending payment from a Paystack transaction payload.

    Paystack reports amounts in kobo, so convert to naira before comparing.
    """
    try:
        amount = Decimal(str(data.get('amount', 0))) / 100
    except InvalidOperation:
        amount = None
    return settle_payment(payment, data.get('status'), amount, source, 'Paystack')
