#!/usr/bin/env python3
"""Behavior tests for check_events.py. Standard library only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import check_events

SCRIPT = Path(__file__).with_name("check_events.py")


def event(**changes):
    item = {
        "kind": "event", "id": "EV01", "date": "2001-06-11", "date_precision": "day",
        "scope": "main", "evidence_type": "journalist_report",
        "title": "CNNIC 会面", "summary": "毛伟提出八条", "status": "documented",
        "sources": [{"file": "V23-newsmth.txt", "lines": "11-30"}],
    }
    item.update(changes)
    return item


class CheckEventsTests(unittest.TestCase):
    def write(self, directory, data):
        path = Path(directory) / "events.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_valid_documented_file_locator(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [event()])
            events = check_events.load_events(path)
            check_events.validate_event(events[0], 1)

    def test_sources_accepts_id_alias(self):
        item = event(sources=[{"id": "V29", "lines": "12, 35-37"}])
        check_events.validate_event(item, 1)

    def test_accepts_object_with_events_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {"events": [event()]})
            self.assertEqual(len(check_events.load_events(path)), 1)

    def test_missing_scope_rejected(self):
        item = event()
        item.pop("scope")
        with self.assertRaises(check_events.EventError):
            check_events.validate_event(item, 1)

    def test_invalid_evidence_type_rejected(self):
        with self.assertRaises(check_events.EventError):
            check_events.validate_event(event(evidence_type="hearsay"), 1)

    def test_corroborated_different_groups_accepted(self):
        item = event(
            status="corroborated",
            sources=[
                {"file": "V17-torrentfreak.txt", "lines": "15", "group": "torrentfreak"},
                {"file": "V23-cch.txt", "lines": "20", "group": "cch"},
            ],
        )
        check_events.validate_event(item, 1)

    def test_corroborated_same_group_rejected(self):
        item = event(
            status="corroborated",
            sources=[
                {"file": "V17-torrentfreak.txt", "lines": "15", "group": "torrentfreak"},
                {"file": "V19-torrentfreak.txt", "lines": "20", "group": "torrentfreak"},
            ],
        )
        with self.assertRaises(check_events.EventError):
            check_events.validate_event(item, 1)

    def test_corroborated_missing_group_rejected(self):
        item = event(
            status="corroborated",
            sources=[
                {"file": "V17-torrentfreak.txt", "lines": "15"},
                {"file": "V23-cch.txt", "lines": "20", "group": "cch"},
            ],
        )
        with self.assertRaises(check_events.EventError):
            check_events.validate_event(item, 1)

    def test_corroborated_one_source_rejected(self):
        item = event(status="corroborated")
        with self.assertRaises(check_events.EventError):
            check_events.validate_event(item, 1)

    def test_source_ids_need_source_groups_for_corroborated(self):
        good = event(
            status="corroborated", sources=[],
            source_ids=["S1", "S2"], source_groups={"S1": "torrentfreak", "S2": "cch"},
        )
        check_events.validate_event(good, 1)
        bad = dict(good)
        bad["source_groups"] = {"S1": "torrentfreak"}
        with self.assertRaises(check_events.EventError):
            check_events.validate_event(bad, 1)

    def test_cli_bad_file_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.json"
            path.write_text("[]", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("0 条事件", proc.stdout)


if __name__ == "__main__":
    unittest.main()
