"""Check or refresh six shared guides while retaining each renderer's wrapper.

Only the current flat, plain-scalar frontmatter format is supported. Rejecting
other YAML shapes avoids guessing how nested metadata should be rewritten.
No files are written unless every managed source and target passes validation.
"""

import argparse
import datetime
import re
import sys
from collections import namedtuple
from html.parser import HTMLParser
from pathlib import Path


GUIDE_SLUGS = ("getting-started", "dns-guide", "network-guide", "drive-guide",
               "mirrors-user", "mirrors-developer")
CANONICAL_DIR = Path("apps/fuwari-site/src/content/docs")
STARLIGHT_DIR = Path("apps/docs-site/src/content/docs/docs")
HUB_DIR = Path("services/hub/docs")
Document = namedtuple("Document", "metadata header_lines body footer newline")


class GuideSyncError(ValueError):
    """A managed guide cannot be safely interpreted or updated."""


class _FeedbackForm(HTMLParser):
    def __init__(self, slug):
        super().__init__(convert_charrefs=True)
        self.slug = slug
        self.open_tags = []
        self.forms = 0
        self.helpful_values = set()

    def handle_starttag(self, tag, attrs):
        names = [name for name, _ in attrs]
        if len(names) != len(set(names)):
            raise GuideSyncError("feedback form has duplicate attributes")
        attributes = dict(attrs)
        if not self.open_tags:
            if tag != "form" or self.forms:
                raise GuideSyncError("feedback footer must contain one trailing form")
            if (attributes.get("action") != f"/docs/{self.slug}/feedback"
                    or attributes.get("method", "").lower() != "post"
                    or "docs-feedback" not in attributes.get("class", "").split()):
                raise GuideSyncError("feedback form action, method or class is invalid")
            self.forms += 1
        elif tag == "form":
            raise GuideSyncError("feedback forms cannot be nested")
        if tag == "button" and attributes.get("name") == "helpful":
            self.helpful_values.add(attributes.get("value"))
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.open_tags.append(tag)

    def handle_endtag(self, tag):
        if not self.open_tags or self.open_tags.pop() != tag:
            raise GuideSyncError("feedback form tags are unbalanced")

    def handle_data(self, data):
        if not self.open_tags and data.strip():
            raise GuideSyncError("content follows the feedback form")

    def handle_comment(self, data):
        if not self.open_tags:
            raise GuideSyncError("content follows the feedback form")

    def validate(self):
        if self.forms != 1 or self.open_tags or self.helpful_values != {"0", "1"}:
            raise GuideSyncError("feedback form is incomplete")


def _outside_fences(lines):
    outside = []
    fence = None
    for line in lines:
        outside.append(fence is None)
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\n"))
        if marker is None:
            continue
        run, rest = marker.groups()
        if fence is None:
            fence = (run[0], len(run))
        elif run[0] == fence[0] and len(run) >= fence[1] and not rest.strip():
            fence = None
    if fence is not None:
        raise GuideSyncError("guide has an unclosed fenced code block")
    return outside


def parse_document(text, *, slug, feedback_required):
    """Parse a managed page without treating body rules or code as frontmatter."""
    if slug not in GUIDE_SLUGS:
        raise GuideSyncError("guide slug is not managed")
    newline = "\r\n" if "\r\n" in text else "\n"
    normalized = text.replace("\r\n", "\n")
    if "\r" in normalized or (newline == "\r\n" and "\n" in text.replace("\r\n", "")):
        raise GuideSyncError("guide has mixed or unsupported line endings")
    lines = normalized.splitlines(keepends=True)
    if not lines or lines[0] != "---\n":
        raise GuideSyncError("guide requires opening frontmatter")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.rstrip("\n") == "---")
    except StopIteration as exc:
        raise GuideSyncError("guide requires closing frontmatter") from exc
    metadata = {}
    header_lines = lines[1:end]
    for index, line in enumerate(header_lines, 2):
        value = line.rstrip("\n")
        if not value or value.startswith("#"):
            continue
        field = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*):[ \t]+([^\r\n]+)", value)
        if field is None:
            raise GuideSyncError(f"unsupported flat frontmatter at line {index}")
        key, scalar = field.groups()
        scalar = scalar.strip()
        if (not scalar or scalar[0] in "[{|>&*!'\"#" or scalar.startswith("- ")
                or " #" in scalar or ": " in scalar):
            raise GuideSyncError(f"unsupported scalar frontmatter at line {index}")
        if key in metadata:
            raise GuideSyncError(f"duplicate frontmatter key at line {index}")
        metadata[key] = scalar
    for key in ("title",):
        if key not in metadata:
            raise GuideSyncError(f"frontmatter is missing {key}")
    remaining = lines[end + 1:]
    outside = _outside_fences(remaining)
    form_starts = [index for index, line in enumerate(remaining)
                   if outside[index] and re.match(r"^ {0,3}<form\b", line)]
    footer = ""
    if form_starts:
        if not feedback_required or len(form_starts) != 1:
            raise GuideSyncError("guide has an unexpected or ambiguous feedback form")
        start = form_starts[0]
        separator = start - 1
        while separator >= 0 and not remaining[separator].strip():
            separator -= 1
        if separator < 0 or remaining[separator].rstrip("\n") != "---" or not outside[separator]:
            raise GuideSyncError("feedback form requires its trailing separator")
        parser = _FeedbackForm(slug)
        parser.feed("".join(remaining[start:]))
        parser.close()
        parser.validate()
        footer = "".join(remaining[separator:]).replace("\n", newline)
        remaining = remaining[:separator]
    elif feedback_required:
        raise GuideSyncError("guide requires its trailing feedback form")
    body = "".join(remaining).strip("\n")
    if body.split("\n", 1)[0] == f"# {metadata['title']}":
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.lstrip("\n")
    if not body.strip():
        raise GuideSyncError("guide body is empty")
    return Document(metadata, header_lines, body, footer, newline)


