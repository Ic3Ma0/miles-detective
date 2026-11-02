#!/usr/bin/env python3
"""Behavior tests for check_delivery.py. Standard library only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import check_delivery

SCRIPT = Path(__file__).with_name("check_delivery.py")


def delivery(**changes):
    item = {
        "mode": "desk_review",
        "fact_cutoff": "2023-12-31",
        "materials_scope": "十份本地材料，2011-2023",
        "breadth": "2011-2023 的求学、创业、监管三个阶段",
        "depth": "每个高优先级缺口最多两轮检索",
        "stop_reason": "十份材料读完，高优先级缺口已写进计划",
        "open_gaps": 1,
        "next_plans": [{
            "gap": "2011-2014 的宾大经历",
            "query": "\"Justin Sun\" \"University of Pennsylvania\"",
            "source_family": "校友记录、同期报道",
            "success": "找到入学或毕业年份",
            "stop": "两轮只有同一篇访谈的转载",
        }],
    }
    item.update(changes)
    return item


class CheckDeliveryTests(unittest.TestCase):
    def test_valid_delivery(self):
        check_delivery.validate_delivery(delivery())

    def test_missing_breadth_rejected(self):
        item = delivery()
        item.pop("breadth")
        with self.assertRaises(check_delivery.DeliveryError):
            check_delivery.validate_delivery(item)

    def test_missing_stop_reason_rejected(self):
        item = delivery()
        item.pop("stop_reason")
        with self.assertRaises(check_delivery.DeliveryError):
            check_delivery.validate_delivery(item)

    def test_invalid_mode_rejected(self):
        with self.assertRaises(check_delivery.DeliveryError):
            check_delivery.validate_delivery(delivery(mode="quick"))

    def test_open_gaps_need_plans(self):
        with self.assertRaises(check_delivery.DeliveryError):
            check_delivery.validate_delivery(delivery(open_gaps=2, next_plans=[]))

    def test_no_open_gaps_allows_empty_plans(self):
        check_delivery.validate_delivery(delivery(open_gaps=0, next_plans=[]))

    def test_plan_missing_stop_rejected(self):
        item = delivery()
        item["next_plans"][0].pop("stop")
        with self.assertRaises(check_delivery.DeliveryError):
            check_delivery.validate_delivery(item)

    def test_duplicate_gap_rejected(self):
        item = delivery()
        item["next_plans"].append(dict(item["next_plans"][0]))
        with self.assertRaises(check_delivery.DeliveryError):
            check_delivery.validate_delivery(item)

    def test_negative_open_gaps_rejected(self):
        with self.assertRaises(check_delivery.DeliveryError):
            check_delivery.validate_delivery(delivery(open_gaps=-1))

    def test_cli_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delivery.json"
            path.write_text(json.dumps(delivery(), ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("交付检查通过", proc.stdout)


if __name__ == "__main__":
    unittest.main()
