"""Unified gateway layer for Paystack and Flutterwave.

Each gateway exposes the same small set of operations, so views never branch on
provider. Amounts are Decimal in naira at this boundary; each client converts to
the unit its API expects (kobo for Paystack, naira for Flutterwave).
"""
import json
import urllib.request
from decimal import Decimal, InvalidOperation

from django.conf import settings


class GatewayError(Exception):
    """Raised when a gateway cannot be reached or rejects a request."""


def _request(url, *, secret, method='GET', payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {
        'Authorization': f'Bearer {secret}',
        # Paystack's Cloudflare blocks the default Python-urllib User-Agent (403, error 1010).
        'User-Agent': 'flowPay/1.0',
    }
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.load(resp)
    except (OSError, ValueError) as exc:
        raise GatewayError(f'Could not reach the gateway: {exc}') from exc
    if not result.get('status'):
        raise GatewayError(result.get('message') or 'The gateway rejected the request.')
    return result


def _to_decimal(value):
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal('0')


class PaystackGateway:
    code = 'paystack'
    base = 'https://api.paystack.co'

    def __init__(self):
        self.secret = settings.PAYSTACK_SECRET_KEY

    def initiate_payment(self, *, email, amount, reference, currency, callback_url):
        result = _request(f'{self.base}/transaction/initialize', secret=self.secret, method='POST', payload={
            'email': email,
            'amount': int(amount * 100),  # kobo
            'reference': reference,
            'currency': currency,
            'callback_url': callback_url,
        })
        return result['data']['authorization_url']

    def verify_payment(self, reference):
        """Return a normalised dict: status, amount (naira), currency, reference."""
        data = _request(f'{self.base}/transaction/verify/{reference}', secret=self.secret)['data']
        return {
            'status': data.get('status'),
            'amount': _to_decimal(data.get('amount', 0)) / 100,
            'currency': data.get('currency'),
            'reference': data.get('reference'),
        }

    def list_banks(self):
        banks = _request(f'{self.base}/bank?currency=NGN&perPage=100', secret=self.secret)['data']
        return [{'name': b['name'], 'code': b['code']} for b in banks]

    def resolve_account(self, account_number, bank_code):
        data = _request(
            f'{self.base}/bank/resolve?account_number={account_number}&bank_code={bank_code}',
            secret=self.secret,
        )['data']
        return {'account_name': data['account_name'], 'account_number': data['account_number']}

    def create_transfer(self, *, reference, amount, currency, account_number, bank_code, name, narration):
        recipient = _request(f'{self.base}/transferrecipient', secret=self.secret, method='POST', payload={
            'type': 'nuban',
            'name': name,
            'account_number': account_number,
            'bank_code': bank_code,
            'currency': currency,
        })['data']
        _request(f'{self.base}/transfer', secret=self.secret, method='POST', payload={
            'source': 'balance',
            'amount': int(amount * 100),  # kobo
            'currency': currency,
            'reference': reference,
            'recipient': recipient['recipient_code'],
            'reason': narration,
        })
        return 'pending'

    def verify_transfer(self, reference):
        data = _request(f'{self.base}/transfer/verify/{reference}', secret=self.secret)['data']
        return {'status': data.get('status'), 'reference': data.get('reference')}


class FlutterwaveGateway:
    code = 'flutterwave'
    base = 'https://api.flutterwave.com/v3'

    def __init__(self):
        self.secret = settings.FLUTTERWAVE_SECRET_KEY

    def initiate_payment(self, *, email, amount, reference, currency, callback_url):
        result = _request(f'{self.base}/payments', secret=self.secret, method='POST', payload={
            'tx_ref': reference,
            'amount': str(amount),  # Flutterwave takes naira
            'currency': currency,
            'redirect_url': callback_url,
            'customer': {'email': email},
        })
        return result['data']['link']

    def verify_payment(self, reference):
        data = _request(
            f'{self.base}/transactions/verify_by_reference?tx_ref={reference}',
            secret=self.secret,
        )['data']
        return {
            'status': data.get('status'),  # 'successful', 'failed', ...
            'amount': _to_decimal(data.get('amount', 0)),
            'currency': data.get('currency'),
            'reference': data.get('tx_ref'),
        }

    def list_banks(self):
        banks = _request(f'{self.base}/banks/NG', secret=self.secret)['data']
        return [{'name': b['name'], 'code': b['code']} for b in banks]

    def resolve_account(self, account_number, bank_code):
        data = _request(f'{self.base}/accounts/resolve', secret=self.secret, method='POST', payload={
            'account_number': account_number,
            'account_bank': bank_code,
        })['data']
        return {'account_name': data['account_name'], 'account_number': account_number}

    def create_transfer(self, *, reference, amount, currency, account_number, bank_code, name, narration):
        data = _request(f'{self.base}/transfers', secret=self.secret, method='POST', payload={
            'account_bank': bank_code,
            'account_number': account_number,
            'amount': str(amount),
            'currency': currency,
            'reference': reference,
            'narration': narration,
            'beneficiary_name': name,
        })['data']
        return data.get('status', 'pending')

    def verify_transfer(self, reference):
        data = _request(f'{self.base}/transfers?reference={reference}', secret=self.secret)['data']
        transfer = data[0] if isinstance(data, list) and data else {}
        return {'status': transfer.get('status'), 'reference': transfer.get('reference')}


GATEWAYS = {
    PaystackGateway.code: PaystackGateway,
    FlutterwaveGateway.code: FlutterwaveGateway,
}


def get_gateway(code):
    """Return a gateway client for `code`, or raise KeyError for an unknown provider."""
    return GATEWAYS[code]()
