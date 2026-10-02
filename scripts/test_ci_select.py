"""Regression tests for CI routing, including real Git PR diffs."""

import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ci_select import (
    ASTRO_APPS, GO_MODULES, PYTHON_SERVICES, VENDOR_GO_MODULES,
    checks_for_event, select_checks, write_outputs,
)


class SelectionTests(unittest.TestCase):
    def test_each_service_dependency_change_only_runs_that_service(self):
        for service in PYTHON_SERVICES:
            with self.subTest(service=service):
                checks = select_checks([f"services/{service}/requirements.txt"])
                self.assertEqual(checks["python_services"], [service])
                self.assertEqual(checks["astro_apps"], [])
                self.assertEqual(checks["go_modules"], [])

    def test_each_astro_dependency_change_only_runs_that_app(self):
        for app in ASTRO_APPS:
            with self.subTest(app=app):
                checks = select_checks([f"apps/{app}/package-lock.json"])
                self.assertEqual(checks["astro_apps"], [app])
                self.assertEqual(checks["python_services"], [])
                self.assertFalse(checks["fuwari"])

    def test_go_module_is_isolated_except_shared_library(self):
        for module in GO_MODULES:
            if module.endswith("/libs"):
                continue
            with self.subTest(module=module):
                self.assertEqual(select_checks([module + "/go.sum"])["go_modules"], [module])

    def test_shared_go_library_runs_its_consumers(self):
        self.assertEqual(
            select_checks(["vendor/moddns-matchall/libs/go.mod"])["go_modules"],
            list(VENDOR_GO_MODULES),
        )

    def test_shared_vendor_fixture_runs_vendor_go_checks(self):
        self.assertEqual(
            select_checks(["vendor/moddns-matchall/fixtures/test.json"])["go_modules"],
            list(VENDOR_GO_MODULES),
        )

    def test_hub_cross_directory_document_fixtures(self):
        for path in (
            "apps/docs-site/src/content/docs/docs/getting-started.md",
            "apps/fuwari-site/src/content/docs/dns-guide.md",
            "apps/dns-site/src/pages/index.astro",
            "apps/console-site/src/pages/index.astro",
            "services/dns/templates/guide.html",
        ):
            with self.subTest(path=path):
                self.assertIn("hub", select_checks([path])["python_services"])
        self.assertEqual(
            select_checks(["services/dns/templates/guide.html"])["python_services"],
            ["hub", "dns"],
        )

    def test_preview_server_runs_both_ui_apps(self):
        self.assertEqual(
            select_checks(["scripts/preview-static.mjs"])["astro_apps"],
            ["main-site", "status-site"],
        )

    def test_fuwari_lockfile_does_not_trigger_npm_apps(self):
        checks = select_checks(["apps/fuwari-site/pnpm-lock.yaml"])
        self.assertTrue(checks["fuwari"])
        self.assertEqual(checks["astro_apps"], [])

    def test_wordpress_and_multiple_modules(self):
        checks = select_checks([
            "wordpress/plugin.php", "apps/status-site/package.json",
            "services/mirrors/app.py", "apps/status-site/package-lock.json",
        ])
        self.assertTrue(checks["php"])
        self.assertEqual(checks["astro_apps"], ["status-site"])
        self.assertEqual(checks["python_services"], ["mirrors"])

    def test_metadata_only_and_empty_diff_select_no_builds(self):
        empty = select_checks([])
        self.assertEqual(select_checks(["README.md", ".github/dependabot.yml"]), empty)
        self.assertEqual(select_checks(["docs/ARCHITECTURE.md"]), empty)
        self.assertFalse(empty["php"])
        self.assertEqual(empty["python_services"], [])

    def test_vendor_frontend_changes_select_only_frontend(self):
        for path in ("package.json", "package-lock.json", "src/App.tsx", "vite.config.ts", "env/.env.test"):
            checks = select_checks(["vendor/moddns-matchall/app/" + path])
            self.assertTrue(checks["vendor_frontend"])
            self.assertEqual(checks["python_services"], [])
            self.assertEqual(checks["astro_apps"], [])
            self.assertEqual(checks["go_modules"], [])

    def test_shared_vendor_configuration_selects_frontend(self):
        self.assertTrue(select_checks(["vendor/moddns-matchall/.gitignore"])["vendor_frontend"])
        self.assertTrue(select_checks(["vendor/moddns-matchall/fixtures/test.json"])["vendor_frontend"])
        self.assertFalse(select_checks(["vendor/moddns-matchall/proxy/go.mod"])["vendor_frontend"])

    def test_unrelated_pr_skips_frontend_and_full_runs_include_it(self):
        self.assertFalse(select_checks(["services/dns/app.py"])["vendor_frontend"])
        self.assertTrue(select_checks([], full=True)["vendor_frontend"])

    def test_workflow_selector_unknown_config_and_new_modules_run_all(self):
        for path in (
            ".github/workflows/ci.yml", "scripts/ci_select.py",
            "scripts/test_ci_select.py", ".nvmrc", "package.json",
            "apps/new-app/package.json", "services/new-service/app.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(select_checks([path]), select_checks([], full=True))

    def test_directory_prefixes_do_not_match_other_services(self):
        checks = select_checks(["services/dns-transports/main.go"])
        self.assertEqual(checks["python_services"], [])
        self.assertEqual(checks["go_modules"], ["services/dns-transports"])

    def test_non_pr_events_always_run_all(self):
        for event in ("push", "workflow_dispatch"):
            self.assertEqual(checks_for_event(event, {}), select_checks([], full=True))

    def test_git_failure_falls_back_to_all_checks(self):
        event = {"pull_request": {"base": {"sha": "missing"}, "head": {"sha": "missing"}}}
        with patch("ci_select.subprocess.check_output", side_effect=subprocess.CalledProcessError(128, "git")):
            self.assertEqual(checks_for_event("pull_request", event), select_checks([], full=True))
        self.assertEqual(checks_for_event("pull_request", {}), select_checks([], full=True))

    def test_outputs_use_json_and_explicit_empty_matrix_flags(self):
        output = io.StringIO()
        write_outputs(select_checks([]), output)
        values = dict(line.split("=", 1) for line in output.getvalue().splitlines())
        self.assertEqual(json.loads(values["astro_apps"]), [])
        self.assertEqual(values["has_astro_apps"], "false")
        self.assertEqual(values["fuwari"], "false")
        self.assertEqual(values["vendor_frontend"], "false")
        output = io.StringIO()
        write_outputs(select_checks(["apps/status-site/package.json"]), output)
        self.assertIn("has_astro_apps=true", output.getvalue())


class GitDiffTests(unittest.TestCase):
    def test_runtime_ignore_rules_keep_log_ui_source_trackable(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for relative in (".gitignore", "vendor/moddns-matchall/.gitignore", "vendor/moddns-matchall/app/.gitignore"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((repository / relative).read_text())
            paths = [
                "vendor/moddns-matchall/app/src/pages/logs/Logs.tsx",
                "vendor/moddns-matchall/app/src/pages/logs/runtime.log",
                "logs/runtime.log", "services/dns/backups/private.sqlite3",
            ]
            result = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "--no-index", "--stdin"],
                input="\n".join(paths) + "\n", text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), paths[1:])

    def test_merge_base_ignores_new_base_changes_but_keeps_rename_and_delete_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL).decode().strip()

            def write(path, text):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)

            git("init", "-b", "main")
            git("config", "user.name", "CI Fixture")
            git("config", "user.email", "ci@example.invalid")
            write("apps/status-site/src/rename me.txt", "rename\n")
            write("services/dns/delete.txt", "delete\n")
            git("add", ".")
            git("commit", "-m", "base")
            git("checkout", "-b", "pr")
            write("apps/main-site/src/renamed\nfile.txt", "rename\n")
            (root / "apps/status-site/src/rename me.txt").unlink()
            (root / "services/dns/delete.txt").unlink()
            git("add", "-A")
            git("commit", "-m", "rename and delete")
            head = git("rev-parse", "HEAD")
            git("checkout", "main")
            write("services/mirrors/main-only.txt", "main-only\n")
            git("add", ".")
            git("commit", "-m", "advance base")
            base = git("rev-parse", "HEAD")
            event = {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                checks = checks_for_event("pull_request", event)
            finally:
                os.chdir(old_cwd)
            self.assertEqual(checks["astro_apps"], ["main-site", "status-site"])
            self.assertEqual(checks["python_services"], ["dns"])
            self.assertEqual(checks["go_modules"], [])


if __name__ == "__main__":
    unittest.main()
