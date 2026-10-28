#!/usr/bin/env python3
"""Append-only research records. Structural checks only; no network or truth score."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit


class RecordError(ValueError):
    pass


ENUMS = {
    "visit": {"outcome": {"content", "partial", "metadata", "shell", "error"}},
    "source": {
        "voice": {"self", "other", "mixed", "unresolved"},
        "form": {"original", "reprint", "quote", "catalog", "program_notes", "institution_record", "unknown"},
        "access": {"full_text", "partial_text", "metadata_only", "search_only", "unretrieved", "transcript", "audio_video_reviewed"},
        "identity": {"confirmed", "supported", "unresolved", "not_applicable"},
    },
    "claim": {"status": {"documented_statement", "corroborated", "disputed", "unverified", "analysis"}},
    "clue": {"state": {"open", "blocked", "resolved", "deferred"}, "priority": {"high", "medium", "low"}},
    "coverage": {"state": {"unsearched", "searched", "partial", "blocked", "deferred", "not_applicable"}},
}
REQUIRED = {
    "search": ("engine", "raw_path"),
    "visit": ("url", "method", "detail", "raw_path"),
    "source": ("title", "url", "limitation"),
    "claim": ("text",),
    "clue": ("question", "next_step"),
    "coverage": ("family", "scope", "reason"),
}
ACCESS_OUTCOMES = {
    "full_text": {"content"},
    "partial_text": {"content", "partial"},
    "metadata_only": {"content", "partial", "metadata"},
    "transcript": {"content", "partial"},
    "audio_video_reviewed": {"content", "partial"},
}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def records(case):
    path = Path(case) / "records.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate(items, case):
    """Validate in chronological order. References must already exist."""
    latest, kinds, seen_events = {}, {}, set()
    for record in items:
        if not isinstance(record, dict):
            raise RecordError("记录必须是对象")
        kind, rid = record.get("kind"), record.get("id")
        if kind not in REQUIRED or not nonempty(rid):
            raise RecordError("kind 或 id 缺失/无效")
        if rid in kinds and kinds[rid] != kind:
            raise RecordError(f"{rid}: ID 不能跨类型复用")
        if rid in latest and kind == "search":
            raise RecordError(f"{rid}: 检索不可改写，重试请用新 ID")
        if rid in latest and kind == "visit":
            if not nonempty(record.get("correction_reason")):
                raise RecordError(f"{rid}: 访问分类更正须有 correction_reason；重试请用新 ID")
            annotation = {"outcome", "detail", "correction_reason", "event_id", "recorded_at"}
            before = {k: v for k, v in latest[rid].items() if k not in annotation}
            after = {k: v for k, v in record.items() if k not in annotation}
            if before != after:
                raise RecordError(f"{rid}: 访问请求事实不可更改，重试请用新 ID")
        for key in REQUIRED[kind]:
            if not nonempty(record.get(key)):
                raise RecordError(f"{rid}: 缺少非空 {key}")
        for key, allowed in ENUMS.get(kind, {}).items():
            if record.get(key) not in allowed:
                raise RecordError(f"{rid}: 无效 {key}")
        if "url" in record:
            url = urlsplit(record["url"])
            if url.scheme not in {"http", "https"} or not url.netloc:
                raise RecordError(f"{rid}: URL 须为完整公开网页地址")
        if kind in {"search", "visit"} and not (Path(case) / record["raw_path"]).is_file():
            raise RecordError(f"{rid}: 原始输出文件不存在")

        def refs(field, expected=None, required=False):
            values = record.get(field, [])
            if not isinstance(values, list) or (required and not values):
                raise RecordError(f"{rid}: {field} 须为{'非空' if required else ''}数组")
            for ref in values:
                if not isinstance(ref, str) or ref not in latest or (expected and kinds[ref] != expected):
                    raise RecordError(f"{rid}: 未知或类型不符的引用 {ref!r}")
            return values

        if kind == "search":
            queries = record.get("queries")
            if not isinstance(queries, list) or not queries or not all(nonempty(q) for q in queries):
                raise RecordError(f"{rid}: queries 须为非空查询数组")
        elif kind == "source":
            visits = refs("visit_ids", "visit")
            discoveries = refs("discovery_ids", "search")
            access = record["access"]
            if access == "search_only" and not discoveries:
                raise RecordError(f"{rid}: 仅摘要须引用实际检索")
            if access in ACCESS_OUTCOMES and not any(latest[v]["outcome"] in ACCESS_OUTCOMES[access] for v in visits):
                raise RecordError(f"{rid}: 获取层级没有相应成功访问支撑")
        elif kind == "claim":
            evidence = record.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                raise RecordError(f"{rid}: 结论须列出 evidence")
            usable = False
            for ev in evidence:
                if not isinstance(ev, dict):
                    raise RecordError(f"{rid}: evidence 项须为对象")
                sid = ev.get("source_id")
                if sid not in latest or kinds[sid] != "source" or not nonempty(ev.get("locator")):
                    raise RecordError(f"{rid}: 缺少有效来源/定位")
                if ev.get("relation") not in {"supports", "contradicts", "context"}:
                    raise RecordError(f"{rid}: evidence.relation 无效")
                if latest[sid]["access"] not in {"unretrieved", "search_only"} and ev["relation"] == "supports":
                    usable = True
            if record["status"] != "unverified" and not usable:
                raise RecordError(f"{rid}: 已记载/分析结论不能只有未取得材料或搜索摘要")
        elif kind == "clue":
            refs("origin_ids", required=True)
        elif kind == "coverage":
            refs("record_ids")
        event_id = record.get("event_id")
        if event_id is not None:
            if event_id in seen_events:
                raise RecordError("event_id 重复")
            seen_events.add(event_id)
        kinds[rid] = kind
        latest[rid] = record
    # 后续来源更新也不能使既有确定性结论失去所有可用支持。
    for record in latest.values():
        if record["kind"] == "source" and record["access"] in ACCESS_OUTCOMES:
            if not any(latest[v]["outcome"] in ACCESS_OUTCOMES[record["access"]] for v in record.get("visit_ids", [])):
                raise RecordError(f"{record['id']}: 最新访问分类已不能支撑获取层级")
        if record["kind"] == "claim" and record["status"] != "unverified":
            if not any(latest[e["source_id"]]["access"] not in {"unretrieved", "search_only"} and e["relation"] == "supports" for e in record["evidence"]):
                raise RecordError(f"{record['id']}: 最新来源状态已不能支撑该结论")
    return latest


def append(case, incoming):
    case = Path(case)
    old = records(case)
    incoming = incoming if isinstance(incoming, list) else [incoming]
    additions = []
    for offset, record in enumerate(incoming, len(old) + 1):
        if not isinstance(record, dict):
            raise RecordError("记录必须是对象")
        additions.append({**record, "event_id": f"E{offset:06d}", "recorded_at": datetime.now(timezone.utc).isoformat()})
    validate(old + additions, case)
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in old + additions)
    # 单案例串行使用；先验证整批，失败时不写半批记录。
    temp = case / "records.jsonl.pending"
    temp.write_text(text, encoding="utf-8")
    temp.replace(case / "records.jsonl")
    return len(additions)


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def report(case):
    case = Path(case)
    events = records(case)
    latest = validate(events, case)
    meta = json.loads((case / "case.json").read_text(encoding="utf-8"))
    by_kind = {k: [r for r in latest.values() if r["kind"] == k] for k in REQUIRED}
    counts = Counter(r["access"] for r in by_kind["source"])
    lines = [f"# {meta['person']}｜研究记录摘要", "", f"本轮范围：{meta['scope']}", "",
             f"保留 {len(events)} 条事件；检索批次 {len(by_kind['search'])}，查询词 {sum(len(r['queries']) for r in by_kind['search'])}，访问行为 {len(by_kind['visit'])}，来源条目 {len(by_kind['source'])}。", "",
             "这些数量不代表独立证据数、事实准确率或互联网覆盖率。记录时间不等于实际访问时间。", "", "获取层级：" + json.dumps(dict(counts), ensure_ascii=False), "",
             "| 来源 | 标题 | 获取层级 | 地址 | 限制 |", "|---|---|---|---|---|"]
    for r in by_kind["source"]:
        lines.append("| " + " | ".join(cell(r[k]) for k in ("id", "title", "access", "url", "limitation")) + " |")
    lines.extend(["", "| 来源家族 | 状态 | 实际范围 | 原因 |", "|---|---|---|---|"])
    for r in by_kind["coverage"]:
        lines.append("| " + " | ".join(cell(r[k]) for k in ("family", "state", "scope", "reason")) + " |")
    lines.extend(["", "| 线索 | 状态 | 问题 | 下一步 |", "|---|---|---|---|"])
    for r in by_kind["clue"]:
        lines.append("| " + " | ".join(cell(r[k]) for k in ("id", "state", "question", "next_step")) + " |")
    lines.extend(["", "这是结构化记录的摘要，不能替代带证据定位的正文及人工核验。", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("case")
    init.add_argument("--person", required=True)
    init.add_argument("--scope", required=True)
    add = sub.add_parser("append")
    add.add_argument("case")
    add.add_argument("--input", required=True)
    check = sub.add_parser("check")
    check.add_argument("case")
    output = sub.add_parser("report")
    output.add_argument("case")
    output.add_argument("--output")
    args = parser.parse_args()
    try:
        if args.command == "init":
            case = Path(args.case)
            if case.exists() and any(case.iterdir()):
                raise RecordError("案例目录非空；为保护已有资料，未初始化")
            case.mkdir(parents=True, exist_ok=True)
            (case / "case.json").write_text(json.dumps({"person": args.person, "scope": args.scope}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (case / "records.jsonl").write_text("", encoding="utf-8")
            print("案例已初始化")
        elif args.command == "append":
            payload = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
            print(f"已追加 {append(args.case, json.loads(payload))} 条记录")
        elif args.command == "check":
            items = records(args.case)
            validate(items, args.case)
            print(f"结构检查通过：{len(items)} 条事件；未判断材料真实性")
        else:
            result = report(args.case)
            if args.output:
                Path(args.output).write_text(result, encoding="utf-8")
                print("摘要已写入指定文件")
            else:
                print(result)
    except (RecordError, OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"记录错误：{exc}\n")


if __name__ == "__main__":
    main()
