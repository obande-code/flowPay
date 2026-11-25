import json
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.businesses.models import Business
from apps.audit.services import audit
from apps.providers.models import Provider

from .gateways import GatewayError, get_gateway
from .models import Payment, PaymentEvent
from .services import paystack_verify, record_event, settle_from_paystack_data, settle_payment


@login_required
@require_POST
def initiate_payment(request):
    try:
        data = json.loads(request.body or b'{}')
        amount = Decimal(str(data['amount'])).quantize(Decimal('0.01'))
        business = Business.objects.get(pk=data['business_id'], owner=request.user)
        provider_code = data.get('provider', 'paystack')
    except (ValueError, KeyError, TypeError, InvalidOperation, ValidationError, Business.DoesNotExist):
        return JsonResponse({'error': 'Provide a valid amount and business_id.'}, status=400)

    if amount <= 0:
        return JsonResponse({'error': 'Amount must be greater than zero.'}, status=400)
    if not request.user.email:
        return JsonResponse({'error': 'Your account needs an email address before paying.'}, status=400)
    try:
        gateway = get_gateway(provider_code)
    except KeyError:
        return JsonResponse({'error': 'Unknown provider.'}, status=400)

    provider, _ = Provider.objects.get_or_create(
        code=provider_code, defaults={'name': provider_code.title()},
    )
    payment = Payment.objects.create(
        business=business,
        provider=provider,
        reference=f'pay_{uuid.uuid4().hex}',
        amount=amount,
        currency='NGN',
    )

    record_event(payment, PaymentEvent.Source.INITIATE, 'Checkout started')
    audit('payment.initiated', business=business, reference=payment.reference,
          amount=str(amount), provider=provider_code, user=request.user.pk)

    try:
        checkout_url = gateway.initiate_payment(
            email=request.user.email,
            amount=amount,
            reference=payment.reference,
            currency=payment.currency,
            callback_url=request.build_absolute_uri('/payments/callback/'),
        )
    except GatewayError:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=['status'])
        record_event(payment, PaymentEvent.Source.INITIATE, f'{provider.name} could not start checkout')
        return JsonResponse(
            {'error': f'{provider.name} could not initialize the payment.', 'reference': payment.reference},
            status=502,
        )

    return JsonResponse({
        'reference': payment.reference,
        'provider': provider_code,
        'authorization_url': checkout_url,
    }, status=201)


@login_required
def payment_detail(request, reference):
    """Show a payment's full history: every checkout, webhook and reconciliation step."""
    payment = get_object_or_404(
        Payment.objects.select_related('business', 'provider'),
        reference=reference, business__owner=request.user,
    )
    return render(request, 'payments/detail.html', {
        'payment': payment,
        'events': payment.events.all(),
    })


@login_required
def payment_callback(request):
    """Settle a payment when the customer comes back from Paystack's checkout.

    Paystack appends the transaction reference as a query parameter. This asks
    Paystack directly, so a payment still settles when its webhook never arrives.
    """
    # Paystack sends `reference`; Flutterwave sends `tx_ref`.
    reference = request.GET.get('reference') or request.GET.get('tx_ref', '')
    payment = Payment.objects.select_related('provider').filter(
        reference=reference, business__owner=request.user
    ).first()
    if payment is None:
        return render(
            request,
            'payments/callback.html',
            {'error': 'We could not find that payment.'},
            status=404,
        )

    if payment.status == Payment.Status.PENDING:
        if payment.provider.code == 'flutterwave':
            try:
                data = get_gateway('flutterwave').verify_payment(payment.reference)
            except GatewayError:
                data = None
            if data is None:
                return render(request, 'payments/callback.html', {
                    'payment': payment,
                    'error': 'We could not reach Flutterwave to confirm this payment yet.',
                })
            if data['currency'] == 'NGN':
                status = 'success' if data['status'] == 'successful' else data['status']
                settle_payment(payment, status, data['amount'], PaymentEvent.Source.CALLBACK, 'Flutterwave')
        else:
            data = paystack_verify(payment.reference)
            if data is None:
                return render(request, 'payments/callback.html', {
                    'payment': payment,
                    'error': 'We could not reach Paystack to confirm this payment yet.',
                })
            settle_from_paystack_data(payment, data, PaymentEvent.Source.CALLBACK)
        payment.refresh_from_db()

    return render(request, 'payments/callback.html', {'payment': payment})
