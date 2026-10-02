"""Import-time settings checks in isolated processes, without application startup tasks."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


HUB_DIR = Path(__file__).resolve().parent
SETTING = "SNAPSHOT_STALE_AFTER_SECONDS"
ERROR = f"{SETTING} must be a positive integer (>= 1)."
IMPORT_APP = textwrap.dedent("""\
    import os
    from pathlib import Path
    from unittest.mock import patch

    def synthetic_secret(path, *args, **kwargs):
        assert path == Path(os.environ["SESSION_SECRET_FILE"]), "Unexpected file read"
        return "synthetic-session-secret-for-config-tests"

    # Do not read secrets, snapshots, or databases, connect to services, or run
    # lifespan/background workers. An import only needs the synthetic session key.
    with patch("sqlite3.connect", side_effect=AssertionError("Unexpected database access")), \\
         patch("socket.socket.connect", side_effect=AssertionError("Unexpected network access")):
        # Load dependency metadata before denying application-level file reads.
        import fastapi
        import monitoring
        with patch.object(Path, "read_text", autospec=True, side_effect=synthetic_secret) as read:
            try:
                import app
            except ValueError:
                read.assert_not_called()
                raise
            read.assert_called_once_with(Path(os.environ["SESSION_SECRET_FILE"]))
            print(app.SNAPSHOT_STALE_AFTER_SECONDS)
""")


class SnapshotConfigurationTests(unittest.TestCase):
    def startup(self, value=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Start from an allowlist, never inherit production environment values.
            env = {
                "DATA_DIR": str(root / "data"),
                "DOCS_DIR": str(root / "docs"),
                "SESSION_SECRET_FILE": str(root / "synthetic-session-secret"),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            if sys.platform == "win32":
                env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
            if value is not None:
                env[SETTING] = value
            result = subprocess.run(
                [sys.executable, "-c", IMPORT_APP], cwd=HUB_DIR, env=env,
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(list(root.iterdir()), [], "Import wrote runtime data")
            return result

    def assert_valid(self, raw, expected):
        result = self.startup(raw)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(expected))
        self.assertEqual(result.stderr, "")

    def assert_invalid(self, raw):
        result = self.startup(raw)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn(f"ValueError: {ERROR}", result.stderr)
        self.assertNotIn("invalid literal", result.stderr)
        self.assertNotIn("During handling", result.stderr)
        return result

    def test_missing_uses_900(self):
        self.assert_valid(None, 900)

    def test_positive_boundary_and_existing_values_are_preserved(self):
        for raw, expected in (("1", 1), ("900", 900), ("1800", 1800),
                              ("  +0900  ", 900), ("1_800", 1800),
                              (str(2**63), 2**63)):
            with self.subTest(raw=raw):
                self.assert_valid(raw, expected)

    def test_zero_and_negative_values_fail_instead_of_clamping(self):
        for raw in ("0", "-0", "-1", "-900"):
            with self.subTest(raw=raw):
                self.assert_invalid(raw)

    def test_empty_and_non_integer_values_fail(self):
        for raw in ("", " ", "1.5", "900.0", "1e3", "nan", "true"):
            with self.subTest(raw=raw):
                self.assert_invalid(raw)

    def test_invalid_setting_is_not_leaked_in_startup_error(self):
        raw = "synthetic-sensitive-value\nsecond-line"
        result = self.assert_invalid(raw)
        self.assertNotIn("synthetic-sensitive-value", result.stderr)
        self.assertNotIn("second-line", result.stderr)


if __name__ == "__main__":
    unittest.main()
