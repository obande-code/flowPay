import hashlib
import hmac
import json
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.businesses.models import Business
from apps.providers.models import Provider
from apps.webhooks.models import WebhookEvent

from .models import Payment, PaymentEvent
from .services import settle_from_paystack_data

SECRET = 'test-secret'


def sign(body):
    return hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest()


@override_settings(PAYSTACK_SECRET_KEY=SECRET)
class PaymentHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pw-123456',
        )
        self.business = Business.objects.create(owner=self.user, name='Acme')
        self.provider = Provider.objects.create(code='paystack', name='Paystack')
        self.payment = Payment.objects.create(
            business=self.business, provider=self.provider,
            reference='pay_test_1', amount=Decimal('1000.00'),
        )

    def charge_success(self, amount_kobo=100000):
        body = json.dumps({
            'event': 'charge.success',
            'data': {'reference': 'pay_test_1', 'amount': amount_kobo, 'status': 'success'},
        }).encode()
        return self.client.post(
            reverse('webhooks:paystack'), data=body, content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=sign(body),
        )

    def test_webhook_settles_and_records_history(self):
        self.assertEqual(self.charge_success().status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESSFUL)
        sources = list(self.payment.events.values_list('source', flat=True))
        self.assertEqual(sources, ['webhook', 'webhook'])

    def test_duplicate_webhook_is_acknowledged_and_not_reprocessed(self):
        self.charge_success()
        self.charge_success()
        self.assertEqual(WebhookEvent.objects.count(), 1)
        # Only the first delivery is processed; the repeat records nothing.
        self.assertEqual(self.payment.events.count(), 2)

    def test_bad_signature_is_rejected_without_recording(self):
        body = b'{"event": "charge.success", "data": {"reference": "pay_test_1"}}'
        response = self.client.post(
            reverse('webhooks:paystack'), data=body, content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='bad',
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_amount_mismatch_is_recorded_but_not_settled(self):
        self.charge_success(amount_kobo=50000)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertTrue(self.payment.events.filter(message__contains='does not match').exists())

    def test_reconcile_settles_and_records_history(self):
        data = {'status': 'success', 'amount': 100000}
        self.assertTrue(settle_from_paystack_data(self.payment, data, PaymentEvent.Source.RECONCILE))
        self.assertEqual(self.payment.events.get().source, 'reconcile')

    def test_detail_page_shows_history_for_owner(self):
        self.charge_success()
        self.client.force_login(self.user)
        response = self.client.get(reverse('payments:detail', args=['pay_test_1']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paystack confirmed the payment')

    def test_detail_page_hidden_from_other_users(self):
        other = User.objects.create_user(username='other', password='pw-123456')
        self.client.force_login(other)
        response = self.client.get(reverse('payments:detail', args=['pay_test_1']))
        self.assertEqual(response.status_code, 404)

    def test_reconcile_command_records_unreachable(self):
        from django.core.management import call_command
        with mock.patch('apps.payments.management.commands.reconcile_payments.paystack_verify',
                        return_value=None):
            call_command('reconcile_payments', reference='pay_test_1', stdout=open('/dev/null', 'w'), stderr=open('/dev/null', 'w'))
        self.assertEqual(self.payment.events.get().source, 'reconcile')
