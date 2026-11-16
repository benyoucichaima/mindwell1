from django.test import SimpleTestCase
from django.urls import reverse


class AccountEntryUrlTests(SimpleTestCase):
    def test_accounts_root_redirects_to_account_type_chooser(self):
        response = self.client.get('/accounts/')

        self.assertRedirects(
            response,
            reverse('accounts:choose_account_type'),
            fetch_redirect_response=False,
        )
