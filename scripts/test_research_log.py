import json
from pathlib import Path
import tempfile
import unittest

from research_log import RecordError, append, records, report, validate


class ResearchLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.case = Path(self.temp.name)
        (self.case / "case.json").write_text(json.dumps({"person": "测试人物", "scope": "隔离夹具"}))
        (self.case / "records.jsonl").write_text("")
        (self.case / "raw.json").write_text('{"result":"fixture"}')

    def tearDown(self):
        self.temp.cleanup()

    def visit(self, rid="V1", outcome="error"):
        return {"kind": "visit", "id": rid, "url": "https://example.org/post", "method": "open", "outcome": outcome, "detail": "测试夹具", "raw_path": "raw.json"}

    def source(self, access="unretrieved", visits=None):
        return {"kind": "source", "id": "S1", "title": "同名候选", "url": "https://example.org/post", "voice": "unresolved", "form": "unknown", "access": access, "identity": "unresolved", "visit_ids": visits or ["V1"], "limitation": "身份未核验"}

    def claim(self, status="documented_statement"):
        return {"kind": "claim", "id": "C1", "text": "页面这样记载", "status": status, "evidence": [{"source_id": "S1", "locator": "正文第二段", "relation": "supports"}]}

    def test_failed_visit_cannot_be_full_text_and_batch_is_atomic(self):
        with self.assertRaises(RecordError):
            append(self.case, [self.visit(), self.source("full_text")])
        self.assertEqual(records(self.case), [])

    def test_failed_source_cannot_support_documented_claim(self):
        append(self.case, [self.visit(), self.source()])
        with self.assertRaises(RecordError):
            append(self.case, self.claim())
        append(self.case, self.claim("unverified"))

    def test_retry_preserves_failure_and_source_history(self):
        append(self.case, [self.visit(), self.source()])
        append(self.case, [self.visit("V2", "content"), self.source("full_text", ["V1", "V2"]), self.claim()])
        rows = records(self.case)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["outcome"], "error")
        self.assertEqual(rows[1]["access"], "unretrieved")
        self.assertEqual(validate(rows, self.case)["S1"]["access"], "full_text")
        self.assertEqual(len({r["event_id"] for r in rows}), 5)

    def test_search_count_is_not_access_count(self):
        append(self.case, {"kind": "search", "id": "Q1", "engine": "fixture", "queries": ["人物原名", "人物旧名"], "raw_path": "raw.json"})
        append(self.case, self.visit())
        result = report(self.case)
        self.assertIn("检索批次 1，查询词 2，访问行为 1，来源条目 0", result)
        self.assertIn("不代表独立证据数", result)

    def test_unknown_reference_and_missing_raw_file_rejected(self):
        with self.assertRaises(RecordError):
            append(self.case, self.source())
        bad = self.visit()
        bad["raw_path"] = "missing.json"
        with self.assertRaises(RecordError):
            append(self.case, bad)

    def test_visit_history_is_immutable(self):
        append(self.case, self.visit())
        with self.assertRaises(RecordError):
            append(self.case, self.visit(outcome="content"))
        self.assertEqual(len(records(self.case)), 1)

    def test_classification_correction_keeps_history_and_access_count(self):
        append(self.case, self.visit(outcome="partial"))
        correction = self.visit(outcome="shell")
        correction['correction_reason'] = '核对原始返回后发现只有导航'
        append(self.case, correction)
        self.assertEqual(len(records(self.case)), 2)
        self.assertEqual(records(self.case)[0]['outcome'], 'partial')
        self.assertIn('访问行为 1', report(self.case))
        correction['url'] = 'https://example.org/another'
        with self.assertRaises(RecordError):
            append(self.case, correction)

    def test_search_only_source_is_not_upgraded_by_claim(self):
        append(self.case, {"kind": "search", "id": "Q1", "engine": "fixture", "queries": ["人物"], "raw_path": "raw.json"})
        src = self.source("search_only")
        src["visit_ids"] = []
        src["discovery_ids"] = ["Q1"]
        append(self.case, src)
        with self.assertRaises(RecordError):
            append(self.case, self.claim())

    def test_source_downgrade_cannot_silently_leave_claim_verified(self):
        append(self.case, [self.visit(outcome="content"), self.source("full_text"), self.claim()])
        with self.assertRaises(RecordError):
            append(self.case, self.source("unretrieved"))

    def test_unknown_identity_and_podcast_notes_remain_distinct(self):
        append(self.case, self.visit(outcome="metadata"))
        src = self.source("metadata_only")
        src.update(form="program_notes", voice="mixed")
        append(self.case, src)
        self.assertEqual(validate(records(self.case), self.case)["S1"]["identity"], "unresolved")
        with self.assertRaises(RecordError):
            append(self.case, self.source("audio_video_reviewed"))

    def test_visit_correction_cannot_leave_source_falsely_full_text(self):
        append(self.case, [self.visit(outcome="content"), self.source("full_text")])
        correction = self.visit(outcome="shell")
        correction['correction_reason'] = '复核发现只有导航'
        with self.assertRaises(RecordError):
            append(self.case, correction)


if __name__ == "__main__":
    unittest.main()
