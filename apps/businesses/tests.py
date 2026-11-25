from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.api_keys.models import ApiKey
from apps.api_keys.services import hash_key

from .models import Business


class MerchantSettingsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pw-123456')
        self.business = Business.objects.create(owner=self.owner, name='Acme', email='a@example.com')
        self.client.force_login(self.owner)

    def test_settings_page_loads_for_owner(self):
        response = self.client.get(reverse('businesses:settings', args=[self.business.pk]))
        self.assertEqual(response.status_code, 200)

    def test_other_users_cannot_see_settings(self):
        other = User.objects.create_user(username='other', password='pw-123456')
        self.client.force_login(other)
        response = self.client.get(reverse('businesses:settings', args=[self.business.pk]))
        self.assertEqual(response.status_code, 404)

    def test_webhook_url_must_be_https(self):
        response = self.client.post(reverse('businesses:settings', args=[self.business.pk]), {
            'name': 'Acme', 'email': 'a@example.com', 'business_type': 'individual',
            'registration_number': '', 'webhook_url': 'http://example.com/hook',
        })
        self.assertEqual(response.status_code, 200)
        self.business.refresh_from_db()
        self.assertEqual(self.business.webhook_url, '')

    def test_valid_profile_and_https_webhook_are_saved(self):
        response = self.client.post(reverse('businesses:settings', args=[self.business.pk]), {
            'name': 'Acme Ltd', 'email': 'a@example.com', 'business_type': 'company',
            'registration_number': 'RC123', 'webhook_url': 'https://example.com/hook',
        })
        self.assertEqual(response.status_code, 302)
        self.business.refresh_from_db()
        self.assertEqual(self.business.name, 'Acme Ltd')
        self.assertEqual(self.business.webhook_url, 'https://example.com/hook')

    def test_generate_key_stores_only_hash_and_shows_key_once(self):
        self.client.post(reverse('businesses:create_key', args=[self.business.pk]), {'name': 'Web'})
        key = ApiKey.objects.get()
        self.assertTrue(key.is_active)
        page = self.client.get(reverse('businesses:settings', args=[self.business.pk]))
        raw = page.context['new_key']
        self.assertTrue(raw.startswith('fp_live_'))
        self.assertEqual(key.key_hash, hash_key(raw))
        self.assertNotIn(raw, key.key_hash)
        # The raw key is not kept after it has been displayed once.
        again = self.client.get(reverse('businesses:settings', args=[self.business.pk]))
        self.assertIsNone(again.context['new_key'])

    def test_revoke_key_deactivates_it(self):
        self.client.post(reverse('businesses:create_key', args=[self.business.pk]), {'name': 'Web'})
        key = ApiKey.objects.get()
        self.client.post(reverse('businesses:revoke_key', args=[self.business.pk, key.pk]))
        key.refresh_from_db()
        self.assertFalse(key.is_active)

    def test_cannot_revoke_another_businesses_key(self):
        other_owner = User.objects.create_user(username='o2', password='pw-123456')
        other_business = Business.objects.create(owner=other_owner, name='Other', email='o@example.com')
        key = ApiKey.objects.create(business=other_business, name='x', key_prefix='fp_live_abc', key_hash='h1')
        self.client.post(reverse('businesses:revoke_key', args=[self.business.pk, key.pk]))
        key.refresh_from_db()
        self.assertTrue(key.is_active)
