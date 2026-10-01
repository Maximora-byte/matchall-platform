import unittest

from app import download_media_type, render_release_markdown


class ReleaseMarkdownTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
