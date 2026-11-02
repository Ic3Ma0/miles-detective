#!/usr/bin/env python3
"""Check a standalone events JSON against the event-ledger rules.

Use this when events are delivered as `events.json` instead of being appended to
`records.jsonl`. It checks structure only: required fields, enums, date
precision, locators, and the corroborated same-source-group rule. It does not
judge whether the content is true.

Accepted input: a JSON array of event objects, or an object with an `events`
array.

Example:
    python3 check_events.py events.json
"""
import argparse
import json
from pathlib import Path
import sys

ENUMS = {
    "status": {"documented", "corroborated", "disputed", "unverified"},
    "date_precision": {"day", "month", "year", "range", "unknown"},
    "scope": {"main", "background", "outside_window"},
    "evidence_type": {"self_account", "journalist_report", "institution_record", "mixed", "unknown"},
}
REQUIRED = ("id", "title", "summary", "status", "date_precision", "scope", "evidence_type")


class EventError(ValueError):
    pass


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate_event(event, index):
    if not isinstance(event, dict):
        raise EventError(f"第 {index} 条不是对象")
    rid = event.get("id") or f"#{index}"
    for key in REQUIRED:
        if not nonempty(event.get(key)):
            raise EventError(f"{rid}: 缺少非空 {key}")
    for key, allowed in ENUMS.items():
        if event[key] not in allowed:
            raise EventError(f"{rid}: 无效 {key}={event[key]!r}")
    if event["date_precision"] != "unknown" and not nonempty(event.get("date")):
        raise EventError(f"{rid}: 非 unknown 日期精度须有 date")

    source_ids = event.get("source_ids", [])
    claim_ids = event.get("claim_ids", [])
    locators = event.get("sources", [])
    for name, values in (("source_ids", source_ids), ("claim_ids", claim_ids)):
        if not isinstance(values, list) or not all(nonempty(v) for v in values):
            raise EventError(f"{rid}: {name} 须为非空字符串数组")
    if not isinstance(locators, list):
        raise EventError(f"{rid}: sources 须为数组")
    if not source_ids and not claim_ids and not locators:
        raise EventError(f"{rid}: 须引用至少一个来源、结论或文件定位")

    locator_keys = []
    for loc in locators:
        if not isinstance(loc, dict):
            raise EventError(f"{rid}: sources 项须为对象")
        sid = loc.get("source_id") or loc.get("id")
        if not nonempty(sid) and not nonempty(loc.get("file")):
            raise EventError(f"{rid}: sources 项须有 source_id、id 或 file")
        if "lines" in loc and not nonempty(str(loc["lines"])):
            raise EventError(f"{rid}: sources.lines 不能为空")
        if "group" in loc and not nonempty(loc["group"]):
            raise EventError(f"{rid}: sources.group 不能为空")
        locator_keys.append("id:" + sid if nonempty(sid) else "file:" + loc["file"])

    if "people" in event and (not isinstance(event["people"], list) or not all(nonempty(p) for p in event["people"])):
        raise EventError(f"{rid}: people 须为非空字符串数组")

    if event["status"] == "corroborated":
        keys = set("id:" + sid for sid in source_ids) | set(locator_keys)
        if len(keys) < 2:
            raise EventError(f"{rid}: corroborated 至少需要两个不同来源")
        groups = set()
        source_groups = event.get("source_groups", {})
        if not isinstance(source_groups, dict):
            raise EventError(f"{rid}: source_groups 须为对象")
        for sid in source_ids:
            group = source_groups.get(sid)
            if not nonempty(group):
                raise EventError(f"{rid}: corroborated 的 source_ids 须在 source_groups 标组")
            groups.add(group)
        for loc in locators:
            sid = loc.get("source_id") or loc.get("id")
            if nonempty(sid):
                group = loc.get("group") or source_groups.get(sid)
                if not nonempty(group):
                    raise EventError(f"{rid}: corroborated 的来源 {sid} 须标 group")
                groups.add(group)
            else:
                group = loc.get("group")
                if not nonempty(group):
                    raise EventError(f"{rid}: corroborated 的文件定位须标 group")
                groups.add(group)
        if len(groups) < 2:
            raise EventError(f"{rid}: corroborated 的来源属于同一同源组")


def load_events(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("events")
    if not isinstance(data, list):
        raise EventError("输入须为事件数组，或含 events 数组的对象")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="events.json 路径")
    args = parser.parse_args()
    try:
        events = load_events(args.path)
        for index, event in enumerate(events, 1):
            validate_event(event, index)
    except (EventError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"事件错误：{exc}\n")
    print(f"结构检查通过：{len(events)} 条事件；未判断材料真实性")


if __name__ == "__main__":
    main()
