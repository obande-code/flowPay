import hashlib
import hmac
import json

from django.db import IntegrityError, transaction

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.payments.gateways import FlutterwaveGateway, GatewayError
from apps.payments.models import Payment, PaymentEvent
from apps.payments.services import record_event, settle_from_paystack_data, settle_payment
from apps.providers.models import Provider

from .models import WebhookEvent


@csrf_exempt
@require_POST
def paystack_webhook(request):
    # Paystack signs the raw body with HMAC-SHA512 using the secret key.
    signature = request.headers.get('x-paystack-signature', '')
    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode(), request.body, hashlib.sha512
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return HttpResponse(status=401)

    try:
        event = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)

    # Paystack redelivers the same body when it does not get a 200 back. The digest
    # of the raw body is unique per delivery, so a repeat is acknowledged and skipped.
    digest = hashlib.sha256(request.body).hexdigest()
    if WebhookEvent.objects.filter(digest=digest).exists():
        return HttpResponse(status=200)

    provider, _ = Provider.objects.get_or_create(code='paystack', defaults={'name': 'Paystack'})
    try:
        with transaction.atomic():
            webhook_event = WebhookEvent.objects.create(
                provider=provider,
                event_type=event.get('event', ''),
                digest=digest,
                payload=event,
            )
    except IntegrityError:
        # A concurrent delivery of the same body won the race; it is already recorded.
        return HttpResponse(status=200)

    if event.get('event') == 'charge.success':
        # The event type is the authority here: a signed charge.success is a success,
        # so do not depend on the payload repeating it in data.status.
        data = {**event.get('data', {}), 'status': 'success'}
        payment = Payment.objects.filter(reference=data.get('reference')).first()
        if payment:
            record_event(payment, PaymentEvent.Source.WEBHOOK, 'Received charge.success webhook')
            if settle_from_paystack_data(payment, data, PaymentEvent.Source.WEBHOOK):
                webhook_event.processed = True
                webhook_event.save(update_fields=['processed'])

    # Always acknowledge a verified event so Paystack does not retry it.
    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def flutterwave_webhook(request):
    # Flutterwave sends the secret hash you configured in its dashboard as the
    # verif-hash header. Without a configured hash, every request is rejected.
    expected = settings.FLUTTERWAVE_WEBHOOK_HASH
    signature = request.headers.get('verif-hash', '')
    if not expected or not hmac.compare_digest(signature, expected):
        return HttpResponse(status=401)

    try:
        event = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)

    digest = hashlib.sha256(request.body).hexdigest()
    if WebhookEvent.objects.filter(digest=digest).exists():
        return HttpResponse(status=200)

    provider, _ = Provider.objects.get_or_create(code='flutterwave', defaults={'name': 'Flutterwave'})
    try:
        with transaction.atomic():
            webhook_event = WebhookEvent.objects.create(
                provider=provider,
                event_type=event.get('event', ''),
                digest=digest,
                payload=event,
            )
    except IntegrityError:
        return HttpResponse(status=200)

    # Flutterwave sends two shapes: a `charge.completed` wrapper with the transaction
    # under `data`, and a flat transaction object (e.g. BANK_TRANSFER_TRANSACTION)
    # with `txRef` and `status` at the top level. Accept both.
    if event.get('event') == 'charge.completed':
        data = event.get('data', {})
    elif 'txRef' in event or 'tx_ref' in event:
        data = event
    else:
        data = None

    if data is not None:
        reference = data.get('tx_ref') or data.get('txRef')
        payment = Payment.objects.filter(reference=reference).first() if reference else None
        if payment:
            record_event(payment, PaymentEvent.Source.WEBHOOK, 'Received Flutterwave webhook')
            # The webhook body is not trusted on its own: confirm the transaction
            # with Flutterwave's API and settle only from that verified result.
            try:
                verified = FlutterwaveGateway().verify_payment(reference)
            except GatewayError:
                # Leave it pending; Flutterwave retries the webhook on a non-200.
                return HttpResponse(status=500)
            if verified['currency'] != 'NGN':
                record_event(payment, PaymentEvent.Source.WEBHOOK, 'Flutterwave reported a non-NGN currency; not settled')
            else:
                status = 'success' if verified['status'] == 'successful' else verified['status']
                if settle_payment(payment, status, verified['amount'], PaymentEvent.Source.WEBHOOK, 'Flutterwave'):
                    webhook_event.processed = True
                    webhook_event.save(update_fields=['processed'])

    return HttpResponse(status=200)
