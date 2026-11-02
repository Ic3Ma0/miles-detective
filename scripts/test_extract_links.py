#!/usr/bin/env python3
"""Behavior tests for extract_links.py. Standard library only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import extract_links

SCRIPT = Path(__file__).with_name("extract_links.py")


class ExtractLinksTests(unittest.TestCase):
    def write(self, directory, name, text, encoding="utf-8"):
        path = Path(directory) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode(encoding))
        return path

    def test_extracts_anchor_text_and_href(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "a.html", '<p>前文</p><a href="https://example.com/x">文章标题</a>')
            result = extract_links.extract(path)
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["links"][0]["text"], "文章标题")
            self.assertEqual(result["links"][0]["href"], "https://example.com/x")

    def test_nested_tags_and_entities(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(
                tmp, "a.html",
                '<a href="https://example.com/?a=1&amp;b=2"><span>原</span>帖</a>',
            )
            link = extract_links.extract(path)["links"][0]
            self.assertEqual(link["href"], "https://example.com/?a=1&b=2")
            self.assertEqual(link["text"], "原帖")

    def test_resolves_relative_against_base_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "a.html", '<a href="../post/1">上一篇</a><a href="/about">关于</a>')
            result = extract_links.extract(path, "https://example.com/dir/page.html")
            self.assertEqual(result["links"][0]["resolved"], "https://example.com/post/1")
            self.assertEqual(result["links"][1]["resolved"], "https://example.com/about")
            self.assertIn("relative", result["links"][0]["flags"])

    def test_reads_base_href_from_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(
                tmp, "a.html",
                '<base href="https://example.com/blog/"><a href="one.html">一</a>',
            )
            result = extract_links.extract(path)
            self.assertEqual(result["base_url"], "https://example.com/blog/")
            self.assertEqual(result["links"][0]["resolved"], "https://example.com/blog/one.html")

    def test_flags_special_links_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "a.html", """
                <a href="javascript:void(0)">脚本</a>
                <a href="mailto:a@example.com">邮件</a>
                <a href="#top">顶部</a>
                <a href="https://example.com/x">第一次</a>
                <a href="https://example.com/x">第二次</a>
                <a href="#empty"></a>
            """)
            links = extract_links.extract(path)["links"]
            self.assertIn("javascript", links[0]["flags"])
            self.assertIn("mailto", links[1]["flags"])
            self.assertIn("fragment", links[2]["flags"])
            self.assertNotIn("duplicate", links[3]["flags"])
            self.assertIn("duplicate", links[4]["flags"])
            self.assertIn("empty_text", links[5]["flags"])

    def test_heading_and_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "a.html", "<h2>周鸿祎的真经</h2><p>正文前一句。</p><a href='x.html'>文章</a>")
            link = extract_links.extract(path, "https://example.com/")["links"][0]
            self.assertEqual(link["heading"], "周鸿祎的真经")
            self.assertIn("正文前一句", link["context"])

    def test_filters_and_min_text(self):
        link = {"text": "短", "href": "https://a.com/1", "resolved": "https://a.com/1"}
        self.assertFalse(extract_links.passes(link, r"b\.com", None, 0))
        self.assertTrue(extract_links.passes(link, None, r"b\.com", 0))
        self.assertFalse(extract_links.passes(link, None, None, 2))

    def test_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "a.html", '<a href="https://example.com/x">一</a><a href="https://example.com/x">二</a>')
            result = extract_links.extract(path)
            seen, unique = set(), []
            for link in result["links"]:
                if link["resolved"] not in seen:
                    seen.add(link["resolved"])
                    unique.append(link)
            self.assertEqual(len(unique), 1)

    def test_directory_and_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write(tmp, "a.html", '<a href="/a">a</a>')
            self.write(tmp, "sub/b.html", '<a href="/b">b</a>')
            flat = extract_links.collect_files([tmp], False)
            deep = extract_links.collect_files([tmp], True)
            self.assertEqual(len(flat), 1)
            self.assertEqual(len(deep), 2)

    def test_gb18030_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(
                tmp, "gb.html",
                '<meta charset="gb18030"><a href="/x">中文标题</a>',
                encoding="gb18030",
            )
            result = extract_links.extract(path)
            self.assertEqual(result["links"][0]["text"], "中文标题")

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "a.html", '<a href="https://example.com/x">标题</a>')
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), "--json", "--quiet"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual(data[0]["links"][0]["resolved"], "https://example.com/x")

    def test_missing_path_exits_nonzero(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "/nonexistent/file.html", "--quiet"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
