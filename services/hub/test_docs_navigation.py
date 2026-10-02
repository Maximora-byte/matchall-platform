import unittest
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

import app


class PageParser(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.links = []
        self.inputs = []
        self.forms = []
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs)
        elif tag == "input":
            self.inputs.append(attrs)
        elif tag == "form":
            self.forms.append(attrs)


class DocsNavigationTests(unittest.TestCase):
    def setUp(self):
        self.category = '账户 & 开发/"帮助"'
        self.query = 'search & "quoted"'
        self.articles = [dict(slug="guide", title=self.query, summary="Example", plain="Example",
                              category=self.category, version="1")]
        self.client = TestClient(app.app)

    def page(self, path="/docs", **params):
        with patch.object(app, "load_docs", return_value=self.articles):
            response = self.client.get(path, params=params or None)
        self.assertEqual(response.status_code, 200)
        return PageParser(response.text)

    def test_categories_stay_on_docs_and_preserve_escaped_search_and_language(self):
        page = self.page(q=self.query, lang="en")
        link = next(link for link in page.links if "category=" in link.get("href", ""))
        target = urlsplit(link["href"])
        self.assertEqual(target.path, "/docs")
        self.assertEqual(parse_qs(target.query), dict(q=[self.query], lang=["en"], category=[self.category]))
        filtered = self.page(link["href"])
        active = next(link for link in filtered.links if link.get("aria-current") == "page")
        self.assertEqual(parse_qs(urlsplit(active["href"]).query)["category"], [self.category])
        self.assertTrue(any(link.get("href") == "/docs/guide" for link in filtered.links))

    def test_all_clears_only_category_and_search_keeps_current_filter(self):
        page = self.page(q=self.query, category=self.category, lang="ja")
        all_link = next(link for link in page.links if link.get("href", "").startswith("/docs?") and "category=" not in link["href"])
        self.assertEqual(parse_qs(urlsplit(all_link["href"]).query), dict(q=[self.query], lang=["ja"]))
        self.assertEqual(page.forms[0].get("action"), "/docs")
        self.assertEqual(page.forms[0].get("method"), "get")
        inputs = {item["name"]: item for item in page.inputs}
        self.assertEqual(inputs["q"]["value"], self.query)
        self.assertEqual(inputs["q"]["aria-label"], "搜索文档")
        self.assertEqual(inputs["category"]["value"], self.category)
        self.assertEqual(inputs["lang"]["value"], "ja")


if __name__ == "__main__":
    unittest.main()
