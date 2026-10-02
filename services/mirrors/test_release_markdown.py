import os
import tempfile
import unittest
from html.parser import HTMLParser

_tmp = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _tmp.name

from app import download_media_type, render_release_markdown, templates


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = {"attrs": dict(attrs), "text": ""}
            self.links.append(self.current)

    def handle_endtag(self, tag):
        if tag == "a":
            self.current = None

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data


def parse_links(rendered):
    parser = LinkParser()
    parser.feed(str(rendered))
    parser.close()
    return parser.links


class ReleaseMarkdownTests(unittest.TestCase):
    def assert_release_link(self, uri, expected_href):
        for syntax, source in (
            ("markdown", f"[版本说明]({uri})"),
            ("html", f'<a href="{uri}">版本说明</a>'),
        ):
            with self.subTest(syntax=syntax):
                links = parse_links(render_release_markdown(source))
                self.assertEqual(len(links), 1)
                self.assertEqual(links[0]["text"], "版本说明")
                if expected_href is None:
                    self.assertNotIn("href", links[0]["attrs"])
                else:
                    self.assertEqual(links[0]["attrs"].get("href"), expected_href)
                    self.assertIn("nofollow", links[0]["attrs"].get("rel", "").split())

    def test_download_media_types_for_release_assets(self):
        self.assertEqual(download_media_type("v2rayNG.apk"), "application/vnd.android.package-archive")
        self.assertEqual(download_media_type("v2rayNG.apk.sig"), "application/pgp-signature")
        self.assertEqual(download_media_type("v2rayN.deb"), "application/vnd.debian.binary-package")
        self.assertEqual(download_media_type("v2rayN.rpm"), "application/x-rpm")
        self.assertEqual(download_media_type("v2rayN.dmg"), "application/x-apple-diskimage")
        self.assertEqual(download_media_type("unknown.bin"), "application/octet-stream")

    def test_renders_markdown_and_normalizes_orphan_summary(self):
        rendered = str(render_release_markdown(
            "<summary>版本介绍\n\n- 摘要项目</summary>\n\n## 更新一览\n\n- 修复问题"
        ))
        self.assertIn("<blockquote>", rendered)
        self.assertIn("<strong>版本摘要</strong>", rendered)
        self.assertIn("<h2>更新一览</h2>", rendered)
        self.assertIn("<li>修复问题</li>", rendered)
        self.assertNotIn("<summary>", rendered)

    def test_sanitizes_active_content_and_unsafe_links(self):
        rendered = str(render_release_markdown(
            "[安全链接](https://example.com) "
            "[危险链接](javascript:alert(1)) "
            "<script>alert(1)</script><img src=x onerror=alert(1)>"
        ))
        self.assertIn('href="https://example.com"', rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertNotIn("<script", rendered)
        self.assertNotIn("<img", rendered)
        self.assertNotIn("onerror", rendered)

    def test_linkifies_bare_https_url(self):
        rendered = str(render_release_markdown("下载：https://get.dot.net/10"))
        self.assertIn('href="https://get.dot.net/10"', rendered)
        self.assertIn('rel="nofollow"', rendered)

    def test_strips_disallowed_schemes_with_invisible_unicode(self):
        # GHSA-8rfp-98v4-mmr6: enforce the protocol allowlist after Unicode
        # normalization, not a claim that modern browsers execute invalid schemes.
        # https://github.com/mozilla/bleach/security/advisories/GHSA-8rfp-98v4-mmr6
        characters = (
            ("zero-width-space", "\u200b"),
            ("zero-width-non-joiner", "\u200c"),
            ("zero-width-joiner", "\u200d"),
            ("bom", "\ufeff"),
            ("soft-hyphen", "\u00ad"),
            ("word-joiner", "\u2060"),
            ("left-to-right-mark", "\u200e"),
            ("right-to-left-override", "\u202e"),
            ("left-to-right-isolate", "\u2066"),
            ("variation-selector", "\ufe0f"),
        )
        for scheme, payload in (
            ("JaVaScRiPt", "alert(1)"),
            ("VbScRiPt", "msgbox(1)"),
            ("DaTa", "text/plain,blocked"),
        ):
            for name, character in characters:
                for position in (0, 2, len(scheme)):
                    uri = scheme[:position] + character + scheme[position:] + ":" + payload
                    with self.subTest(scheme=scheme, character=name, position=position):
                        self.assert_release_link(uri, None)

    def test_strips_entity_encoded_and_control_obfuscated_schemes(self):
        for uri in (
            "javascript\u200b:alert(1)",  # Upstream advisory's original example.
            "\ufeff javascript:alert(1)",
            "javascript\u00ad:alert(1)",
            "java&#x200B;script:alert(1)",
            "&#65279;JaVaScRiPt&#58;alert(1)",
            "vb&#8238;script&#x3A;msgbox(1)",
            "da&#x2060;ta:text/plain,blocked",
            "java\tscript:alert(1)",
            "vb\nscript:msgbox(1)",
            "da\rta:text/plain,blocked",
            "java&#9;script&#58;alert(1)",
            "\u00a0javascript:alert(1)",
        ):
            with self.subTest(uri=ascii(uri)):
                self.assert_release_link(uri, None)

    def test_preserves_allowed_urls_and_unicode_outside_schemes(self):
        for uri in (
            "http://example.invalid/releases",
            "HTTPS://example.invalid/releases",
            "https://例え.invalid/发行\u200b说明?名称=新版&x=1#摘要",
            "https://example.invalid/\ufeffnotes",
            "/releases/新版",
            "../releases/更新.md",
            "//example.invalid/版本",
            "?version=新版",
            "#更新",
            # Percent escapes are not decoded into a URL scheme by the browser.
            "java%E2%80%8Bscript:alert(1)",
            "javascript%3Aalert(1)",
        ):
            with self.subTest(uri=ascii(uri)):
                self.assert_release_link(uri, uri)

    def test_named_colon_entity_stays_escaped(self):
        # Bleach escapes this named entity, so the parsed href contains literal
        # "&colon;", not a colon that could introduce a javascript: scheme.
        self.assert_release_link("java&#9;script&colon;alert(1)", "java\tscript&colon;alert(1)")

    def test_project_template_sanitizes_release_links(self):
        notes = (
            "## 新版公告\n\n"
            "[blocked-js](java\u200bscript:alert(1))\n\n"
            '<a href="\ufeffvbscript:msgbox(1)">blocked-vbs</a>\n\n'
            '<a href="da&#x2060;ta:text/plain,blocked">blocked-data</a>\n\n'
            "[safe-release](https://example.invalid/更新)"
        )
        rendered = templates.get_template("project.html").render(
            request={"url": {"path": "/project/unicode-fixture"}},
            user=None,
            is_admin=False,
            project={
                "name": "Unicode fixture", "slug": "unicode-fixture",
                "access_mode": "free", "allowed": True,
                "releases": [{"version": "1.0", "channel": "stable",
                              "published_at": 1_700_000_000, "notes": notes,
                              "artifacts": []}],
            },
        )
        self.assertIn('<div class="release-notes"><h2>新版公告</h2>', rendered)
        expected = {"blocked-js": None, "blocked-vbs": None, "blocked-data": None,
                    "safe-release": "https://example.invalid/更新"}
        links = [link for link in parse_links(rendered) if link["text"] in expected]
        self.assertEqual([link["text"] for link in links], list(expected))
        for link in links:
            with self.subTest(label=link["text"]):
                if expected[link["text"]] is None:
                    self.assertNotIn("href", link["attrs"])
                else:
                    self.assertEqual(link["attrs"].get("href"), expected[link["text"]])
                    self.assertIn("nofollow", link["attrs"].get("rel", "").split())


if __name__ == "__main__":
    unittest.main()
