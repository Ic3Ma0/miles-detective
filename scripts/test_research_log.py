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

    def source(self, access="unretrieved", visits=None, sid="S1", group=None):
        item = {"kind": "source", "id": sid, "title": "同名候选", "url": "https://example.org/post", "voice": "unresolved", "form": "unknown", "access": access, "identity": "unresolved", "visit_ids": visits or ["V1"], "limitation": "身份未核验"}
        if group:
            item["same_source_group"] = group
        return item

    def claim(self, status="documented_statement"):
        return {"kind": "claim", "id": "C1", "text": "页面这样记载", "status": status, "evidence": [{"source_id": "S1", "locator": "正文第二段", "relation": "supports"}]}

    def event(self, status="documented", **changes):
        item = {
            "kind": "event", "id": "EV1", "date": "2001-06-11", "date_precision": "day",
            "scope": "main", "evidence_type": "journalist_report",
            "title": "CNNIC 会面", "summary": "毛伟提出八条", "place": "北京中关村",
            "people": ["周鸿祎", "毛伟"], "status": status,
            "source_ids": ["S1"], "claim_ids": ["C1"],
        }
        item.update(changes)
        return item

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

    def test_event_requires_source_or_claim_and_report_shows_timeline(self):
        append(self.case, [self.visit(outcome="content"), self.source("full_text"), self.claim()])
        append(self.case, self.event())
        result = report(self.case)
        self.assertIn("时间线事件 1", result)
        self.assertIn("2001-06-11", result)
        self.assertIn("CNNIC 会面", result)

    def test_unknown_date_sorts_after_dated_events(self):
        append(self.case, [self.visit(outcome="content"), self.source("full_text"), self.claim()])
        append(self.case, self.event(id="EV1", title="有日期"))
        append(self.case, self.event(id="EV2", date="", date_precision="unknown", title="无日期"))
        result = report(self.case)
        self.assertLess(result.index("有日期"), result.index("无日期"))

    def test_event_without_source_or_claim_rejected(self):
        append(self.case, [self.visit(outcome="content"), self.source("full_text")])
        with self.assertRaises(RecordError):
            append(self.case, self.event(source_ids=[], claim_ids=[]))

    def test_event_status_and_date_precision_validated(self):
        append(self.case, [self.visit(outcome="content"), self.source("full_text"), self.claim()])
        with self.assertRaises(RecordError):
            append(self.case, self.event(status="confirmed"))
        with self.assertRaises(RecordError):
            append(self.case, self.event(date_precision="decade"))
        with self.assertRaises(RecordError):
            append(self.case, self.event(date="", date_precision="day"))

    def test_event_update_uses_latest_and_keeps_history(self):
        append(self.case, [self.visit(outcome="content"), self.source("full_text"), self.claim()])
        append(self.case, self.event())
        append(self.case, self.event(title="CNNIC 办公室会谈"))
        self.assertEqual(validate(records(self.case), self.case)["EV1"]["title"], "CNNIC 办公室会谈")
        result = report(self.case)
        self.assertIn("CNNIC 办公室会谈", result)
        self.assertNotIn("| CNNIC 会面 |", result)

    def test_event_unknown_reference_rejected(self):
        append(self.case, [self.visit(outcome="content"), self.source("full_text"), self.claim()])
        with self.assertRaises(RecordError):
            append(self.case, self.event(source_ids=["S404"]))

    def test_event_cannot_be_documented_from_search_snippet_only(self):
        append(self.case, {"kind": "search", "id": "Q1", "engine": "fixture", "queries": ["人物"], "raw_path": "raw.json"})
        src = self.source("search_only")
        src["visit_ids"] = []
        src["discovery_ids"] = ["Q1"]
        append(self.case, src)
        with self.assertRaises(RecordError):
            append(self.case, self.event(status="documented", source_ids=["S1"], claim_ids=[]))
        append(self.case, self.event(status="unverified", source_ids=["S1"], claim_ids=[]))

    def test_event_requires_scope_and_evidence_type(self):
        append(self.case, [self.visit(outcome="content"), self.source("full_text"), self.claim()])
        missing_scope = self.event()
        missing_scope.pop("scope")
        with self.assertRaises(RecordError):
            append(self.case, missing_scope)
        with self.assertRaises(RecordError):
            append(self.case, self.event(scope="later"))
        missing_type = self.event()
        missing_type.pop("evidence_type")
        with self.assertRaises(RecordError):
            append(self.case, missing_type)

    def test_event_accepts_file_locator_without_records(self):
        event = self.event(source_ids=[], claim_ids=[], sources=[{"file": "V01-2004sina.txt", "lines": "12"}])
        append(self.case, event)
        self.assertIn("V01-2004sina.txt L12", report(self.case))

    def test_event_accepts_id_locator_alias(self):
        event = self.event(source_ids=[], claim_ids=[], sources=[{"id": "V29", "lines": "12"}])
        append(self.case, event)
        self.assertIn("V29 L12", report(self.case))

    def test_corroborated_event_requires_source_groups(self):
        append(self.case, [
            self.visit("V1", "content"), self.source("full_text", ["V1"], "S1"),
            self.visit("V2", "content"), self.source("full_text", ["V2"], "S2"),
        ])
        with self.assertRaises(RecordError):
            append(self.case, self.event(status="corroborated", source_ids=["S1", "S2"], claim_ids=[]))

    def test_corroborated_event_same_group_rejected(self):
        append(self.case, [
            self.visit("V1", "content"), self.source("full_text", ["V1"], "S1", "torrentfreak"),
            self.visit("V2", "content"), self.source("full_text", ["V2"], "S2", "torrentfreak"),
        ])
        with self.assertRaises(RecordError):
            append(self.case, self.event(status="corroborated", source_ids=["S1", "S2"], claim_ids=[]))

    def test_corroborated_event_different_groups_accepted(self):
        append(self.case, [
            self.visit("V1", "content"), self.source("full_text", ["V1"], "S1", "torrentfreak"),
            self.visit("V2", "content"), self.source("full_text", ["V2"], "S2", "cnbc"),
        ])
        append(self.case, self.event(status="corroborated", source_ids=["S1", "S2"], claim_ids=[]))
        self.assertIn("corroborated", report(self.case))

    def test_corroborated_event_file_locators_with_groups_accepted(self):
        event = self.event(
            status="corroborated", source_ids=[], claim_ids=[],
            sources=[
                {"file": "V17-torrentfreak.txt", "lines": "15", "group": "torrentfreak"},
                {"file": "V23-cch.txt", "lines": "20", "group": "cch"},
            ],
        )
        append(self.case, event)
        self.assertIn("V17-torrentfreak.txt L15", report(self.case))

    def test_corroborated_event_file_locators_same_group_rejected(self):
        event = self.event(
            status="corroborated", source_ids=[], claim_ids=[],
            sources=[
                {"file": "V17-torrentfreak.txt", "lines": "15", "group": "torrentfreak"},
                {"file": "V19-torrentfreak.txt", "lines": "20", "group": "torrentfreak"},
            ],
        )
        with self.assertRaises(RecordError):
            append(self.case, event)


if __name__ == "__main__":
    unittest.main()
