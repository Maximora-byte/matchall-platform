"""Read-only route/content contracts; no service lifespan or external OIDC calls."""
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import app

ROOT = Path(__file__).resolve().parents[2]
DOC_DIRS = [ROOT / 'services/hub/docs', ROOT / 'apps/docs-site/src/content/docs/docs', ROOT / 'apps/fuwari-site/src/content/docs']
sys.path.insert(0, str(ROOT / 'scripts'))
from sync_guides import GUIDE_SLUGS, parse_document, plan_sync


def body(path):
    return parse_document(path.read_text(encoding='utf-8'), slug=path.stem,
                          feedback_required=path.parent != DOC_DIRS[0]).body


class GuidePage(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.titles = 0
        self.forms = []
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == 'h1':
            self.titles += 1
        elif tag == 'form':
            self.forms.append(attributes)
        elif tag == 'a':
            self.links.append(attributes.get('href', ''))


class OnboardingGuideTests(unittest.TestCase):
    def test_changed_guides_have_identical_body_across_renderers(self):
        for slug in GUIDE_SLUGS:
            copies = [body(directory / f'{slug}.md') for directory in DOC_DIRS]
            self.assertEqual(copies[0], copies[1])
            self.assertEqual(copies[1], copies[2])

    def test_local_guide_links_exist_in_every_renderer(self):
        for directory in DOC_DIRS:
            for slug in GUIDE_SLUGS:
                for target in re.findall(r'\]\(/docs/([a-z-]+)/\)', body(directory / f'{slug}.md')):
                    self.assertTrue((directory / f'{target}.md').is_file(), target)

    def test_shared_guide_bodies_and_metadata_have_no_sync_drift(self):
        self.assertEqual(plan_sync(ROOT), {})

    def test_hub_renders_full_guides_with_one_title_and_native_feedback(self):
        with patch.object(app, 'DOCS_DIR', DOC_DIRS[0]):
            client = TestClient(app.app)
            self.addCleanup(client.close)
            for slug in GUIDE_SLUGS:
                with self.subTest(slug=slug):
                    response = client.get(f'/docs/{slug}')
                    self.assertEqual(response.status_code, 200)
                    page = GuidePage(response.text)
                    self.assertEqual(page.titles, 1)
                    self.assertEqual(page.forms, [{'method': 'post', 'action': f'/docs/{slug}/feedback'}])
                    self.assertIn('https://www.maximoraverse.org/contact/', page.links)

    def test_docs_home_cards_link_to_existing_guides(self):
        home = (ROOT / 'apps/docs-site/src/content/docs/index.mdx').read_text(encoding='utf-8')
        targets = re.findall(r'<LinkCard\b[^>]*href="(/docs/[a-z-]+/)"', home)
        self.assertEqual(set(targets), {f'/docs/{slug}/' for slug in (
            'account-security', 'drive-guide', 'network-guide', 'dns-guide', 'mirrors-user', 'mirrors-developer')})
        for target in targets:
            self.assertTrue((DOC_DIRS[1] / f'{target.split("/")[2]}.md').is_file(), target)

    def test_getting_started_explains_invites_permissions_and_partial_setup(self):
        content = body(DOC_DIRS[0] / 'getting-started.md')
        for expected in ('不是无需邀请的开放注册', '注册成功不代表所有服务已经开通', '刷新 Console 不会触发同步任务', '旧版 Console', '会话过期', '注册未完成'):
            self.assertIn(expected, content)
        for service in ('Drive', 'Network', 'DNS', 'Mirrors'):
            self.assertIn(f'### {service}', content)

    def test_dns_links_use_native_routes_and_existing_guide_anchors(self):
        content = body(DOC_DIRS[0] / 'dns-guide.md')
        self.assertIn('https://dns.maximoraverse.org/login', content)
        self.assertNotIn('https://dns.maximoraverse.org/account', content)
        native = (ROOT / 'services/dns/templates/guide.html').read_text()
        for anchor in re.findall(r'https://dns\.maximoraverse\.org/guide#([a-z-]+)', content):
            self.assertIn(f'id="{anchor}"', native)
        landing = (ROOT / 'apps/dns-site/src/pages/index.astro').read_text()
        self.assertIn('href="/login">进入账户', landing)
        self.assertNotIn('href="/account"', landing)

    def test_console_landing_has_direct_login_and_session_paths(self):
        content = (ROOT / 'apps/console-site/src/pages/index.astro').read_text()
        for link in ('href="/login"', 'href="/console"', 'https://auth.maximoraverse.org/register', 'https://docs.maximoraverse.org'):
            self.assertIn(link, content)
        self.assertIn('已有会话，直接进入', content)
        self.assertIn('需要有效邀请', content)

    def test_successful_login_returns_to_console_without_marketing_bounce(self):
        token = AsyncMock()
        token.status_code = 200
        # response.json() is synchronous on httpx responses
        from unittest.mock import Mock
        token.json = Mock(return_value={'access_token': 'synthetic-access'})
        userinfo = Mock(status_code=200)
        userinfo.json.return_value = {'sub': 'synthetic-sub', 'preferred_username': 'example', 'email': 'example@example.invalid'}
        http = AsyncMock()
        http.post.return_value = token
        http.get.return_value = userinfo
        client_factory = AsyncMock()
        client_factory.__aenter__.return_value = http
        with patch.object(app.httpx, 'AsyncClient', return_value=client_factory), patch.object(app, 'read_secret', return_value='synthetic-secret'):
            client = TestClient(app.app, base_url='https://console.example.invalid')
            client.cookies.set('console_oidc', app.serializer.dumps({'state': 'synthetic-state', 'verifier': 'synthetic-verifier'}))
            response = client.get('/auth/callback?code=synthetic-code&state=synthetic-state', follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/console')
        self.assertIn('console_session=', response.headers.get('set-cookie', ''))

    def test_interrupted_login_does_not_pretend_success(self):
        client = TestClient(app.app)
        with patch.object(app.httpx, 'AsyncClient') as http:
            for url in ('/auth/callback', '/auth/callback?code=synthetic-code&state=wrong'):
                self.assertEqual(client.get(url).status_code, 400)
            http.assert_not_called()


if __name__ == '__main__':
    unittest.main()
