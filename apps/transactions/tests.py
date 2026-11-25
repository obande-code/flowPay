from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.businesses.models import Business
from apps.payments.models import Payment
from apps.providers.models import Provider


class TransactionListTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pw-123456')
        self.business = Business.objects.create(owner=self.user, name='Acme', email='a@example.com')
        self.provider = Provider.objects.create(code='paystack', name='Paystack')
        for i in range(25):
            Payment.objects.create(
                business=self.business, provider=self.provider,
                reference=f'pay_ref_{i:03d}', amount=Decimal('100.00'),
                status=Payment.Status.SUCCESSFUL if i % 2 else Payment.Status.PENDING,
            )
        self.client.force_login(self.user)
        self.url = reverse('transactions:list')

    def test_paginates_twenty_per_page(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['page'].object_list), 20)
        self.assertEqual(response.context['page'].paginator.num_pages, 2)
        page_two = self.client.get(self.url, {'page': 2})
        self.assertEqual(len(page_two.context['page'].object_list), 5)

    def test_status_filter(self):
        response = self.client.get(self.url, {'status': 'successful'})
        self.assertEqual(response.context['page'].paginator.count, 12)

    def test_search_by_reference(self):
        response = self.client.get(self.url, {'q': 'ref_007'})
        self.assertEqual(response.context['page'].paginator.count, 1)

    def test_search_by_business_name(self):
        response = self.client.get(self.url, {'q': 'acme'})
        self.assertEqual(response.context['page'].paginator.count, 25)

    def test_invalid_status_is_ignored(self):
        response = self.client.get(self.url, {'status': 'bogus'})
        self.assertEqual(response.context['page'].paginator.count, 25)

    def test_only_own_transactions_are_listed(self):
        other = User.objects.create_user(username='other', password='pw-123456')
        other_business = Business.objects.create(owner=other, name='Other', email='o@example.com')
        Payment.objects.create(business=other_business, provider=self.provider,
                               reference='pay_foreign', amount=Decimal('5.00'))
        response = self.client.get(self.url, {'q': 'foreign'})
        self.assertEqual(response.context['page'].paginator.count, 0)
