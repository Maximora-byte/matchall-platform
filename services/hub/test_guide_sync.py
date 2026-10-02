"""Synthetic guide trees only; no service imports, lifespans or network calls."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sync_guides.py"
spec = importlib.util.spec_from_file_location("sync_guides", SCRIPT)
sync_guides = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_guides)


class GuideSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for slug in sync_guides.GUIDE_SLUGS:
            self.write(sync_guides.CANONICAL_DIR, slug, self.source(slug))
            self.write(sync_guides.STARLIGHT_DIR, slug, self.starlight(slug))
            self.write(sync_guides.HUB_DIR, slug, self.hub(slug))

    def footer(self, slug, label="保留本地反馈"):
        return (f'---\n\n<form class="docs-feedback" method="post" action="/docs/{slug}/feedback">\n'
                f'  <strong>{label}</strong>\n'
                '  <button name="helpful" value="1">有帮助</button>\n'
                '  <button name="helpful" value="0">需要改进</button>\n'
                '</form>\n')

    def source(self, slug, body="## 统一指南\n\n这是更新的合成内容。"):
        return ('---\ntitle: 合成指南\ndescription: 合成说明，包含 Unicode。\n'
                'lastUpdated: 2026-10-02\n---\n\n' + body + '\n\n' + self.footer(slug, "源页面反馈"))

    def starlight(self, slug):
        return ('---\ntitle: 旧指南\ndescription: 旧说明\nlastUpdated: 2026-01-01\n'
                '# Native renderer metadata\nrenderer: Synthetic\n---\n\n旧内容。\n\n' + self.footer(slug))

    def hub(self, slug):
        return ('---\ntitle: 旧指南\nsummary: 旧说明\ncategory: 合成分类\nversion: 9.7\n'
                'updated: 2026-01-01\n---\n\n# 旧指南\n\n旧内容。\n')

    def path(self, directory, slug):
        return self.root / directory / f"{slug}.md"

    def write(self, directory, slug, content):
        path = self.path(directory, slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
        return path

    def snapshot(self):
        return {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*.md")}

    def test_default_check_reports_paths_and_never_writes_content(self):
        before = self.snapshot()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(sync_guides.main(["--root", str(self.root)]), 1)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(output.getvalue().splitlines()), 12)
        self.assertIn("DRIFT services/hub/docs/getting-started.md", output.getvalue())
        self.assertNotIn("合成内容", output.getvalue())

    def test_write_synchronizes_unicode_metadata_and_preserves_renderer_wrappers(self):
        slug = "getting-started"
        canonical = self.path(sync_guides.CANONICAL_DIR, slug).read_bytes()
        native_footer = self.footer(slug)
        changed = sync_guides.synchronize(self.root, write=True)
        self.assertEqual(len(changed), 12)
        starlight = self.path(sync_guides.STARLIGHT_DIR, slug).read_bytes().decode("utf-8")
        hub = self.path(sync_guides.HUB_DIR, slug).read_bytes().decode("utf-8")
        for content in (starlight, hub):
            self.assertIn("title: 合成指南", content)
            self.assertIn("2026-10-02", content)
            self.assertIn("这是更新的合成内容。", content)
        self.assertIn("description: 合成说明，包含 Unicode。", starlight)
        self.assertIn("# Native renderer metadata\nrenderer: Synthetic\n", starlight)
        self.assertTrue(starlight.endswith(native_footer))
        self.assertNotIn("源页面反馈", starlight)
        self.assertIn("summary: 合成说明，包含 Unicode。", hub)
        self.assertIn("category: 合成分类\nversion: 9.7\n", hub)
        self.assertNotIn("<form", hub)
        self.assertNotIn("# 旧指南", hub)
        self.assertEqual(self.path(sync_guides.CANONICAL_DIR, slug).read_bytes(), canonical)

    def test_horizontal_rules_and_fenced_frontmatter_and_forms_stay_in_body(self):
        slug = "network-guide"
        body = ('正文。\n\n---\n\n```yaml\n---\ntitle: code example\n---\n```\n\n'
                '~~~html\n<form action="/wrong/feedback">示例</form>\n~~~\n\n## 规则后的正文')
        self.write(sync_guides.CANONICAL_DIR, slug, self.source(slug, body))
        sync_guides.synchronize(self.root, write=True)
        for directory, feedback in ((sync_guides.STARLIGHT_DIR, True), (sync_guides.HUB_DIR, False)):
            content = self.path(directory, slug).read_bytes().decode("utf-8")
            document = sync_guides.parse_document(content, slug=slug, feedback_required=feedback)
            self.assertEqual(document.body, body)

    def test_missing_last_target_rejects_entire_write_before_any_mutation(self):
        self.path(sync_guides.HUB_DIR, "mirrors-developer").unlink()
        before = self.snapshot()
        with self.assertRaisesRegex(sync_guides.GuideSyncError, "missing managed file"):
            sync_guides.synchronize(self.root, write=True)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_target_feedback_action_prevents_partial_write(self):
        path = self.path(sync_guides.STARLIGHT_DIR, "mirrors-developer")
        path.write_bytes(path.read_bytes().replace(b"/docs/mirrors-developer/feedback", b"/docs/wrong-slug/feedback"))
        before = self.snapshot()
        with self.assertRaisesRegex(sync_guides.GuideSyncError, "feedback form action"):
            sync_guides.synchronize(self.root, write=True)
        self.assertEqual(self.snapshot(), before)

    def test_unsupported_or_duplicate_frontmatter_fails_clearly_without_writes(self):
        slug = "dns-guide"
        original = self.source(slug)
        for invalid in ('title: |\n  multiline', 'title: [structured, value]', 'title: "quoted value"',
                        'title: 合成指南\ntitle: duplicate'):
            with self.subTest(invalid=invalid.splitlines()[0]):
                self.write(sync_guides.CANONICAL_DIR, slug, original.replace("title: 合成指南", invalid))
                before = self.snapshot()
                error = io.StringIO()
                with contextlib.redirect_stderr(error):
                    self.assertEqual(sync_guides.main(["--write", "--root", str(self.root)]), 2)
                self.assertIn("frontmatter", error.getvalue())
                self.assertIn("dns-guide.md", error.getvalue())
                self.assertEqual(self.snapshot(), before)

    def test_write_is_idempotent_and_check_exits_successfully_after_sync(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync_guides.main(["--write", "--root", str(self.root)]), 0)
        before = self.snapshot()
        self.assertEqual(sync_guides.synchronize(self.root, write=True), ())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(sync_guides.main(["--check", "--root", str(self.root)]), 0)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(self.snapshot(), before)

    def test_unmanaged_documents_are_never_read_or_changed(self):
        unmanaged = []
        for directory in (sync_guides.CANONICAL_DIR, sync_guides.STARLIGHT_DIR, sync_guides.HUB_DIR):
            unmanaged.append(self.write(directory, "custom-guide", "Not managed and intentionally invalid.\n"))
        before = {path: path.read_bytes() for path in unmanaged}
        sync_guides.synchronize(self.root, write=True)
        self.assertEqual({path: path.read_bytes() for path in unmanaged}, before)

    def test_crlf_renderer_preserves_its_exact_feedback_html(self):
        slug = "drive-guide"
        native = self.starlight(slug).replace("\n", "\r\n")
        self.write(sync_guides.STARLIGHT_DIR, slug, native)
        footer = self.footer(slug).replace("\n", "\r\n").encode("utf-8")
        sync_guides.synchronize(self.root, write=True)
        result = self.path(sync_guides.STARLIGHT_DIR, slug).read_bytes()
        self.assertTrue(result.endswith(footer))
        self.assertNotIn(b"\n", result.replace(b"\r\n", b""))
        self.assertEqual(sync_guides.synchronize(self.root), ())

    def test_feedback_must_be_complete_trailing_and_outside_code_fences(self):
        slug = "mirrors-user"
        original = self.source(slug)
        invalid_sources = [original.replace("</form>", ""), original + "Unexpected body after the form.\n",
                           original.replace('<button name="helpful" value="0">需要改进</button>', ""),
                           original.replace("## 统一指南", "```\n## 统一指南")]
        for invalid in invalid_sources:
            with self.subTest(length=len(invalid)):
                self.write(sync_guides.CANONICAL_DIR, slug, invalid)
                before = self.snapshot()
                with self.assertRaises(sync_guides.GuideSyncError):
                    sync_guides.synchronize(self.root, write=True)
                self.assertEqual(self.snapshot(), before)

    def test_only_exact_leading_title_heading_is_removed(self):
        slug = "mirrors-developer"
        self.write(sync_guides.CANONICAL_DIR, slug, self.source(slug, "# 合成指南\n\n正文。\n\n# 不同标题"))
        sync_guides.synchronize(self.root, write=True)
        document = sync_guides.parse_document(self.path(sync_guides.HUB_DIR, slug).read_bytes().decode("utf-8"),
            slug=slug, feedback_required=False)
        self.assertEqual(document.body, "正文。\n\n# 不同标题")
        with self.assertRaisesRegex(sync_guides.GuideSyncError, "slug is not managed"):
            sync_guides.parse_document(self.source(slug), slug="../escape", feedback_required=True)

    def test_invalid_metadata_date_rejects_all_changes(self):
        slug = "mirrors-developer"
        self.write(sync_guides.CANONICAL_DIR, slug, self.source(slug).replace("2026-10-02", "2026-02-30"))
        before = self.snapshot()
        with self.assertRaisesRegex(sync_guides.GuideSyncError, "invalid lastUpdated date"):
            sync_guides.synchronize(self.root, write=True)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
