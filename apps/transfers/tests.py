import json
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.beneficiaries.models import Beneficiary
from apps.businesses.models import Business
from apps.payments.gateways import GatewayError, PaystackGateway
from apps.providers.models import Provider
from apps.transfers.models import Transfer


class FakeGateway:
    """Stands in for a real gateway client so no HTTP call is made."""

    def __init__(self, transfer_status='pending', verify_status='success', fail=False):
        self.transfer_status = transfer_status
        self.verify_status = verify_status
        self.fail = fail

    def list_banks(self):
        return [{'name': 'Access Bank', 'code': '044'}]

    def resolve_account(self, account_number, bank_code):
        return {'account_name': 'Jane Doe', 'account_number': account_number}

    def initiate_payment(self, **kwargs):
        if self.fail:
            raise GatewayError('down')
        return 'https://checkout.example/abc'

    def create_transfer(self, **kwargs):
        if self.fail:
            raise GatewayError('down')
        return self.transfer_status

    def verify_transfer(self, reference):
        return {'status': self.verify_status, 'reference': reference}


class TransferFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='owner', password='pw-12345', email='o@example.com')
        self.client.force_login(self.user)
        self.business = Business.objects.create(owner=self.user, name='Acme')
        self.beneficiary = Beneficiary.objects.create(
            business=self.business, name='Jane Doe', account_number='0123456789', bank_code='044',
        )

    def post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type='application/json')

    def test_list_banks_returns_gateway_banks(self):
        with mock.patch('apps.transfers.views.get_gateway', return_value=FakeGateway()):
            resp = self.client.get('/transfers/banks/?provider=flutterwave')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['banks'][0]['code'], '044')

    def test_resolve_rejects_bad_account_number(self):
        resp = self.client.get('/transfers/resolve/?account_number=123&bank_code=044')
        self.assertEqual(resp.status_code, 400)

    def test_resolve_returns_account_name(self):
        with mock.patch('apps.transfers.views.get_gateway', return_value=FakeGateway()):
            resp = self.client.get('/transfers/resolve/?account_number=0123456789&bank_code=044')
        self.assertEqual(resp.json()['account_name'], 'Jane Doe')

    def test_initiate_creates_transfer_and_verify_marks_it_successful(self):
        with mock.patch('apps.transfers.views.get_gateway', return_value=FakeGateway()):
            resp = self.post_json('/transfers/initiate/', {
                'business_id': str(self.business.pk),
                'beneficiary_id': self.beneficiary.pk,
                'amount': '2500.00',
                'provider': 'flutterwave',
            })
        self.assertEqual(resp.status_code, 201)
        reference = resp.json()['reference']
        transfer = Transfer.objects.get(reference=reference)
        self.assertEqual(transfer.amount, Decimal('2500.00'))
        self.assertEqual(transfer.provider.code, 'flutterwave')

        with mock.patch('apps.transfers.views.get_gateway', return_value=FakeGateway(verify_status='success')):
            resp = self.client.get(f'/transfers/{reference}/verify/')
        self.assertEqual(resp.json()['status'], Transfer.Status.SUCCESSFUL)

    def test_failed_gateway_call_marks_transfer_failed(self):
        with mock.patch('apps.transfers.views.get_gateway', return_value=FakeGateway(fail=True)):
            resp = self.post_json('/transfers/initiate/', {
                'business_id': str(self.business.pk),
                'beneficiary_id': self.beneficiary.pk,
                'amount': '100',
            })
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(Transfer.objects.get().status, Transfer.Status.FAILED)

    def test_transfer_to_another_users_beneficiary_is_rejected(self):
        other = get_user_model().objects.create_user(username='other', password='pw-12345', email='x@example.com')
        other_business = Business.objects.create(owner=other, name='Other')
        resp = self.post_json('/transfers/initiate/', {
            'business_id': str(other_business.pk),
            'beneficiary_id': self.beneficiary.pk,
            'amount': '100',
        })
        self.assertEqual(resp.status_code, 400)


class UnifiedPaymentTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='payer', password='pw-12345', email='p@example.com')
        self.client.force_login(self.user)
        self.business = Business.objects.create(owner=self.user, name='Acme')

    def test_initiate_uses_selected_provider(self):
        with mock.patch('apps.payments.views.get_gateway', return_value=FakeGateway()):
            resp = self.client.post(
                '/payments/initiate/',
                data=json.dumps({'business_id': str(self.business.pk), 'amount': '1000', 'provider': 'flutterwave'}),
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['provider'], 'flutterwave')
        self.assertEqual(resp.json()['authorization_url'], 'https://checkout.example/abc')

    def test_unknown_provider_is_rejected(self):
        resp = self.client.post(
            '/payments/initiate/',
            data=json.dumps({'business_id': str(self.business.pk), 'amount': '1000', 'provider': 'nope'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)


class PaystackGatewayTests(TestCase):
    def test_list_banks_parses_paystack_response(self):
        payload = {'status': True, 'data': [{'name': 'GTBank', 'code': '058'}]}
        with mock.patch('apps.payments.gateways._request', return_value=payload):
            banks = PaystackGateway().list_banks()
        self.assertEqual(banks, [{'name': 'GTBank', 'code': '058'}])
