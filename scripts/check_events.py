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

from evidence import (EvidenceError as EventError, validate_event_structure,
                      check_event_evidence)


def validate_event(event, index):
    validate_event_structure(event, index)
    check_event_evidence(event)


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
    print(f"结构与声明检查通过：{len(events)} 条事件；来源取得情况、真实独立性与实际支持关系未核验；未判断材料真实性")


if __name__ == "__main__":
    main()
