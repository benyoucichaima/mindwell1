from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from accounts.models import Notification


class PageLinksParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get('id'):
            self.ids.add(attributes['id'])
        if tag == 'a' and 'href' in attributes:
            self.hrefs.append(attributes['href'])


class InternalPageLinkTests(TestCase):
    page_names = (
        'home',
        'about',
        'ethics',
        'faq',
        'psychologists',
        'specialties',
        'comment_ca_marche',
        'blog',
        'aide',
        'contact',
        'confidentialite',
        'cgv',
        'mentions_legales',
        'carriere',
    )

    def test_internal_links_resolve_in_each_language(self):
        for language in ('fr', 'ar', 'en'):
            with self.subTest(language=language), translation.override(language):
                login_path = reverse('accounts:login')
                for page_name in self.page_names:
                    page_response = self.client.get(reverse(page_name))
                    self.assertEqual(
                        page_response.status_code,
                        200,
                        f'{page_name} did not render for {language}',
                    )
                    parser = PageLinksParser()
                    parser.feed(page_response.content.decode(page_response.charset))
                    page_url = page_response.wsgi_request.build_absolute_uri()

                    for href in parser.hrefs:
                        with self.subTest(page=page_name, href=href):
                            self.assertTrue(href.strip(), 'Anchor has an empty href')
                            target = urljoin(page_url, href)
                            target_parts = urlsplit(target)
                            if target_parts.netloc != urlsplit(page_url).netloc:
                                continue
                            if target_parts.fragment and not target_parts.path:
                                self.assertIn(
                                    target_parts.fragment,
                                    parser.ids,
                                    f'In-page target #{target_parts.fragment} is missing',
                                )
                                continue

                            path = target_parts.path
                            if target_parts.query:
                                path = f'{path}?{target_parts.query}'
                            response = self.client.get(path)
                            self.assertIn(
                                response.status_code,
                                (200, 302),
                                f'{href} returned {response.status_code}',
                            )
                            if response.status_code == 302:
                                location = urlsplit(response['Location'])
                                self.assertEqual(
                                    location.path,
                                    login_path,
                                    f'{href} redirected somewhere other than login',
                                )
                                self.assertIn(
                                    'next',
                                    parse_qs(location.query),
                                    f'{href} login redirect omitted ?next=',
                                )

    def test_notifications_page_and_mark_all_read(self):
        user = get_user_model().objects.create_user(
            username='notifications-reader',
            email='notifications@example.test',
            password='test-password-123',
            user_type='patient',
        )
        notification = Notification.objects.create(
            user=user,
            message='A consultation has been confirmed.',
        )
        notifications_url = reverse('accounts:notifications')
        response = self.client.get(notifications_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response['Location'])
        self.assertIn('next=', response['Location'])

        self.client.force_login(user)
        self.assertEqual(self.client.get(notifications_url).status_code, 200)
        response = self.client.post(reverse('accounts:mark_notifications_read'))
        self.assertRedirects(response, reverse('accounts:patient_dashboard'))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_flow_completes(self):
        user = get_user_model().objects.create_user(
            username='password-reset-reader',
            email='reset@example.test',
            password='old-password-123',
        )
        response = self.client.post(
            reverse('accounts:password_reset'),
            {'email': user.email},
        )
        self.assertRedirects(response, reverse('accounts:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)

        reset_url = next(
            part for part in mail.outbox[0].body.split()
            if '/accounts/password-reset/' in part
        )
        parsed_url = urlsplit(reset_url)
        response = self.client.get(parsed_url.path, follow=True)
        self.assertEqual(response.status_code, 200)
        reset_path = response.wsgi_request.path
        response = self.client.post(reset_path, {
            'new_password1': 'new-password-456!',
            'new_password2': 'new-password-456!',
        })
        self.assertRedirects(response, reverse('accounts:password_reset_complete'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('new-password-456!'))
