import json
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.businesses.models import Business
from apps.payments.gateways import GatewayError
from apps.payments.models import Payment
from apps.providers.models import Provider
from apps.webhooks.models import WebhookEvent

HASH = 'flw-test-hash'
VERIFY = 'apps.payments.gateways.FlutterwaveGateway.verify_payment'


def verified(status='successful', amount='1000.00', currency='NGN', reference='pay_fw_1'):
    return {'status': status, 'amount': Decimal(amount), 'currency': currency, 'reference': reference}


@override_settings(FLUTTERWAVE_WEBHOOK_HASH=HASH, FLUTTERWAVE_SECRET_KEY='flw-test-secret')
class FlutterwaveWebhookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pw-123456')
        self.business = Business.objects.create(owner=self.user, name='Acme')
        self.provider = Provider.objects.create(code='flutterwave', name='Flutterwave')
        self.payment = Payment.objects.create(
            business=self.business, provider=self.provider,
            reference='pay_fw_1', amount=Decimal('1000.00'),
        )

    def post(self, body, token=HASH):
        headers = {'HTTP_VERIF_HASH': token} if token is not None else {}
        return self.client.post(
            reverse('webhooks:flutterwave'), data=json.dumps(body),
            content_type='application/json', **headers,
        )

    def flat_event(self, reference='pay_fw_1', status='successful', amount=1000):
        # Shape Flutterwave sent for a BANK_TRANSFER_TRANSACTION: transaction fields at the top level.
        return {'event.type': 'BANK_TRANSFER_TRANSACTION', 'txRef': reference,
                'status': status, 'amount': amount, 'currency': 'NGN'}

    def wrapped_event(self, reference='pay_fw_1', status='successful', amount=1000):
        return {'event': 'charge.completed', 'data': {
            'tx_ref': reference, 'status': status, 'amount': amount, 'currency': 'NGN'}}

    # --- authentication -------------------------------------------------------

    def test_missing_hash_is_rejected(self):
        with mock.patch(VERIFY) as api:
            response = self.post(self.flat_event(), token=None)
        self.assertEqual(response.status_code, 401)
        api.assert_not_called()
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_wrong_hash_is_rejected(self):
        with mock.patch(VERIFY) as api:
            response = self.post(self.flat_event(), token='guessed')
        self.assertEqual(response.status_code, 401)
        api.assert_not_called()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    @override_settings(FLUTTERWAVE_WEBHOOK_HASH='')
    def test_unconfigured_hash_rejects_everything(self):
        with mock.patch(VERIFY) as api:
            response = self.post(self.flat_event(), token='')
        self.assertEqual(response.status_code, 401)
        api.assert_not_called()

    # --- settlement -----------------------------------------------------------

    def test_flat_transaction_settles_from_verified_api_result(self):
        with mock.patch(VERIFY, return_value=verified()) as api:
            response = self.post(self.flat_event())
        self.assertEqual(response.status_code, 200)
        api.assert_called_once_with('pay_fw_1')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESSFUL)

    def test_wrapped_charge_completed_settles(self):
        with mock.patch(VERIFY, return_value=verified()):
            response = self.post(self.wrapped_event())
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESSFUL)

    def test_webhook_body_is_not_trusted_on_its_own(self):
        # The body claims success, but Flutterwave's API says the charge failed.
        with mock.patch(VERIFY, return_value=verified(status='failed')):
            response = self.post(self.flat_event(status='successful'))
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)

    def test_forged_amount_in_body_is_ignored(self):
        # The body says 1,000,000 but the verified charge is 1,000: no settlement at the wrong amount.
        with mock.patch(VERIFY, return_value=verified(amount='500.00')):
            self.post(self.flat_event(amount=1000000))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_amount_mismatch_is_not_settled(self):
        with mock.patch(VERIFY, return_value=verified(amount='10.00')):
            self.post(self.flat_event())
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertTrue(self.payment.events.filter(message__contains='does not match').exists())

    def test_non_ngn_currency_is_not_settled(self):
        with mock.patch(VERIFY, return_value=verified(currency='USD')):
            self.post(self.flat_event())
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertTrue(self.payment.events.filter(message__contains='non-NGN').exists())

    def test_unknown_reference_is_ignored(self):
        with mock.patch(VERIFY) as api:
            response = self.post(self.flat_event(reference='pay_unknown'))
        self.assertEqual(response.status_code, 200)
        api.assert_not_called()

    def test_gateway_outage_returns_500_so_flutterwave_retries(self):
        with mock.patch(VERIFY, side_effect=GatewayError('down')):
            response = self.post(self.flat_event())
        self.assertEqual(response.status_code, 500)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_duplicate_delivery_is_not_reprocessed(self):
        with mock.patch(VERIFY, return_value=verified()) as api:
            self.post(self.flat_event())
            response = self.post(self.flat_event())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(WebhookEvent.objects.count(), 1)


@override_settings(FLUTTERWAVE_SECRET_KEY='flw-test-secret')
class FlutterwaveCallbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pw-123456')
        self.business = Business.objects.create(owner=self.user, name='Acme')
        self.provider = Provider.objects.create(code='flutterwave', name='Flutterwave')
        self.payment = Payment.objects.create(
            business=self.business, provider=self.provider,
            reference='pay_fw_1', amount=Decimal('1000.00'),
        )

    def test_return_with_tx_ref_settles_after_verification(self):
        self.client.force_login(self.user)
        with mock.patch(VERIFY, return_value=verified()) as api:
            response = self.client.get(reverse('payments:callback'), {'tx_ref': 'pay_fw_1'})
        self.assertEqual(response.status_code, 200)
        api.assert_called_once_with('pay_fw_1')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESSFUL)

    def test_return_for_another_users_payment_is_not_found(self):
        other = User.objects.create_user(username='other', password='pw-123456')
        self.client.force_login(other)
        with mock.patch(VERIFY) as api:
            response = self.client.get(reverse('payments:callback'), {'tx_ref': 'pay_fw_1'})
        self.assertEqual(response.status_code, 404)
        api.assert_not_called()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_return_requires_login(self):
        response = self.client.get(reverse('payments:callback'), {'tx_ref': 'pay_fw_1'})
        self.assertEqual(response.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_return_with_non_ngn_currency_is_not_settled(self):
        self.client.force_login(self.user)
        with mock.patch(VERIFY, return_value=verified(currency='USD')):
            self.client.get(reverse('payments:callback'), {'tx_ref': 'pay_fw_1'})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
