#!/usr/bin/env python3
"""Behaviour tests for scripts/mc_to_records.py."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import mc_to_records

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "research_log.py"


class TimestampTest(unittest.TestCase):
    def test_milliseconds_and_seconds(self):
        self.assertTrue(mc_to_records.timestamp_date(1779758939000).startswith("2026-"))
        self.assertTrue(mc_to_records.timestamp_date(1792166470).startswith("2026-"))

    def test_invalid_values(self):
        self.assertEqual(mc_to_records.timestamp_date(None), "")
        self.assertEqual(mc_to_records.timestamp_date("x"), "")


class NormalizeTest(unittest.TestCase):
    def test_xhs_url_fallback(self):
        url, title, author, date, text = mc_to_records.normalize("xhs", {
            "note_id": "abc", "title": "标题", "desc": "正文", "nickname": "作者",
            "time": 1779758939000})
        self.assertEqual(url, "https://www.xiaohongshu.com/explore/abc")
        self.assertEqual((title, author, text), ("标题", "作者", "正文"))
        self.assertTrue(date.startswith("2026-"))

    def test_zhihu_answer_url(self):
        url, title, author, date, text = mc_to_records.normalize("zhihu", {
            "content_id": "123", "content_type": "answer", "title": "问题",
            "content_text": "回答", "created_time": 1792166470})
        self.assertEqual(url, "https://www.zhihu.com/answer/123")
        self.assertEqual(text, "回答")
        self.assertTrue(date.startswith("2026-"))

    def test_missing_title_is_dropped(self):
        url, title, *_ = mc_to_records.normalize("xhs", {"note_id": "abc"})
        self.assertEqual(url, "https://www.xiaohongshu.com/explore/abc")
        self.assertEqual(title, "")


class ConvertTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.case = self.root / "case"
        self.case.mkdir()
        subprocess.run(
            [sys.executable, str(LOG), "init", str(self.case),
             "--person", "测试", "--scope", "测试"],
            check=True, capture_output=True)
        self.jsonl = self.root / "data" / "xhs" / "jsonl" / "notes.jsonl"
        self.jsonl.parent.mkdir(parents=True)
        rows = [
            {"note_id": "n1", "note_url": "https://www.xiaohongshu.com/explore/n1",
             "title": "标题一", "desc": "正文一", "nickname": "作者一", "time": 1779758939000},
            {"note_id": "n2", "title": "标题二", "desc": "正文二", "nickname": "作者二",
             "time": 1779758939000},
        ]
        self.jsonl.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_convert(self):
        return subprocess.run(
            [sys.executable, str(ROOT / "mc_to_records.py"), "--case", str(self.case),
             "--jsonl", str(self.jsonl), "--data-dir", str(self.root / "data")],
            capture_output=True, text=True)

    def test_writes_visits_and_sources(self):
        result = self.run_convert()
        self.assertEqual(result.returncode, 0, result.stderr)
        records = [json.loads(line) for line in
                   (self.case / "records.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["kind"] for r in records],
                         ["visit", "source", "visit", "source"])
        self.assertEqual(records[1]["url"], "https://www.xiaohongshu.com/explore/n1")
        self.assertEqual(records[3]["url"], "https://www.xiaohongshu.com/explore/n2")
        self.assertTrue(list((self.case / "raw").glob("mc-xhs-*.jsonl")))

        check = subprocess.run([sys.executable, str(LOG), "check", str(self.case)],
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_rerun_skips_existing(self):
        self.assertEqual(self.run_convert().returncode, 0)
        again = self.run_convert()
        self.assertEqual(again.returncode, 0)
        self.assertIn("没有新记录", again.stdout)
        records = [json.loads(line) for line in
                   (self.case / "records.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(records), 4)


if __name__ == "__main__":
    unittest.main()
