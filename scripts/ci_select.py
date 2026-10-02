"""Select existing CI checks from a PR diff using only the standard library."""

import argparse
import json
import os
import subprocess
from pathlib import Path


PYTHON_SERVICES = ("hub", "dns", "mirrors")
ASTRO_APPS = (
    "main-site", "cv-site", "status-site", "console-site", "entry-sites",
    "dns-site", "docs-site", "mirrors-site", "investment-site",
)
GO_MODULES = (
    "services/dns-transports",
    "vendor/moddns-matchall/api",
    "vendor/moddns-matchall/blocklists",
    "vendor/moddns-matchall/dnscheck",
    "vendor/moddns-matchall/libs",
    "vendor/moddns-matchall/proxy",
)
VENDOR_GO_MODULES = GO_MODULES[1:]
# test_onboarding_guides.py reads these files outside services/hub.
HUB_FIXTURES = (
    "apps/docs-site/src/content/docs/docs/",
    "apps/fuwari-site/src/content/docs/",
    "apps/dns-site/src/pages/index.astro",
    "apps/console-site/src/pages/index.astro",
    "services/dns/templates/guide.html",
)
METADATA_FILES = {
    "README.md", "AGENTS.md", ".gitignore", ".dockerignore", ".env.example",
    ".github/dependabot.yml", ".github/CODEOWNERS",
    ".github/pull_request_template.md",
}


def matches(path, prefix):
    return path.startswith(prefix) if prefix.endswith("/") else path == prefix


def select_checks(paths, *, full=False):
    if full:
        return {
            "python_services": list(PYTHON_SERVICES),
            "astro_apps": list(ASTRO_APPS),
            "go_modules": list(GO_MODULES),
            "fuwari": True,
            "php": True,
        }

    python, astro, go = set(), set(), set()
    fuwari = php = False
    for path in paths:
        if path.startswith(".github/workflows/") or path in {
            "scripts/ci_select.py", "scripts/test_ci_select.py",
        }:
            return select_checks((), full=True)
        if any(matches(path, fixture) for fixture in HUB_FIXTURES):
            python.add("hub")
        if path.startswith("vendor/moddns-matchall/libs/"):
            # API, blocklists, dnscheck and proxy use replace ... => ../libs.
            go.update(VENDOR_GO_MODULES)
        for service in PYTHON_SERVICES:
            if path.startswith(f"services/{service}/"):
                python.add(service)
        for app in ASTRO_APPS:
            if path.startswith(f"apps/{app}/"):
                astro.add(app)
        for module in GO_MODULES:
            if path.startswith(module + "/"):
                go.add(module)
        fuwari |= path.startswith("apps/fuwari-site/")
        php |= path.startswith("wordpress/")

        if path == "scripts/preview-static.mjs":
            astro.update(("main-site", "status-site"))
        elif path in METADATA_FILES or path.startswith(("docs/", "infrastructure/")):
            pass
        elif path.startswith(tuple(
            [f"services/{name}/" for name in PYTHON_SERVICES]
            + [f"apps/{name}/" for name in ASTRO_APPS]
            + [module + "/" for module in GO_MODULES]
            + ["apps/fuwari-site/", "wordpress/"]
        )):
            pass
        elif path.startswith("vendor/moddns-matchall/app/"):
            # The existing workflow has no vendor React frontend check.
            pass
        elif path.startswith("vendor/moddns-matchall/"):
            # Shared vendor configuration/fixtures may affect every Go module.
            go.update(VENDOR_GO_MODULES)
        else:
            # Unknown shared config or new directories must not silently skip CI.
            return select_checks((), full=True)

    return {
        "python_services": [s for s in PYTHON_SERVICES if s in python],
        "astro_apps": [a for a in ASTRO_APPS if a in astro],
        "go_modules": [m for m in GO_MODULES if m in go],
        "fuwari": fuwari,
        "php": php,
    }


def checks_for_event(event_name, event):
    if event_name != "pull_request":
        return select_checks((), full=True)
    try:
        pr = event["pull_request"]
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        # Disabling rename detection includes BOTH the old and new paths.
        diff = subprocess.check_output([
            "git", "diff", "--name-only", "--no-renames", "-z",
            f"{base}...{head}", "--",
        ])
    except (KeyError, TypeError, OSError, subprocess.CalledProcessError):
        print("::warning::Cannot compute PR diff; running all existing checks.")
        return select_checks((), full=True)
    return select_checks(os.fsdecode(p) for p in diff.split(b"\0") if p)


def write_outputs(checks, output):
    for name, value in checks.items():
        output.write(f"{name}={json.dumps(value, separators=(',', ':'))}\n")
        if isinstance(value, list):
            output.write(f"has_{name}={str(bool(value)).lower()}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks = checks_for_event(args.event_name, json.loads(args.event_path.read_text()))
    with args.output.open("a", encoding="utf-8") as output:
        write_outputs(checks, output)
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
