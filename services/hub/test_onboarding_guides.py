"""Read-only route/content contracts; no service lifespan or external OIDC calls."""
import re
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import app

ROOT = Path(__file__).resolve().parents[2]
DOC_DIRS = [ROOT / 'services/hub/docs', ROOT / 'apps/docs-site/src/content/docs/docs', ROOT / 'apps/fuwari-site/src/content/docs']


def body(path):
    text = path.read_text().split('\n---\n', 1)[1]
    return text.split('\n---\n')[0].strip()


class OnboardingGuideTests(unittest.TestCase):
    def test_changed_guides_have_identical_body_across_renderers(self):
        for slug in ('getting-started', 'dns-guide'):
            copies = [body(directory / f'{slug}.md') for directory in DOC_DIRS]
            self.assertEqual(copies[0], copies[1])
            self.assertEqual(copies[1], copies[2])

    def test_local_guide_links_exist_in_every_renderer(self):
        for directory in DOC_DIRS:
            for slug in ('getting-started', 'dns-guide'):
                for target in re.findall(r'\]\(/docs/([a-z-]+)/\)', body(directory / f'{slug}.md')):
                    self.assertTrue((directory / f'{target}.md').is_file(), target)

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