def _read_document(root, relative, *, slug, feedback_required):
    path = root / relative
    if not path.is_file():
        raise GuideSyncError(f"missing managed file: {relative.as_posix()}")
    if not path.resolve().is_relative_to(root) or any(item.is_symlink() for item in (path, *path.parents) if item != root):
        raise GuideSyncError(f"managed file cannot use a symbolic link: {relative.as_posix()}")
    try:
        return parse_document(path.read_bytes().decode("utf-8"), slug=slug, feedback_required=feedback_required)
    except (UnicodeError, GuideSyncError) as exc:
        raise GuideSyncError(f"{relative.as_posix()}: {exc}") from exc


def _required(document, keys):
    missing = [key for key in keys if key not in document.metadata]
    if missing:
        raise GuideSyncError("frontmatter is missing " + ", ".join(missing))


def _render(target, canonical, mapping):
    _required(target, mapping)
    replacements = {key: canonical.metadata[source] for key, source in mapping.items()}
    header = []
    for line in target.header_lines:
        key = line.partition(":")[0]
        if key in replacements:
            prefix = re.match(r"[^:]+:[ \t]+", line).group()
            line = prefix + replacements[key] + "\n"
        header.append(line)
    content = "---\n" + "".join(header) + "---\n\n" + canonical.body + "\n"
    content = content.replace("\n", target.newline)
    if target.footer:
        content += target.newline + target.footer
    return content


def plan_sync(root):
    """Validate all managed pages and return only target files that would change."""
    root = Path(root).resolve()
    documents = {}
    for slug in GUIDE_SLUGS:
        for directory, feedback in ((CANONICAL_DIR, True), (STARLIGHT_DIR, True), (HUB_DIR, False)):
            relative = directory / f"{slug}.md"
            documents[relative] = _read_document(root, relative, slug=slug, feedback_required=feedback)
    changes = {}
    for slug in GUIDE_SLUGS:
        canonical = documents[CANONICAL_DIR / f"{slug}.md"]
        _required(canonical, ("title", "description", "lastUpdated"))
        updated = canonical.metadata["lastUpdated"]
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated):
                raise ValueError
            datetime.date.fromisoformat(updated)
        except ValueError as exc:
            raise GuideSyncError(f"{CANONICAL_DIR.as_posix()}/{slug}.md: invalid lastUpdated date") from exc
        for directory, mapping in ((STARLIGHT_DIR, {"title": "title", "description": "description", "lastUpdated": "lastUpdated"}),
                (HUB_DIR, {"title": "title", "summary": "description", "updated": "lastUpdated"})):
            relative = directory / f"{slug}.md"
            try:
                expected = _render(documents[relative], canonical, mapping)
            except GuideSyncError as exc:
                raise GuideSyncError(f"{relative.as_posix()}: {exc}") from exc
            path = root / relative
            if path.read_bytes() != expected.encode("utf-8"):
                changes[path] = expected
    return changes


def synchronize(root, *, write=False):
    """Return drift paths; writing is opt-in and starts after complete validation."""
    changes = plan_sync(root)
    if write:
        for path, content in changes.items():
            path.write_bytes(content.encode("utf-8"))
    return tuple(changes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report drift without writing (default)")
    mode.add_argument("--write", action="store_true", help="refresh managed target guides")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        changes = synchronize(root, write=args.write)
    except (GuideSyncError, OSError) as exc:
        print(f"Guide synchronization failed: {exc}", file=sys.stderr)
        return 2
    for path in changes:
        print(f"{'UPDATED' if args.write else 'DRIFT'} {path.relative_to(root).as_posix()}")
    return 1 if changes and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
