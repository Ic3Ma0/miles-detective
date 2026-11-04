#!/usr/bin/env python3
"""Append-only research records. Structural checks only; no network or truth score."""
import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit


from evidence import (EvidenceError as RecordError, validate_event_structure,
                      event_support, check_event_evidence, claim_support,
                      independent_pair, canonical_groups, ENUMS as EVENT_ENUMS,
                      REQUIRED as EVENT_REQUIRED)


ENUMS = {
    "visit": {"outcome": {"content", "partial", "metadata", "shell", "error"}},
    "source": {
        "voice": {"self", "other", "mixed", "unresolved"},
        "form": {"original", "reprint", "quote", "catalog", "program_notes", "institution_record", "unknown"},
        "access": {"full_text", "partial_text", "metadata_only", "search_only", "unretrieved", "transcript", "audio_video_reviewed"},
        "identity": {"confirmed", "supported", "unresolved", "not_applicable"},
    },
    "claim": {"status": {"documented_statement", "corroborated", "disputed", "unverified", "analysis"}},
    "event": EVENT_ENUMS,
    "clue": {"state": {"open", "blocked", "resolved", "deferred"}, "priority": {"high", "medium", "low"}},
    "coverage": {"state": {"unsearched", "searched", "partial", "blocked", "deferred", "not_applicable"}},
}
REQUIRED = {
    "search": ("engine", "raw_path"),
    "visit": ("url", "method", "detail", "raw_path"),
    "source": ("title", "url", "limitation"),
    "claim": ("text",),
    "event": tuple(key for key in EVENT_REQUIRED if key != "id"),
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


def claim_is_corroborated(record, sources):
    """Check declared independence, not whether the underlying claim is true."""
    return independent_pair(claim_support(record, sources))


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def records(case):
    path = Path(case) / "records.jsonl"
    return read_jsonl(path)


def read_jsonl(path):
    path = Path(path)
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
            if "same_source_group" in record and not nonempty(record["same_source_group"]):
                raise RecordError(f"{rid}: same_source_group 不能为空")
            if access == "search_only" and not discoveries:
                raise RecordError(f"{rid}: 仅摘要须引用实际检索")
            if access in ACCESS_OUTCOMES and not any(latest[v]["outcome"] in ACCESS_OUTCOMES[access] for v in visits):
                raise RecordError(f"{rid}: 获取层级没有相应成功访问支撑")
        elif kind == "claim":
            evidence = record.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                raise RecordError(f"{rid}: 结论须列出 evidence")
            for ev in evidence:
                if not isinstance(ev, dict):
                    raise RecordError(f"{rid}: evidence 项须为对象")
                sid = ev.get("source_id")
                if sid not in latest or kinds[sid] != "source" or not nonempty(ev.get("locator")):
                    raise RecordError(f"{rid}: 缺少有效来源/定位")
                if ev.get("relation") not in {"supports", "contradicts", "context"}:
                    raise RecordError(f"{rid}: evidence.relation 无效")
            if record["status"] != "unverified" and not claim_support(record, latest):
                raise RecordError(f"{rid}: 已记载/分析结论不能只有未取得材料或搜索摘要")
            if record["status"] == "corroborated" and not claim_is_corroborated(record, latest):
                raise RecordError(f"{rid}: corroborated 须有两个已取得、不同 URL 且标明不同同源组的支持来源")
        elif kind == "event":
            refs("source_ids", "source")
            refs("claim_ids", "claim")
            validate_event_structure(record, rid)
            for loc in record.get("sources", []):
                explicit = loc.get("source_id")
                if explicit and (explicit not in latest or kinds[explicit] != "source"):
                    raise RecordError(f"{rid}: 未知来源引用 {explicit!r}")
            if "same_event_group" in record and not nonempty(record["same_event_group"]):
                raise RecordError(f"{rid}: same_event_group 不能为空")
            check_event_evidence(record, {s: r for s, r in latest.items() if r["kind"] == "source"}, latest)
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
            if not claim_support(record, latest):
                raise RecordError(f"{record['id']}: 最新来源状态已不能支撑该结论")
        if record["kind"] == "claim" and record["status"] == "corroborated" and not claim_is_corroborated(record, latest):
            raise RecordError(f"{record['id']}: 最新来源状态已不能支撑两个独立来源的 corroborated 结论")
        if record["kind"] == "event":
            check_event_evidence(record, {s: r for s, r in latest.items() if r["kind"] == "source"}, latest)
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


def event_date_key(record):
    date = record.get("date") or ""
    if not date or date == "unknown" or record.get("date_precision") == "unknown":
        date = "9999"
    return date, record["id"]


def report(case):
    case = Path(case)
    events = records(case)
    latest = validate(events, case)
    meta = json.loads((case / "case.json").read_text(encoding="utf-8"))
    by_kind = {k: [r for r in latest.values() if r["kind"] == k] for k in REQUIRED}
    counts = Counter(r["access"] for r in by_kind["source"])
    lines = [f"# {meta['person']}｜研究记录摘要", "", f"本轮范围：{meta['scope']}", "",
             f"保留 {len(events)} 条记录；检索批次 {len(by_kind['search'])}，查询词 {sum(len(r['queries']) for r in by_kind['search'])}，访问行为 {len(by_kind['visit'])}，来源条目 {len(by_kind['source'])}，时间线事件 {len(by_kind['event'])}。", "",
             "这些数量不代表独立证据数、事实准确率或互联网覆盖率。记录时间不等于实际访问时间。", "", "获取层级：" + json.dumps(dict(counts), ensure_ascii=False), "",
             "| 来源 | 标题 | 获取层级 | 地址 | 限制 |", "|---|---|---|---|---|"]
    for r in by_kind["source"]:
        lines.append("| " + " | ".join(cell(r[k]) for k in ("id", "title", "access", "url", "limitation")) + " |")
    if by_kind["event"]:
        lines.extend(["", "| 日期 | 精度 | 范围 | 事件 | 地点 | 状态 | 证据类型 | 来源/结论 |", "|---|---|---|---|---|---|---|---|"])
        for r in sorted(by_kind["event"], key=event_date_key):
            parts = list(r.get("source_ids", [])) + list(r.get("claim_ids", []))
            for loc in r.get("sources", []):
                label = loc.get("source_id") or loc.get("id") or loc.get("file", "")
                if loc.get("lines"):
                    label += f" L{loc['lines']}"
                parts.append(label)
            refs = ", ".join(dict.fromkeys(parts))
            lines.append("| " + " | ".join(cell(v) for v in (
                r.get("date", ""), r["date_precision"], r.get("scope", ""), r["title"],
                r.get("place", ""), r["status"], r.get("evidence_type", ""), refs)) + " |")
    lines.extend(["", "| 来源家族 | 状态 | 实际范围 | 原因 |", "|---|---|---|---|"])
    for r in by_kind["coverage"]:
        lines.append("| " + " | ".join(cell(r[k]) for k in ("family", "state", "scope", "reason")) + " |")
    lines.extend(["", "| 线索 | 状态 | 问题 | 下一步 |", "|---|---|---|---|"])
    for r in by_kind["clue"]:
        lines.append("| " + " | ".join(cell(r[k]) for k in ("id", "state", "question", "next_step")) + " |")
    lines.extend(["", "这是结构化记录的摘要，不能替代带证据定位的正文及人工核验。", ""])
    return "\n".join(lines)


KIND_PREFIX = {
    "search": "Q", "visit": "V", "source": "S", "claim": "C",
    "event": "EV", "clue": "L", "coverage": "COV",
}
KIND_ORDER = {kind: index for index, kind in enumerate(
    ("search", "visit", "source", "claim", "event", "clue", "coverage"))}
REFERENCE_FIELDS = ("visit_ids", "discovery_ids", "source_ids", "claim_ids", "origin_ids", "record_ids")
ACCESS_RANK = {
    "unretrieved": 0, "search_only": 1, "metadata_only": 2, "partial_text": 3,
    "audio_video_reviewed": 4, "transcript": 4, "full_text": 5,
}


def id_number(record):
    digits = "".join(ch for ch in record["id"] if ch.isdigit())
    return int(digits) if digits else 0


def normalized_title(value):
    return "".join(str(value).split())


def merge_case(case, report_path=None, force=False, dry_run=False):
    """Merge shard ledgers into the case ledger. Structural work only.

    The merge assigns stable IDs, rewrites references, deduplicates sources by
    exact URL, merges events explicitly marked with the same event group,
    namespaces source groups per shard, and downgrades corroborated claims or
    events that cannot show two independent source groups afterwards. It never
    decides which conflicting date or claim is true.
    """
    case = Path(case)
    target = case / "records.jsonl"
    if target.exists() and target.read_text(encoding="utf-8").strip() and not force:
        raise RecordError("records.jsonl 非空；如需覆盖请加 --force")

    shards_root = case / "shards"
    if not shards_root.is_dir():
        raise RecordError("没有分片目录 shards/")
    shard_dirs = sorted(path for path in shards_root.iterdir() if path.is_dir())
    if not shard_dirs:
        raise RecordError("shards/ 下没有分片")

    shard_data = []
    seen_shard_ids = set()
    for directory in shard_dirs:
        meta_path = directory / "shard.json"
        if not meta_path.is_file():
            raise RecordError(f"{directory.name}: 缺少 shard.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or not nonempty(meta.get("id")) or not nonempty(meta.get("family")):
            raise RecordError(f"{directory.name}: shard.json 须有非空 id 与 family")
        shard_id = meta["id"]
        if shard_id in seen_shard_ids:
            raise RecordError(f"分片 ID 重复：{shard_id}")
        seen_shard_ids.add(shard_id)
        items = read_jsonl(directory / "records.jsonl")
        latest = validate(items, directory)
        shard_data.append({"path": directory, "meta": meta, "items": items, "latest": latest})

    counters = Counter()
    provisional = {}
    ordered = []
    for shard in shard_data:
        shard_id = shard["meta"]["id"]
        for old_id, record in shard["latest"].items():
            kind = record["kind"]
            counters[kind] += 1
            new_id = f"{KIND_PREFIX[kind]}{counters[kind]:02d}"
            provisional[(shard_id, old_id)] = new_id
            ordered.append((shard_id, old_id, record))

    source_merge = {}
    source_unions = {}
    source_duplicates = []
    first_by_url = {}

    def add_source_union(kept_id, shard_id, record):
        union = source_unions.setdefault(
            kept_id, {"visit_ids": [], "discovery_ids": [], "accesses": [], "group": None})
        union["visit_ids"].extend((shard_id, value) for value in record.get("visit_ids", []))
        union["discovery_ids"].extend((shard_id, value) for value in record.get("discovery_ids", []))
        if record.get("access"):
            union["accesses"].append(record["access"])
        if union["group"] is None and nonempty(record.get("same_source_group")):
            union["group"] = f"{shard_id}/{record['same_source_group']}"

    for shard_id, old_id, record in ordered:
        if record["kind"] != "source":
            continue
        url = record.get("url")
        if not nonempty(url):
            continue
        provisional_id = provisional[(shard_id, old_id)]
        if url in first_by_url:
            kept_id = first_by_url[url]
            source_merge[provisional_id] = kept_id
            source_duplicates.append({"url": url, "kept": kept_id, "merged": f"{shard_id}:{old_id}"})
            add_source_union(kept_id, shard_id, record)
        else:
            first_by_url[url] = provisional_id
            add_source_union(provisional_id, shard_id, record)

    def final_id(shard_id, old_id):
        key = (shard_id, old_id)
        if key not in provisional:
            raise RecordError(f"{shard_id}: 未知引用 {old_id!r}")
        provisional_id = provisional[key]
        return source_merge.get(provisional_id, provisional_id)

    # Duplicate URLs connect the shard-local names for the same origin.
    group_mapping = canonical_groups(
        (record["url"], f"{shard_id}/{record['same_source_group']}")
        for shard_id, _, record in ordered
        if record["kind"] == "source" and nonempty(record.get("same_source_group")))

    def mapped_group(shard_id, group):
        name = f"{shard_id}/{group}"
        return group_mapping.get(name, name)

    output = []
    for shard_id, old_id, record in ordered:
        provisional_id = provisional[(shard_id, old_id)]
        if record["kind"] == "source" and provisional_id in source_merge:
            continue
        merged = copy.deepcopy(record)
        merged["id"] = final_id(shard_id, old_id)
        merged["shard_id"] = shard_id
        for field in REFERENCE_FIELDS:
            if field in merged:
                merged[field] = [final_id(shard_id, ref) for ref in merged[field]]
        for evidence in merged.get("evidence", []):
            if "source_id" in evidence:
                evidence["source_id"] = final_id(shard_id, evidence["source_id"])
        if "source_groups" in merged:
            merged["source_groups"] = {
                final_id(shard_id, sid) if (shard_id, sid) in provisional else f"{shard_id}/{sid}": mapped_group(shard_id, group)
                for sid, group in merged["source_groups"].items()}
        for locator in merged.get("sources", []):
            for key in ("source_id", "id"):
                if key in locator:
                    locator[key] = (final_id(shard_id, locator[key])
                                    if (shard_id, locator[key]) in provisional
                                    else f"{shard_id}/{locator[key]}")
            if nonempty(locator.get("group")):
                locator["group"] = mapped_group(shard_id, locator["group"])
            if nonempty(locator.get("file")) and not locator["file"].startswith("shards/"):
                locator["file"] = f"shards/{shard_id}/{locator['file']}"
        if merged["kind"] in {"search", "visit"} and not merged["raw_path"].startswith("shards/"):
            merged["raw_path"] = f"shards/{shard_id}/{merged['raw_path']}"
        if nonempty(merged.get("same_source_group")):
            merged["same_source_group"] = mapped_group(shard_id, merged["same_source_group"])
        if merged["kind"] == "source" and provisional_id in source_unions:
            union = source_unions[provisional_id]
            merged["visit_ids"] = list(dict.fromkeys(
                final_id(shard, ref) for shard, ref in union["visit_ids"]))
            if union["discovery_ids"]:
                merged["discovery_ids"] = list(dict.fromkeys(
                    final_id(shard, ref) for shard, ref in union["discovery_ids"]))
            if union["accesses"]:
                merged["access"] = max(union["accesses"], key=lambda value: ACCESS_RANK.get(value, -1))
            if not nonempty(merged.get("same_source_group")) and union["group"]:
                merged["same_source_group"] = group_mapping.get(union["group"], union["group"])
        output.append(merged)

    output.sort(key=lambda record: (KIND_ORDER[record["kind"]], id_number(record), record.get("shard_id", "")))

    event_groups = {}
    for record in output:
        if record["kind"] == "event" and nonempty(record.get("same_event_group")):
            event_groups.setdefault(record["same_event_group"], []).append(record)

    event_merge = {}
    skipped_events = set()
    conflicts = []
    for group, events in event_groups.items():
        if len(events) < 2:
            continue
        kept = events[0]
        for duplicate in events[1:]:
            if duplicate.get("date") != kept.get("date") or (duplicate.get("place") or "") != (kept.get("place") or ""):
                conflicts.append({
                    "same_event_group": group,
                    "events": [kept["id"], duplicate["id"]],
                    "date": [kept.get("date"), duplicate.get("date")],
                    "place": [kept.get("place"), duplicate.get("place")],
                })
                continue
            for field in ("source_ids", "claim_ids"):
                kept[field] = list(dict.fromkeys(kept.get(field, []) + duplicate.get(field, [])))
            locators = kept.get("sources", []) + duplicate.get("sources", [])
            seen = set()
            kept["sources"] = []
            for locator in locators:
                marker = json.dumps(locator, ensure_ascii=False, sort_keys=True)
                if marker not in seen:
                    seen.add(marker)
                    kept["sources"].append(locator)
            event_merge[duplicate["id"]] = kept["id"]
            skipped_events.add(duplicate["id"])

    output = [record for record in output if record["id"] not in skipped_events]
    if event_merge:
        for record in output:
            for field in REFERENCE_FIELDS:
                if field in record:
                    record[field] = [event_merge.get(ref, ref) for ref in record[field]]

    duplicate_candidates = {}
    for record in output:
        if record["kind"] != "event":
            continue
        key = (record.get("date", ""), normalized_title(record.get("title", "")), record.get("place", ""))
        duplicate_candidates.setdefault(key, []).append(record["id"])
    duplicate_candidates = [
        {"date": key[0], "title": key[1], "place": key[2], "events": ids}
        for key, ids in duplicate_candidates.items() if len(ids) > 1
    ]

    sources = {record["id"]: record for record in output if record["kind"] == "source"}
    downgraded = []

    for record in output:
        kind = record["kind"]
        if kind not in {"event", "claim"} or record.get("status") != "corroborated":
            continue
        support = event_support(record, sources) if kind == "event" else claim_support(record, sources)
        if not independent_pair(support):
            target_status = "documented" if kind == "event" else "documented_statement"
            record["status"] = target_status
            record["merge_note"] = f"合并后台账复核：不足两个已取得、不同 URL 且不同同源组的支持来源，降为 {target_status}"
            downgraded.append({"id": record["id"], "kind": kind, "reason": record["merge_note"]})

    for index, record in enumerate(output, 1):
        record["event_id"] = f"E{index:06d}"

    validate(output, case)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "shards": [
            {
                "id": shard["meta"]["id"],
                "family": shard["meta"]["family"],
                "status": shard["meta"].get("status", ""),
                "stop_reason": shard["meta"].get("stop_reason", ""),
                "input_records": len(shard["items"]),
                "latest_records": len(shard["latest"]),
            }
            for shard in shard_data
        ],
        "counts": {
            "input_records": sum(len(shard["items"]) for shard in shard_data),
            "output_records": len(output),
            "by_kind": dict(Counter(record["kind"] for record in output)),
        },
        "id_map": {
            shard_id: {old_id: final_id(shard_id, old_id) for old_id in shard["latest"]}
            for shard_id, shard in ((shard["meta"]["id"], shard) for shard in shard_data)
        },
        "source_duplicates": source_duplicates,
        "event_merged": [{"from": duplicate, "into": kept} for duplicate, kept in event_merge.items()],
        "duplicate_candidates": duplicate_candidates,
        "conflicts": conflicts,
        "corroborated_downgraded": downgraded,
    }

    if not dry_run:
        text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in output)
        pending = case / "records.jsonl.pending"
        pending.write_text(text, encoding="utf-8")
        pending.replace(target)
        report_file = Path(report_path) if report_path else case / "merge-report.json"
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report, output


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
    merge = sub.add_parser("merge")
    merge.add_argument("case")
    merge.add_argument("--report", help="合并报告路径，默认 <案例目录>/merge-report.json")
    merge.add_argument("--force", action="store_true", help="覆盖已有的 records.jsonl")
    merge.add_argument("--dry-run", action="store_true", help="只计算，不写主台账与报告")
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
        elif args.command == "merge":
            summary, merged = merge_case(
                args.case, report_path=args.report, force=args.force, dry_run=args.dry_run)
            action = "试算" if args.dry_run else "合并完成"
            print(
                f"{action}：{len(summary['shards'])} 个分片，{len(merged)} 条记录；"
                f"来源去重 {len(summary['source_duplicates'])}，事件合并 {len(summary['event_merged'])}，"
                f"冲突 {len(summary['conflicts'])}，状态降级 {len(summary['corroborated_downgraded'])}")
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
