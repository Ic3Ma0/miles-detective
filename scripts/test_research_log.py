import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research_log import RecordError, append, merge_case, records, report, validate


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

    def test_corroborated_claim_requires_two_usable_independent_sources(self):
        cases = [
            ("single", ["S1"], "original", "independent", "full_text", False),
            ("duplicate_evidence", ["S1", "S1"], "original", "independent", "full_text", False),
            ("same_group", ["S1", "S2"], "original", "original", "full_text", False),
            ("missing_group", ["S1", "S2"], "original", None, "full_text", False),
            ("unretrieved", ["S1", "S2"], "original", "independent", "unretrieved", False),
            ("independent", ["S1", "S2"], "original", "independent", "full_text", True),
        ]
        for name, ids, group1, group2, access2, accepted in cases:
            with self.subTest(name=name):
                source2 = self.source(access2, sid="S2", group=group2)
                source2["url"] = "https://example.org/independent"
                rows = [self.visit(outcome="content"), self.source("full_text", group=group1), source2]
                claim = self.claim("corroborated")
                claim["evidence"] = [{"source_id": sid, "locator": "正文", "relation": "supports"} for sid in ids]
                if accepted:
                    self.assertEqual(validate(rows + [claim], self.case)["C1"]["status"], "corroborated")
                else:
                    with self.assertRaises(RecordError):
                        validate(rows + [claim], self.case)

    def test_corroborated_claim_rejects_duplicate_url_and_context_only_support(self):
        for same_url, relation in [(True, "supports"), (False, "context"), (False, "contradicts")]:
            with self.subTest(same_url=same_url, relation=relation):
                source2 = self.source("full_text", sid="S2", group="independent")
                if not same_url:
                    source2["url"] = "https://example.org/independent"
                claim = self.claim("corroborated")
                claim["evidence"].append({"source_id": "S2", "locator": "正文", "relation": relation})
                with self.assertRaises(RecordError):
                    validate([self.visit(outcome="content"), self.source("full_text", group="original"), source2, claim], self.case)

    def test_corroborated_claim_keeps_valid_pair_with_extra_ungrouped_source(self):
        source2 = self.source("full_text", sid="S2", group="independent")
        source2["url"] = "https://example.org/second"
        source3 = self.source("full_text", sid="S3")
        source3["url"] = "https://example.org/third"
        claim = self.claim("corroborated")
        claim["evidence"].extend({"source_id": sid, "locator": "正文", "relation": "supports"} for sid in ["S2", "S3"])
        rows = [self.visit(outcome="content"), self.source("full_text", group="original"), source2, source3, claim]
        self.assertEqual(validate(rows, self.case)["C1"]["status"], "corroborated")

    def test_corroborated_claim_rechecked_after_source_correction(self):
        source2 = self.source("full_text", sid="S2", group="independent")
        source2["url"] = "https://example.org/independent"
        claim = self.claim("corroborated")
        claim["evidence"].append({"source_id": "S2", "locator": "正文", "relation": "supports"})
        append(self.case, [self.visit(outcome="content"), self.source("full_text", group="original"), source2, claim])
        before = (self.case / "records.jsonl").read_bytes()
        for correction in [dict(source2, same_source_group="original"), dict(source2, access="unretrieved")]:
            with self.assertRaises(RecordError):
                append(self.case, correction)
            self.assertEqual((self.case / "records.jsonl").read_bytes(), before)
        downgraded = dict(claim, status="documented_statement")
        append(self.case, [downgraded, dict(source2, same_source_group="original")])
        self.assertEqual(validate(records(self.case), self.case)["C1"]["status"], "documented_statement")

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
            self.visit("V2", "content"), {**self.source("full_text", ["V2"], "S2", "cnbc"), "url": "https://example.org/independent"},
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


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.case = Path(self.temp.name) / "case"
        self.case.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def search(self, sid="Q1"):
        return {"kind": "search", "id": sid, "engine": "fixture", "queries": ["人物"], "raw_path": "raw/B01.json"}

    def visit(self, sid="V1", outcome="content"):
        return {"kind": "visit", "id": sid, "url": "https://example.org/post", "method": "open",
                "outcome": outcome, "detail": "测试夹具", "raw_path": "raw/B01.json"}

    def source(self, sid="S1", url="https://example.org/a", group="origin", visits=("V1",)):
        return {"kind": "source", "id": sid, "title": "来源", "url": url, "voice": "self",
                "form": "original", "access": "full_text", "identity": "confirmed",
                "visit_ids": list(visits), "same_source_group": group, "limitation": "测试夹具"}

    def claim(self, sid="C1", source_id="S1", status="documented_statement"):
        return {"kind": "claim", "id": sid, "text": "原文这样说", "status": status,
                "evidence": [{"source_id": source_id, "locator": "正文", "relation": "supports"}]}

    def event(self, sid="EV1", source_ids=("S1",), status="documented", group=None,
              date="2020-01-01", title="事件", place="北京"):
        item = {"kind": "event", "id": sid, "date": date, "date_precision": "day",
                "scope": "main", "evidence_type": "journalist_report", "title": title,
                "summary": "摘要", "place": place, "status": status, "source_ids": list(source_ids)}
        if group:
            item["same_event_group"] = group
        return item

    def coverage(self, sid="CV1", refs=("S1",)):
        return {"kind": "coverage", "id": sid, "family": "新闻", "scope": "全时段",
                "state": "searched", "reason": "已检查", "record_ids": list(refs)}

    def write_shard(self, shard_id, rows):
        directory = self.case / "shards" / shard_id
        (directory / "raw").mkdir(parents=True)
        (directory / "raw" / "B01.json").write_text("{}")
        (directory / "shard.json").write_text(json.dumps(
            {"id": shard_id, "family": "新闻", "status": "complete", "stop_reason": "测试停止"}, ensure_ascii=False))
        (directory / "records.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    def test_merge_remaps_ids_references_and_raw_paths(self):
        self.write_shard("s01", [self.search(), self.visit(), self.source(url="https://example.org/s01"),
                                 self.claim(), self.event(), self.coverage()])
        self.write_shard("s02", [self.search(), self.visit(), self.source(url="https://example.org/s02"),
                                 self.claim(), self.event(), self.coverage()])
        report_data, merged = merge_case(self.case)
        by_kind = {}
        for row in merged:
            by_kind.setdefault(row["kind"], []).append(row)
        self.assertEqual([row["id"] for row in by_kind["search"]], ["Q01", "Q02"])
        self.assertEqual([row["id"] for row in by_kind["source"]], ["S01", "S02"])
        self.assertEqual([row["id"] for row in by_kind["event"]], ["EV01", "EV02"])
        self.assertEqual(by_kind["visit"][0]["raw_path"], "shards/s01/raw/B01.json")
        self.assertEqual(by_kind["event"][0]["source_ids"], ["S01"])
        self.assertEqual(by_kind["coverage"][0]["record_ids"], ["S01"])
        self.assertEqual(report_data["counts"]["output_records"], 12)
        self.assertTrue((self.case / "records.jsonl").is_file())
        self.assertTrue((self.case / "merge-report.json").is_file())

    def test_merge_dedupes_same_url_and_downgrades_corroborated(self):
        # Each input is valid. The earlier shard links the two URL groups;
        # merging duplicate URLs then reveals that the later pair is not independent.
        self.write_shard("s00", [self.visit(),
            self.source("S1", url="https://example.org/a", group="shared"),
            self.source("S2", url="https://example.org/b", group="shared")])
        self.write_shard("s01", [self.visit(),
            self.source("S1", url="https://example.org/a", group="a"),
            self.source("S2", url="https://example.org/b", group="b"),
            self.event(source_ids=("S1", "S2"), status="corroborated")])
        report_data, merged = merge_case(self.case)
        sources = [row for row in merged if row["kind"] == "source"]
        events = [row for row in merged if row["kind"] == "event"]
        self.assertEqual(len(sources), 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "documented")
        self.assertEqual(len(report_data["source_duplicates"]), 2)
        self.assertEqual(len(report_data["corroborated_downgraded"]), 1)

    def test_merge_keeps_corroborated_with_independent_shard_sources(self):
        self.write_shard("s01", [
            self.search(), self.visit("V1"), self.visit("V2", "content"),
            self.source("S1", url="https://a.example/1", group="a", visits=("V1",)),
            self.source("S2", url="https://a.example/2", group="b", visits=("V2",)),
            self.event(source_ids=("S1", "S2"), status="corroborated", group="shared"),
        ])
        self.write_shard("s02", [
            self.search(), self.visit("V1"), self.visit("V2", "content"),
            self.source("S1", url="https://b.example/1", group="a", visits=("V1",)),
            self.source("S2", url="https://b.example/2", group="b", visits=("V2",)),
            self.event(source_ids=("S1", "S2"), status="corroborated", group="shared"),
            self.coverage(refs=("EV1",)),
        ])
        report_data, merged = merge_case(self.case)
        events = [row for row in merged if row["kind"] == "event"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "corroborated")
        self.assertEqual(len(events[0]["source_ids"]), 4)
        coverage = [row for row in merged if row["kind"] == "coverage"][0]
        self.assertEqual(coverage["record_ids"], [events[0]["id"]])
        self.assertEqual(len(report_data["event_merged"]), 1)

    def test_merge_flags_same_date_title_place_without_group(self):
        self.write_shard("s01", [self.search(), self.visit(), self.source(), self.event()])
        self.write_shard("s02", [self.search(), self.visit(), self.source(), self.event()])
        report_data, merged = merge_case(self.case)
        self.assertEqual(len([row for row in merged if row["kind"] == "event"]), 2)
        self.assertEqual(len(report_data["duplicate_candidates"]), 1)
        self.assertEqual(len(report_data["duplicate_candidates"][0]["events"]), 2)

    def test_merge_conflict_keeps_events_separate(self):
        self.write_shard("s01", [self.search(), self.visit(), self.source(),
                                 self.event(date="2020-01-01", group="shared")])
        self.write_shard("s02", [self.search(), self.visit(), self.source(),
                                 self.event(date="2021-01-01", group="shared")])
        report_data, merged = merge_case(self.case)
        self.assertEqual(len([row for row in merged if row["kind"] == "event"]), 2)
        self.assertEqual(len(report_data["conflicts"]), 1)
        self.assertEqual(report_data["conflicts"][0]["date"], ["2020-01-01", "2021-01-01"])

    def test_merge_refuses_non_empty_target_without_force(self):
        self.write_shard("s01", [self.search(), self.visit(), self.source()])
        (self.case / "records.jsonl").write_text('{"existing": true}\n', encoding="utf-8")
        with self.assertRaises(RecordError):
            merge_case(self.case)

    def test_merge_dry_run_writes_nothing(self):
        self.write_shard("s01", [self.search(), self.visit(), self.source()])
        report_data, merged = merge_case(self.case, dry_run=True)
        self.assertTrue(merged)
        self.assertFalse((self.case / "records.jsonl").exists())
        self.assertFalse((self.case / "merge-report.json").exists())

    def test_report_cli_still_works_after_merge_subcommand(self):
        (self.case / "case.json").write_text(json.dumps({"person": "测试人物", "scope": "夹具"}), encoding="utf-8")
        (self.case / "records.jsonl").write_text("", encoding="utf-8")
        script = Path(__file__).with_name("research_log.py")
        proc = subprocess.run(
            [sys.executable, str(script), "report", str(self.case)],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("测试人物", proc.stdout)


if __name__ == "__main__":
    unittest.main()
