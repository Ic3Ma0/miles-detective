#!/usr/bin/env python3
"""Check the delivery header and next-round plan before handing over a report.

The point is to make two fields impossible to omit: the breadth/depth budget
with its stop reason, and a stop condition for every next-round query.

Input is a JSON object (usually `delivery.json`) with:

    {
      "mode": "online" | "desk_review",
      "fact_cutoff": "2026-10-26",
      "materials_scope": "十份本地材料，2011-2023",
      "breadth": "阶段与来源家族范围",
      "depth": "每个高优先级线索最多追几轮",
      "stop_reason": "为什么在这一轮停止",
      "open_gaps": 3,
      "next_plans": [
        {"gap": "...", "query": "...", "source_family": "...",
         "success": "...", "stop": "..."}
      ]
    }

If `open_gaps` > 0, `next_plans` must have at least one entry. Each plan must
state what would make the search stop.

This checks structure only; it does not judge whether the budget is sensible.
"""
import argparse
import json
from pathlib import Path
import sys

REQUIRED = ("mode", "fact_cutoff", "materials_scope", "breadth", "depth", "stop_reason")
MODES = {"online", "desk_review"}
PLAN_FIELDS = ("gap", "query", "source_family", "success", "stop")


class DeliveryError(ValueError):
    pass


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate_delivery(data):
    if not isinstance(data, dict):
        raise DeliveryError("delivery 须为对象")
    for key in REQUIRED:
        if not nonempty(data.get(key)):
            raise DeliveryError(f"缺少非空 {key}")
    if data["mode"] not in MODES:
        raise DeliveryError(f"无效 mode={data['mode']!r}，应为 online 或 desk_review")
    open_gaps = data.get("open_gaps")
    if not isinstance(open_gaps, int) or isinstance(open_gaps, bool) or open_gaps < 0:
        raise DeliveryError("open_gaps 须为大于等于 0 的整数")
    plans = data.get("next_plans")
    if not isinstance(plans, list):
        raise DeliveryError("next_plans 须为数组")
    if open_gaps > 0 and not plans:
        raise DeliveryError("仍有 {0} 个开放缺口，next_plans 不能为空".format(open_gaps))
    seen = set()
    for index, plan in enumerate(plans, 1):
        if not isinstance(plan, dict):
            raise DeliveryError(f"第 {index} 条计划不是对象")
        for key in PLAN_FIELDS:
            if not nonempty(plan.get(key)):
                raise DeliveryError(f"第 {index} 条计划缺少非空 {key}")
        if plan["gap"] in seen:
            raise DeliveryError(f"重复的缺口：{plan['gap']}")
        seen.add(plan["gap"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="delivery.json 路径")
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.path).read_text(encoding="utf-8"))
        validate_delivery(data)
    except (DeliveryError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"交付检查错误：{exc}\n")
    print(f"交付检查通过：{len(data['next_plans'])} 条下一轮计划；预算与停止原因已填；未判断内容真假")


if __name__ == "__main__":
    main()
