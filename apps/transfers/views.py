import json
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from apps.audit.services import audit
from apps.beneficiaries.models import Beneficiary
from apps.businesses.models import Business
from apps.payments.gateways import GatewayError, get_gateway
from apps.providers.models import Provider

from .models import Transfer


@login_required
@require_GET
def list_banks(request):
    provider = request.GET.get('provider', 'paystack')
    try:
        banks = get_gateway(provider).list_banks()
    except KeyError:
        return JsonResponse({'error': 'Unknown provider.'}, status=400)
    except GatewayError as exc:
        return JsonResponse({'error': str(exc)}, status=502)
    return JsonResponse({'banks': banks})


@login_required
@require_GET
def resolve_account(request):
    provider = request.GET.get('provider', 'paystack')
    account_number = request.GET.get('account_number', '')
    bank_code = request.GET.get('bank_code', '')
    if not (account_number.isdigit() and len(account_number) == 10 and bank_code):
        return JsonResponse({'error': 'Provide a 10-digit account_number and bank_code.'}, status=400)
    try:
        details = get_gateway(provider).resolve_account(account_number, bank_code)
    except KeyError:
        return JsonResponse({'error': 'Unknown provider.'}, status=400)
    except GatewayError as exc:
        return JsonResponse({'error': str(exc)}, status=502)
    return JsonResponse(details)


@login_required
@require_POST
def initiate_transfer(request):
    try:
        data = json.loads(request.body or b'{}')
        amount = Decimal(str(data['amount'])).quantize(Decimal('0.01'))
        business = Business.objects.get(pk=data['business_id'], owner=request.user)
        beneficiary = Beneficiary.objects.get(pk=data['beneficiary_id'], business=business)
        provider_code = data.get('provider', 'paystack')
        narration = str(data.get('narration', 'Transfer'))[:100]
    except (ValueError, KeyError, TypeError, InvalidOperation, ValidationError,
            Business.DoesNotExist, Beneficiary.DoesNotExist):
        return JsonResponse({'error': 'Provide a valid amount, business_id and beneficiary_id.'}, status=400)

    if amount <= 0:
        return JsonResponse({'error': 'Amount must be greater than zero.'}, status=400)

    try:
        gateway = get_gateway(provider_code)
    except KeyError:
        return JsonResponse({'error': 'Unknown provider.'}, status=400)

    provider, _ = Provider.objects.get_or_create(
        code=provider_code, defaults={'name': provider_code.title()},
    )
    transfer = Transfer.objects.create(
        business=business,
        beneficiary=beneficiary,
        provider=provider,
        reference=f'tr_{uuid.uuid4().hex}',
        amount=amount,
        currency='NGN',
    )

    audit('transfer.initiated', business=business, reference=transfer.reference,
          amount=str(amount), provider=provider_code, user=request.user.pk)
    try:
        status = gateway.create_transfer(
            reference=transfer.reference,
            amount=amount,
            currency=transfer.currency,
            account_number=beneficiary.account_number,
            bank_code=beneficiary.bank_code,
            name=beneficiary.name,
            narration=narration,
        )
    except GatewayError as exc:
        transfer.status = Transfer.Status.FAILED
        transfer.save(update_fields=['status'])
        audit('transfer.failed', business=business, reference=transfer.reference, error=str(exc))
        return JsonResponse(
            {'error': str(exc), 'reference': transfer.reference}, status=502,
        )

    return JsonResponse({
        'reference': transfer.reference,
        'status': status,
    }, status=201)


@login_required
@require_GET
def verify_transfer(request, reference):
    transfer = Transfer.objects.select_related('provider').filter(
        reference=reference, business__owner=request.user,
    ).first()
    if transfer is None:
        return JsonResponse({'error': 'Transfer not found.'}, status=404)

    try:
        result = get_gateway(transfer.provider.code).verify_transfer(reference)
    except (KeyError, GatewayError) as exc:
        return JsonResponse({'error': str(exc)}, status=502)

    gateway_status = (result.get('status') or '').lower()
    if gateway_status in ('success', 'successful', 'completed'):
        transfer.status = Transfer.Status.SUCCESSFUL
    elif gateway_status in ('failed', 'reversed', 'rejected'):
        transfer.status = Transfer.Status.FAILED
        transfer.save(update_fields=['status'])
        audit('transfer.failed', business=transfer.business, reference=transfer.reference,
              error=gateway_status)
        return JsonResponse({'reference': reference, 'status': transfer.status})

    transfer.save(update_fields=['status'])
    return JsonResponse({'reference': reference, 'status': transfer.status})

